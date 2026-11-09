// shared/location/manager.ts
//
// Centralized, reusable GPS acquisition manager. This is the single entry
// point for all "use my location" flows in the app (student scan, classroom
// map picker, and any future consumer). It wraps the low-level
// `requestBestPosition` primitive in shared/utils/geo.ts and adds:
//
//   - a standardized LocationState shape,
//   - permission introspection (best-effort, feature-detected),
//   - validation helpers that reuse the pure geofence math in geo.ts,
//   - consistent error normalization,
//   - cancellation via AbortController.
//
// The geofence math itself stays in shared/utils/geo.ts (pure functions,
// unit-tested independently). This module depends on geo.ts; geo.ts must
// never import from here.

import {
	requestBestPosition,
	isWithinGeofence,
	isWithinGeofenceWithUncertainty,
	type BestPosition,
} from '$lib/shared/utils/geo';
import { APIError } from '$lib/api/client';

export type PermissionStatus = 'granted' | 'denied' | 'prompt' | 'unsupported';

export interface LocationState {
	latitude: number | null;
	longitude: number | null;
	accuracy: number | null;
	timestamp: number | null;
	altitude: number | null;
	heading: number | null;
	speed: number | null;
	permissionStatus: PermissionStatus;
	loading: boolean;
	error: { code: string; message: string } | null;
	source: 'gps' | 'cached' | 'manual' | 'fallback' | null;
}

export interface AcquireOptions {
	desiredAccuracy?: number;
	maxFixes?: number;
	timeoutMs?: number;
	maxAccuracy?: number;
	signal?: AbortSignal;
	fastFirst?: boolean;
	fastMaximumAge?: number;
	fastAccuracyThreshold?: number;
}

export interface ValidationResult {
	ok: boolean;
	reason: 'ok' | 'hard_floor' | 'outside_geofence' | 'review_band';
}

const DEFAULTS: Required<Omit<AcquireOptions, 'signal'>> = {
	desiredAccuracy: 50,
	maxFixes: 3,
	timeoutMs: 10000,
	maxAccuracy: 1000,
	fastFirst: true,
	fastMaximumAge: 0,
	fastAccuracyThreshold: 50,
};

function normalizeError(e: unknown): { code: string; message: string } {
	if (e instanceof APIError) {
		return { code: e.code ?? 'location_unavailable', message: e.message };
	}
	if (e instanceof Error) {
		const code = (e as { code?: unknown }).code;
		return {
			code: typeof code === 'string' && code.length > 0 ? code : 'location_unavailable',
			message: e.message,
		};
	}
	return { code: 'location_unavailable', message: 'Unable to get your location.' };
}

/**
 * Query the current geolocation permission state. Returns 'unsupported'
 * when the Permissions API is unavailable (Safari, older browsers) — callers
 * must treat that as "unknown, just try".
 */
export async function queryPermissionStatus(): Promise<PermissionStatus> {
	if (typeof navigator === 'undefined' || !navigator.permissions?.query) {
		return 'unsupported';
	}
	try {
		const status = await navigator.permissions.query({ name: 'geolocation' as PermissionName });
		return (status.state as PermissionStatus) ?? 'unsupported';
	} catch {
		return 'unsupported';
	}
}

/**
 * Subscribe to permission changes. Returns an unsubscribe function. No-op
 * (returns a no-op) when the Permissions API is unavailable.
 */
export function watchPermissionStatus(callback: (status: PermissionStatus) => void): () => void {
	if (typeof navigator === 'undefined' || !navigator.permissions?.query) {
		return () => {};
	}
	let cancelled = false;
	let permStatus: any = null;
	navigator.permissions
		.query({ name: 'geolocation' as PermissionName })
		.then((s) => {
			if (cancelled) return;
			permStatus = s;
			const handler = () => {
				if (!cancelled) callback((s.state as PermissionStatus) ?? 'unsupported');
			};
			s.addEventListener('change', handler);
			// store cleanup
			(unsubscribe as any)._handler = handler;
			(unsubscribe as any)._status = s;
		})
		.catch(() => {
			if (!cancelled) callback('unsupported');
		});

	const unsubscribe = () => {
		cancelled = true;
		const s = (unsubscribe as any)._status as any;
		const h = (unsubscribe as any)._handler as EventListener | null;
		if (s && h) {
			try {
				s.removeEventListener('change', h);
			} catch {
				// ignore
			}
		}
	};
	return unsubscribe;
}

/**
 * Acquire a single best-effort GPS fix. Never throws for permission/timeout/
 * unavailable — those are reported via the returned LocationState.error. The
 * underlying requestBestPosition may still throw for programming errors; those
 * are normalized too.
 */
export async function acquire(options?: AcquireOptions): Promise<LocationState> {
	const opts = { ...DEFAULTS, ...(options ?? {}) };
	const state: LocationState = {
		latitude: null,
		longitude: null,
		accuracy: null,
		timestamp: null,
		altitude: null,
		heading: null,
		speed: null,
		permissionStatus: await queryPermissionStatus(),
		loading: true,
		error: null,
		source: null,
	};

	let fix: BestPosition;
	try {
		fix = await requestBestPosition({
			desiredAccuracy: opts.desiredAccuracy,
			maxFixes: opts.maxFixes,
			timeoutMs: opts.timeoutMs,
			maxAccuracy: opts.maxAccuracy,
			signal: opts.signal,
			fastFirst: opts.fastFirst,
			fastMaximumAge: opts.fastMaximumAge,
			fastAccuracyThreshold: opts.fastAccuracyThreshold,
		});
	} catch (e) {
		state.loading = false;
		state.error = normalizeError(e);
		return state;
	}

	state.latitude = fix.lat;
	state.longitude = fix.lng;
	state.accuracy = fix.accuracy;
	state.timestamp = fix.timestamp ?? null;
	state.loading = false;
	state.source = 'gps';
	return state;
}

/**
 * Validate a fix against a geofence context. Reuses the pure helpers in
 * geo.ts so client and server agree.
 */
export function validateGeofence(
	fix: { lat: number; lng: number; accuracy: number },
	center: { lat: number | null; lng: number | null; radius: number },
	uncertaintyCap: number,
	hardFloor: number
): ValidationResult {
	if (hardFloor > 0 && fix.accuracy > hardFloor) {
		return { ok: false, reason: 'hard_floor' };
	}
	if (center.lat === null || center.lng === null) {
		return { ok: true, reason: 'ok' };
	}
	if (isWithinGeofence(fix.lat, fix.lng, center.lat, center.lng, center.radius)) {
		return { ok: true, reason: 'ok' };
	}
	if (isWithinGeofenceWithUncertainty(fix.lat, fix.lng, center.lat, center.lng, center.radius, fix.accuracy, uncertaintyCap)) {
		return { ok: true, reason: 'review_band' };
	}
	return { ok: false, reason: 'outside_geofence' };
}

/**
 * Convenience: build a LocationState from a cached/manual fix (no GPS call).
 */
export function fromManual(lat: number, lng: number, accuracy: number | null = null): LocationState {
	return {
		latitude: lat,
		longitude: lng,
		accuracy,
		timestamp: Date.now(),
		altitude: null,
		heading: null,
		speed: null,
		permissionStatus: 'unsupported',
		loading: false,
		error: null,
		source: 'manual',
	};
}