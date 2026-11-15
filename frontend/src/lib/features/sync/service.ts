// features/sync/service.ts
// Offline scan outbox over IndexedDB (docs/architecture/offline-first.md).
//
// Real persistence by default: failed scan submissions enqueue with their
// device-time scanned_at and drain oldest-first through the live scan
// endpoint with X-Idempotency-Key = queue id (the backend keys idempotency
// on user_id:session_id:key, so replays never double-record). Server
// decisions (duplicate, mismatch, validation) are terminal (rejected +
// last_error); transient failures — network loss, 429 rate-limit, timeouts,
// 5xx — stay pending with exponential backoff.
//
// Two fallbacks share one code path: PUBLIC_MOCK_MODE=true and environments
// without IndexedDB (SSR, some private modes) use an in-memory map instead —
// same shapes, lost on reload. flushQueue is a no-op in mock mode (there is
// no backend to drain into).

import { APIError, isMockMode } from '$lib/api/client';
import type { LivenessEvidence } from '$lib/shared/types';
import { submitAttendanceScan } from '$lib/features/liveness/service';

export type QueuedScanPayload = {
	sessionId: number;
	sessionCode: string;
	studentNumber: string;
	// Location is optional: scans against sessions with no geofence (remote,
	// disabled, or no classroom coordinates) do not collect GPS.
	gps: { lat: number; lng: number; accuracy: number } | null;
	livenessEvidence: LivenessEvidence;
	liveFaceEmbedding?: string;
	liveFaceImage?: string;
	scannedAt: string;
	idempotencyKey?: string;
};

export type QueuedScanStatus = 'pending' | 'syncing' | 'synced' | 'rejected';

export type QueuedScan = {
	id: string;
	type: 'attendance_scan';
	status: QueuedScanStatus;
	payload: QueuedScanPayload;
	createdAt: string;
	updatedAt: string;
	attempts: number;
	maxAttempts: number;
	lastError: string | null;
};

export type CachedSession = {
	session_id: number;
	code: string;
	course_code: string;
	course_name: string;
	expires_at: string;
	// Actual scheduled class start time (UTC ISO). Cached separately from
	// expires_at so the offline confirmation screen shows the real class start
	// instead of the scan-window expiry. Optional for entries cached by older
	// clients; those fall back to expires_at.
	scheduled_start_time?: string;
	// Actual scheduled class end time (UTC ISO). Cached separately from
	// expires_at so the offline confirmation screen shows the real class end
	// instead of the scan-window expiry. Optional for entries cached by older
	// clients; those fall back to expires_at.
	scheduled_end_time?: string;
	// Immutable per-session attempt cap (0 = unlimited). Safe to cache
	// because it never changes after the session is created — unlike the
	// remaining count, which the offline path must NOT cache (it goes
	// stale by design and the server re-decides on sync). Optional for
	// entries cached before the attempt-metadata contract.
	attendance_attempt_limit?: number;
	// Center null = no classroom coordinates (mirrors VerifyGeofence); the
	// scan pre-check skips geofence in that case, same as the server.
	geofence: { radius: number; lat: number | null; lng: number | null; uncertaintyCapMeters?: number; gpsHardFloorMeters?: number; gpsReviewAccuracyThreshold?: number };
	// Cached so the offline path can decide whether location is required
	// without re-deriving it from the (possibly stale) geofence center.
	geofenceEnabled?: boolean;
	isRemote?: boolean;
	cached_at: string;
};

const DB_NAME = 'attendly';
const DB_VERSION = 2;
const QUEUE_STORE = 'attendance_queue';
const SESSION_STORE = 'session_cache';
export const FACE_STORE = 'face_embeddings';
export const KEY_STORE = 'face_keys';

// Synced rows are history, not work: prune them a week after they land so
// the store stays bounded to genuinely actionable items.
const SYNCED_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
const DEFAULT_MAX_ATTEMPTS = 25;

// Retry delay: min(30s * 2^retry_count, 30 minutes) per offline-first.md.
export const retryDelayMs = (retryCount: number): number =>
	Math.min(30_000 * 2 ** Math.max(0, retryCount), 30 * 60 * 1000);

// registerOutboxSync
// Best-effort Background Sync wake-up so a browser-restart or worker wake can
// nudge open pages to drain. The worker only relays FLUSH_OUTBOX messages —
// the authed replay stays in flushQueue (the worker cannot read the
// localStorage token). Never rejects; unsupported browsers just skip it.
export const registerOutboxSync = async (): Promise<void> => {
	try {
		if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
		const registration = await navigator.serviceWorker.ready;
		const syncManager = (
			registration as ServiceWorkerRegistration & {
				sync?: { register: (tag: string) => Promise<void> };
			}
		).sync;
		if (!syncManager) return;
		await syncManager.register('attendly-outbox');
	} catch (error) {
		// No service worker / SyncManager (Firefox, iOS): the page-driven
		// online-event and retry-timer paths already cover the drain. Log at
		// debug so a real registration failure (e.g. quota) is diagnosable
		// instead of silent.
		console.debug('[sync] Background Sync registration skipped:', error);
	}
};

// --- IndexedDB plumbing ------------------------------------------------------

export const openAppDb = (): Promise<IDBDatabase> =>
	new Promise((resolve, reject) => {
		if (typeof indexedDB === 'undefined') {
			reject(new Error('IndexedDB is unavailable'));
			return;
		}
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(QUEUE_STORE)) {
				const store = db.createObjectStore(QUEUE_STORE, { keyPath: 'id' });
				store.createIndex('status', 'status');
			}
			if (!db.objectStoreNames.contains(SESSION_STORE)) {
				db.createObjectStore(SESSION_STORE, { keyPath: 'session_id' });
			}
			// v2: face-embedding cache (keyPath 'student') + device keys
			// (keyPath 'id'). Existing v1 stores carry over untouched.
			if (!db.objectStoreNames.contains(FACE_STORE)) {
				db.createObjectStore(FACE_STORE, { keyPath: 'student' });
			}
			if (!db.objectStoreNames.contains(KEY_STORE)) {
				db.createObjectStore(KEY_STORE, { keyPath: 'id' });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error ?? new Error('Unable to open offline queue'));
	});

const requestToPromise = <T>(request: IDBRequest<T>): Promise<T> =>
	new Promise((resolve, reject) => {
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error ?? new Error('Offline queue access failed'));
	});

const withStore = async <T>(
	storeName: string,
	mode: IDBTransactionMode,
	run: (store: IDBObjectStore) => Promise<T>
): Promise<T> => {
	const db = await openAppDb();
	try {
		const transaction = db.transaction(storeName, mode);
		const result = await run(transaction.objectStore(storeName));
		await new Promise<void>((resolve, reject) => {
			transaction.oncomplete = () => resolve();
			transaction.onerror = () => reject(transaction.error ?? new Error('Offline queue write failed'));
			transaction.onabort = () => reject(transaction.error ?? new Error('Offline queue write aborted'));
		});
		return result;
	} finally {
		db.close();
	}
};

// Generic IndexedDB access against the shared database, for sibling slices
// (face-embedding cache). Callers own their fallback when storage is
// unavailable — these throw.
export const idbGet = async <T>(storeName: string, key: IDBValidKey): Promise<T | undefined> =>
	withStore(storeName, 'readonly', (store) => requestToPromise(store.get(key) as IDBRequest<T | undefined>));

export const idbGetAll = async <T>(storeName: string): Promise<T[]> =>
	withStore(storeName, 'readonly', (store) => requestToPromise(store.getAll() as IDBRequest<T[]>));

export const idbPut = async (storeName: string, value: unknown): Promise<void> =>
	withStore(storeName, 'readwrite', async (store) => void requestToPromise(store.put(value)));

export const idbDelete = async (storeName: string, key: IDBValidKey): Promise<void> =>
	withStore(storeName, 'readwrite', async (store) => void requestToPromise(store.delete(key)));

// In-memory fallback (mock mode or no IndexedDB): same row shapes, lost on reload.
const memoryQueue = new Map<string, QueuedScan>();
const memorySessions = new Map<number, CachedSession>();
let idbUnusable = false;

// Cross-tab drain coordination. Web Locks (see flushQueue) is the primary
// guard; BroadcastChannel is the fallback signal so tabs that cannot acquire a
// lock at least know another tab is draining and skip their own run.
let remoteDraining = false;
let drainChannel: BroadcastChannel | null = null;
if (typeof BroadcastChannel !== 'undefined') {
	try {
		drainChannel = new BroadcastChannel('attendly-outbox-drain');
		drainChannel.onmessage = (event: MessageEvent) => {
			const data = event.data as { type?: unknown } | null;
			if (data?.type === 'drain-start') remoteDraining = true;
			else if (data?.type === 'drain-end') remoteDraining = false;
		};
	} catch {
		drainChannel = null;
	}
}

const broadcastDrain = (type: 'drain-start' | 'drain-end'): void => {
	try {
		drainChannel?.postMessage({ type });
	} catch {
		// ignore
	}
};

const useMemory = (): boolean => isMockMode() || idbUnusable || typeof indexedDB === 'undefined';

const idbOrMemory = async <T>(fn: () => Promise<T>, fallback: () => T): Promise<T> => {
	if (useMemory()) return fallback();
	try {
		return await fn();
	} catch {
		idbUnusable = true;
		return fallback();
	}
};

// --- Queue -------------------------------------------------------------------

const nowIso = (): string => new Date().toISOString();

// Queue/idempotency ids: crypto UUIDs when available; the fallback mixes a
// timestamp, a per-session counter, and randomness so two rapid offline scans
// can never share an id (bare Math.random() could collide and the second
// scan would reuse the first scan's idempotency key on replay).
let fallbackSeq = 0;
export const newQueueId = (): string => {
	if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
	fallbackSeq += 1;
	return `q-${Date.now().toString(36)}-${fallbackSeq.toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};

const listRows = (): Promise<QueuedScan[]> =>
	idbOrMemory(
		() => idbGetAll<QueuedScan>(QUEUE_STORE),
		() => [...memoryQueue.values()]
	);

const writeRow = (row: QueuedScan): Promise<void> =>
	idbOrMemory(
		() => idbPut(QUEUE_STORE, row),
		() => void memoryQueue.set(row.id, row)
	);

const deleteRow = (id: string): Promise<void> =>
	idbOrMemory(
		() => idbDelete(QUEUE_STORE, id),
		() => void memoryQueue.delete(id)
	);

const byOldest = (a: QueuedScan, b: QueuedScan): number =>
	a.createdAt === b.createdAt ? a.id.localeCompare(b.id) : a.createdAt.localeCompare(b.createdAt);

// Single-flight guard for flushQueue: the per-page `flushing` flags don't span
// callers (the scan page's online drain vs History's "Sync now"), and two
// loops racing over one row is how a recorded scan got painted as a spurious
// "Rejected · duplicate_scan" card. A concurrent second caller simply finds
// its work already in flight.
let draining = false;

// recoverOrphanedSyncing
// A drain stamps rows 'syncing' before its POST and only back-converts them on
// a failure observed while the process is alive. If the tab dies mid-drain
// (reload, crash, laptop sleep) those rows are stranded forever: the drain
// filter reads 'pending' only, yet they keep counting as "N pending" in the
// banner, every flush returns {0,0,0}, and enqueue treats them as
// already-queued — silently discarding a fresh scan's payload. Normalize them
// back to pending; rows genuinely mid-drain are protected by `draining`.
const recoverOrphanedSyncing = async (): Promise<void> => {
	if (draining) return;
	const rows = await listRows();
	for (const row of rows) {
		if (row.status === 'syncing') {
			await writeRow({ ...row, status: 'pending', updatedAt: nowIso() });
		}
	}
};

// queue
// Offline scan outbox. Enqueue is duplicate-safe: a scan for a session that
// already has a pending/syncing item returns the existing item instead of
// queueing twice (spec: local duplicate check).
export const queue = {
	// Enqueue a completed scan submission for later sync
	enqueue: async (record: Omit<QueuedScan, 'id' | 'createdAt' | 'updatedAt' | 'attempts' | 'maxAttempts' | 'status' | 'lastError'>): Promise<QueuedScan> => {
		const rows = await listRows();
		const existing = rows.find(
			(row) =>
				row.payload.sessionId === record.payload.sessionId &&
				(row.status === 'pending' || row.status === 'syncing')
		);
		if (existing) return existing;
		const createdAt = nowIso();
		const row: QueuedScan = {
			...record,
			id: newQueueId(),
			status: 'pending',
			createdAt,
			updatedAt: createdAt,
			attempts: 0,
			maxAttempts: DEFAULT_MAX_ATTEMPTS,
			lastError: null
		};
		await writeRow(row);
		// Nudge a future worker wake-up; never breaks the enqueue itself.
		void registerOutboxSync().catch(() => undefined);
		return row;
	},

	// Oldest pending item (next to sync)
	dequeue: async (): Promise<QueuedScan | null> => {
		const rows = await listRows();
		return rows.filter((row) => row.status === 'pending').sort(byOldest)[0] ?? null;
	},

	// Update record status
	updateStatus: async (id: string, status: QueuedScanStatus): Promise<void> => {
		const rows = await listRows();
		const row = rows.find((entry) => entry.id === id);
		if (!row) return;
		await writeRow({ ...row, status, updatedAt: nowIso() });
	},

	// All pending (or mid-sync) records, oldest first
	getPending: async (): Promise<QueuedScan[]> => {
		await recoverOrphanedSyncing();
		const rows = await listRows();
		return rows
			.filter((row) => row.status === 'pending' || row.status === 'syncing')
			.sort(byOldest);
	},

	// Actionable queue depth for the scan banner (pending + syncing only).
	// Rejected rows have their own card with Retry/Discard, so they are
	// excluded here to avoid double-counting the same record twice.
	getPendingCount: async (): Promise<number> => {
		await recoverOrphanedSyncing();
		const rows = await listRows();
		return rows.filter((row) => row.status === 'pending' || row.status === 'syncing').length;
	},

	// Rejected items stay visible until the student discards them
	getRejected: async (): Promise<QueuedScan[]> => {
		const rows = await listRows();
		return rows.filter((row) => row.status === 'rejected').sort(byOldest);
	},

	// Discard a rejected (or stale pending) item
	remove: async (id: string): Promise<void> => {
		await deleteRow(id);
	}
};

// `faceMatchScore` is passed straight through, undefined included:
// `submitAttendanceScan` substitutes FACE_MATCH_SCORE_PLACEHOLDER when it is
// missing, so the field is always sent. Building the body conditionally here
// (as this used to) is what let a required backend field go missing on replay
// and marked queued scans terminally `rejected`.
const toScanBody = (payload: QueuedScanPayload) => ({
	sessionId: payload.sessionId,
	studentNumber: payload.studentNumber,
	gps: payload.gps ?? null,
	livenessEvidence: payload.livenessEvidence,
	liveFaceEmbedding: payload.liveFaceEmbedding,
	liveFaceImage: payload.liveFaceImage,
	scannedAt: payload.scannedAt,
});

// Transient API failures worth another attempt: offline, 429 rate-limit,
// timeouts, cancellations, and 5xx. Everything else the server decided
// (duplicate, mismatch, validation) is terminal. Offline (network_error)
// stays pending the same way it always did via the non-APIError else-branch
// — naming it here only documents the intent after the fetch wrapper started
// emitting it as an APIError.
const isTransientApiError = (error: APIError): boolean => {
	if (
		error.code === 'network_error' ||
		error.code === 'rate_limited' ||
		error.code === 'request_timeout' ||
		error.code === 'request_cancelled'
	)
		return true;
	if (error.status !== undefined && error.status >= 500) return true;
	return false;
};

const markRejected = async (id: string, lastError: string): Promise<void> => {
	const rows = await listRows();
	const row = rows.find((entry) => entry.id === id);
	if (row) {
		await writeRow({ ...row, status: 'rejected', updatedAt: nowIso(), lastError });
	}
};

const markPendingForRetry = async (id: string, lastError: string): Promise<'rejected' | 'pending'> => {
	const rows = await listRows();
	const row = rows.find((entry) => entry.id === id);
	if (!row) return 'pending';
	const attempts = row.attempts + 1;
	if (attempts >= row.maxAttempts) {
		await writeRow({ ...row, status: 'rejected', updatedAt: nowIso(), attempts, lastError });
		return 'rejected';
	}
	await writeRow({ ...row, status: 'pending', updatedAt: nowIso(), attempts, lastError });
	return 'pending';
};

// drainOnce
// Inner drain implementation. Assumes the caller holds the single-flight
// guard (either the in-process `draining` flag or the cross-tab Web Lock).
// Drain pending items oldest-first through the live scan endpoint, one
// idempotent replay each (X-Idempotency-Key = queue id). Stops at the first
// transient failure — the rest would fail the same way — and leaves backoff
// scheduling to the caller via retryDelayMs.
const drainOnce = async (): Promise<{ synced: number; rejected: number; failed: number }> => {
	if (isMockMode()) return { synced: 0, rejected: 0, failed: 0 };
	if (draining) return { synced: 0, rejected: 0, failed: 0 };
	draining = true;
	try {
		await recoverOrphanedSyncing();
		const pending = (await listRows())
			.filter((row) => row.status === 'pending')
			.sort(byOldest);
		let synced = 0;
		let rejected = 0;
		let failed = 0;
		for (const item of pending) {
			await queue.updateStatus(item.id, 'syncing');
			try {
				await submitAttendanceScan({
					...toScanBody(item.payload),
					idempotencyKey: item.payload.idempotencyKey || item.id
				});
				await queue.updateStatus(item.id, 'synced');
				synced += 1;
			} catch (error) {
				if (error instanceof APIError && !isTransientApiError(error)) {
					// The server decided: terminal, with its reason code preserved
					// for the user-facing message.
					await markRejected(item.id, error.code);
					rejected += 1;
				} else {
					// Still offline — or throttled/timed-out/5xx: back to pending
					// with backoff; stop draining. A 429 must never burn queued
					// evidence the way a decision code does.
					const lastError = error instanceof APIError ? error.code : 'network_error';
					const outcome = await markPendingForRetry(item.id, lastError);
					if (outcome === 'rejected') rejected += 1;
					else failed += 1;
					break;
				}
			}
		}
		await pruneSynced();
		return { synced, rejected, failed };
	} finally {
		draining = false;
	}
};

// flushQueue
// Cross-tab single-flight wrapper around drainOnce. Uses the Web Locks API
// when available so two browser tabs cannot drain the same IndexedDB queue
// concurrently; falls back to the in-process guard on unsupported browsers
// (Firefox, older Safari), where the existing per-tab guard still applies.
export const flushQueue = async (): Promise<{ synced: number; rejected: number; failed: number }> => {
	if (isMockMode()) return { synced: 0, rejected: 0, failed: 0 };
	if (remoteDraining) return { synced: 0, rejected: 0, failed: 0 };

	const locks = (typeof navigator !== 'undefined'
		? (navigator as Navigator & {
				locks?: {
					request: (
						name: string,
						options: { ifAvailable: boolean },
						callback: (lock: unknown) => Promise<void>
					) => Promise<void>;
				};
			}).locks
		: undefined);

	if (locks) {
		let result: { synced: number; rejected: number; failed: number } = {
			synced: 0,
			rejected: 0,
			failed: 0
		};
		let started = false;
		await locks.request(
			'attendly-outbox-drain',
			{ ifAvailable: true },
			async (lock: unknown) => {
				if (!lock) return;
				started = true;
				broadcastDrain('drain-start');
				result = await drainOnce();
			}
		);
		if (started) broadcastDrain('drain-end');
		return result;
	}

	broadcastDrain('drain-start');
	try {
		return await drainOnce();
	} finally {
		broadcastDrain('drain-end');
	}
};

const pruneSynced = async (): Promise<void> => {
	const cutoff = Date.now() - SYNCED_RETENTION_MS;
	const rows = await listRows();
	for (const row of rows) {
		if (row.status === 'synced' && Date.parse(row.updatedAt) < cutoff) {
			await deleteRow(row.id);
		}
	}
};

// --- Session cache ------------------------------------------------------------
// Snapshots of verified session configs so a student who verified the code
// and then lost signal can still complete the scan offline. Freshness = the
// session's own expires_at: an entry for a closed session is never reused.

export const cacheSession = async (entry: Omit<CachedSession, 'cached_at'>): Promise<void> => {
	const row: CachedSession = { ...entry, cached_at: nowIso() };
	await idbOrMemory(
		() => idbPut(SESSION_STORE, row),
		() => void memorySessions.set(row.session_id, row)
	);
};

export const getCachedSession = async (code: string): Promise<CachedSession | null> => {
	const normalized = code.trim();
	const rows: CachedSession[] = await idbOrMemory(
		() => idbGetAll<CachedSession>(SESSION_STORE),
		() => [...memorySessions.values()]
	);
	const match = rows.find((entry) => entry.code === normalized) ?? null;
	if (!match) return null;
	if (Date.parse(match.expires_at) <= Date.now()) return null;
	return match;
};
