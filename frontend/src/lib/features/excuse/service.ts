// features/excuse/service.ts
// Professor excuse queue (D21 Paths A/B/C).
//
// Real API by default; in-memory mock only when PUBLIC_MOCK_MODE=true (see
// api/client.ts). List + review hit the live backend
// (features/excuse/professor_router.py), as do quick/edit/revoke/bulk by
// integer id. The typed-number quick modal is mock-only: no professor
// endpoint returns integer student ids (only numbers/names), so a typed
// student number cannot resolve to the id the per-record routes need.
// without backend help. Path B (evidence upload) rides the D24 presigned
// flow: the quick modal collects files and sends attachment_urls (presence
// selects prof_with_evidence server-side); reason-only stays Path A.
//
// The list row carries its display identity from the server: the student by
// name and number, the class by its course and session code, and the reviewer
// once it has been decided (ADR-088). The client used to join a session and a
// courses directory to recover half of that, and could not recover the other
// half at all — the student and the reviewer have no client-side source — so
// the queues rendered "Student #<id>" where a name belongs.
//
// Contract refs (docs/architecture/api-contracts.md):
// - GET /professor/excuse-requests?status=&page=&size=
//   -> { items, total, page, size }
// - POST /professor/excuse-requests/{rid}/review { status, review_notes? }
//   -> { id, status, reviewed_at }
// - POST /professor/sessions/{id}/attendance/{sid}/excuse (quick-excuse)
//   -> { excuse_request_id, status: "approved", original_status, new_status }

import { EXCUSE_REQUESTS } from '$lib/features/excuse/mock';
import { del, get, isMockMode, patch, post } from '$lib/api/client';
import type {
	ExcuseActionBody,
	ExcuseActionResponse,
	ExcuseBulkResponse,
	ExcuseEditBody,
	ExcuseRequestReadResponse,
	ExcuseRevokeResponse,
	ExcuseReviewBody,
	Paginated,
} from '$lib/api/endpoints';
import type {
	ExcuseInitiatedVia,
	ExcuseOriginalStatus,
	ExcuseRequest,
	ExcuseStatus
} from '$lib/shared/types/excuse';

// Single home for the excuse-reason rule (excuse-workflow.md Path A modal
// spec: min 10 chars). Every quick/edit/bulk entry point — service and page
// pre-checks — goes through here so the client message can never drift from
// itself; a server 422 still surfaces verbatim via the thrown APIError.
export const EXCUSE_REASON_MIN_LENGTH = 10;
export const EXCUSE_REASON_SHORT_MESSAGE = `Reason must be at least ${EXCUSE_REASON_MIN_LENGTH} characters.`;

export const requireExcuseReason = (reason: string): string => {
	const clean = reason.trim();
	if (clean.length < EXCUSE_REASON_MIN_LENGTH) throw new Error(EXCUSE_REASON_SHORT_MESSAGE);
	return clean;
};

// Mock only when the whole app runs without a backend. Defaults to real API.
// Evaluated per call (not frozen at import) so tests and HMR toggling
// PUBLIC_MOCK_MODE cannot leave the service pinned to the wrong backend.

export type ExcuseFilters = {
	status?: ExcuseStatus;
	course?: string;
	search?: string;
	from?: string;
	to?: string;
	page?: number;
	size?: number;
};

export type ExcuseListResult = {
	items: ExcuseRequest[];
	total: number;
	page: number;
	size: number;
	counts: Record<ExcuseStatus, number>;
};

// In-memory working copy so review/quick-excuse mutations show up without a
// backend. Reset on reload — acceptable for mock mode.
let store: ExcuseRequest[] = EXCUSE_REQUESTS.map((row) => ({
	...row,
	attachmentNames: [...row.attachmentNames]
}));

let nextId = Math.max(...store.map((row) => row.id)) + 1;


const initiatedViaFor = (value: string): ExcuseInitiatedVia =>
	value === 'quick' || value === 'prof_with_evidence' || value === 'request'
		? value
		: 'request';

const statusFor = (value: string): ExcuseStatus =>
	value === 'pending' || value === 'approved' || value === 'rejected' ? value : 'pending';

// Map one backend row to the queue view-model.
//
// The display identity comes from the server: the student's name, number and
// section, the session's code and date, the course behind it, and — once the
// request has been decided — who decided it. The pre-excuse status is the
// one field with no source on the row, so it still reads as "unknown".
const mapReadRow = (read: ExcuseRequestReadResponse): ExcuseRequest => {
	return {
		id: read.id,
		studentId: read.student_id,
		studentNumber: read.student_number || `#${read.student_id}`,
		studentName: read.student_name || `Student #${read.student_id}`,
		section: read.student_section || '—',
		courseCode: read.course_code || '—',
		courseName: read.course_name,
		sessionId: read.session_id,
		sessionCode: read.session_code || '—',
		sessionDate: read.session_date || read.requested_at,
		initiatedVia: initiatedViaFor(read.initiated_via),
		reason: read.reason,
		status: statusFor(read.status),
		originalStatus: 'unknown',
		requestedAt: read.requested_at,
		reviewedAt: read.reviewed_at ?? undefined,
		reviewedByName: read.reviewed_by_name ?? undefined,
		reviewNotes: read.review_notes ?? undefined,
		attachmentNames: [...(read.attachment_urls ?? [])],
	};
};

// Queue counts have no endpoint; totals per status come from three size=1
// list calls. Cached briefly so per-keystroke filter loads stay at one
// request (counts are filter-independent).
const COUNTS_TTL_MS = 30_000;
let countsCache: { at: number; value: Record<ExcuseStatus, number> } | null = null;

const fetchCounts = async (): Promise<Record<ExcuseStatus, number>> => {
	if (countsCache && Date.now() - countsCache.at < COUNTS_TTL_MS) return countsCache.value;
	const statuses: ExcuseStatus[] = ['pending', 'approved', 'rejected'];
	const settled = await Promise.all(
		statuses.map(async (status) => {
			try {
				const response = await get<Paginated<ExcuseRequestReadResponse>>('excuseList', {
					status,
					page: '1',
					size: '1',
				});
				return response.total ?? 0;
			} catch {
				return 0;
			}
		})
	);
	const value: Record<ExcuseStatus, number> = {
		pending: settled[0],
		approved: settled[1],
		rejected: settled[2],
	};
	countsCache = { at: Date.now(), value };
	return value;
};

const matches = (row: ExcuseRequest, filters: ExcuseFilters): boolean => {
	if (filters.status !== undefined && row.status !== filters.status) return false;
	if (filters.course !== undefined && filters.course !== '' && row.courseCode !== filters.course)
		return false;
	if (filters.from !== undefined && filters.from !== '' && row.sessionDate.slice(0, 10) < filters.from)
		return false;
	if (filters.to !== undefined && filters.to !== '' && row.sessionDate.slice(0, 10) > filters.to)
		return false;
	const search = (filters.search ?? '').trim().toLowerCase();
	if (search) {
		const haystack = `${row.studentName} ${row.studentNumber} ${row.courseCode} ${row.sessionCode}`.toLowerCase();
		if (!haystack.includes(search)) return false;
	}
	return true;
};

// listExcuseRequests
// Paginated, filterable queue read. Newest requests first (requestedAt desc).
// Contract: GET /professor/excuse-requests with ?status&page&size
//
// Real mode passes status/page/size through and maps + sorts the page. The
// backend filters by status only, so course/search/date narrow the returned
// page client-side (same `matches` predicate as mock mode); `total` stays the
// backend status-filtered total.
export const listExcuseRequests = async (filters: ExcuseFilters = {}): Promise<ExcuseListResult> => {
	if (isMockMode()) {
		const counts: Record<ExcuseStatus, number> = { pending: 0, approved: 0, rejected: 0 };
		for (const row of store) counts[row.status] += 1;

		const filtered = store.filter((row) => matches(row, filters)).sort((a, b) => b.requestedAt.localeCompare(a.requestedAt));

		const size = Math.min(Math.max(filters.size ?? 10, 1), 100);
		const pageCount = Math.max(1, Math.ceil(filtered.length / size));
		const page = Math.min(Math.max(filters.page ?? 1, 1), pageCount);

		return {
			items: filtered.slice((page - 1) * size, page * size),
			total: filtered.length,
			page,
			size,
			counts
		};
	}

	const query: Record<string, string> = {
		page: String(filters.page ?? 1),
		size: String(Math.min(Math.max(filters.size ?? 10, 1), 100)),
	};
	if (filters.status !== undefined) query.status = filters.status;

	const response = await get<Paginated<ExcuseRequestReadResponse>>('excuseList', query);
	const items = (response.items ?? [])
		.map(mapReadRow)
		.sort((a, b) => b.requestedAt.localeCompare(a.requestedAt))
		.filter((row) => matches(row, filters));

	return {
		items,
		total: response.total ?? items.length,
		page: response.page ?? 1,
		size: response.size ?? items.length,
		counts: await fetchCounts(),
	};
};

// reviewExcuseRequest
// Approve or reject a pending student request (Path C review).
// Reject requires review_notes (contract state-machine row); approve leaves
// notes optional.
// Contract: POST /professor/excuse-requests/{rid}/review
//
// Real mode posts the decision and maps the returned row (merging nothing —
// the row is rebuilt from the response + directory, same as list items).
// The backend owns the pending-only state machine; the client pre-checks for
// fast errors and lets server errors surface as APIError messages.
export const reviewExcuseRequest = async (
	id: number,
	input: { status: 'approved' | 'rejected'; review_notes?: string }
): Promise<ExcuseRequest> => {
	const notes = (input.review_notes ?? '').trim();
	if (input.status === 'rejected' && notes.length === 0)
		throw new Error('A rejection reason is required.');

	if (isMockMode()) {
		const index = store.findIndex((row) => row.id === id);
		if (index === -1) throw new Error('Excuse request not found.');
		const current = store[index];
		if (current.status !== 'pending') throw new Error('Only pending requests can be reviewed.');

		const updated: ExcuseRequest = {
			...current,
			status: input.status,
			reviewedAt: new Date().toISOString(),
			reviewNotes: notes.length > 0 ? notes : undefined
		};
		store[index] = updated;
		return updated;
	}

	const body: ExcuseReviewBody = { status: input.status };
	if (notes.length > 0) body.review_notes = notes;

	const read = await post<ExcuseRequestReadResponse>('excuseReview', body, undefined, `/${id}/review`);
	countsCache = null;
	return mapReadRow(read);
};

export type QuickExcuseInput = {
	studentNumber: string;
	studentName: string;
	section?: string;
	courseCode: string;
	courseName?: string;
	sessionId: number;
	sessionCode?: string;
	sessionDate?: string;
	originalStatus: ExcuseOriginalStatus;
	reason: string;
};

// quickExcuse
// Professor-initiated excuse (Path A): creates an immediately-approved row.
//
// Mock-only: typed numbers cannot resolve to the integer ids the live
// per-record routes need (no professor endpoint returns them), so live
// callers must use quickExcuseByIds (queue rows carry student_id) or
// excuseAllAbsent. Calling this outside mock mode throws instead of creating
// an in-memory row with studentId -1 that edit/revoke would later reject.
// Reason min 10 chars per excuse-workflow.md Path A modal spec. The quick
// modal collects evidence files via the D24 presigned flow; their object
// urls ride along as attachment names so the created row mirrors them.
// Contract: POST /professor/sessions/{id}/attendance/{sid}/excuse
export const quickExcuse = async (input: QuickExcuseInput & { attachmentUrls?: string[] }): Promise<ExcuseRequest> => {
	if (!isMockMode()) {
		throw new Error(
			'Quick excuse by student number is unavailable with a live backend — use the review queue row actions or Excuse all absent instead.'
		);
	}
	const reason = requireExcuseReason(input.reason);
	if (input.studentNumber.trim().length === 0) throw new Error('Student number is required.');

	const now = new Date().toISOString();
	const row: ExcuseRequest = {
		id: nextId,
		// Unknown: typed numbers cannot be resolved to integer ids without
		// backend help (see above). Edit/revoke on such rows throw a clear
		// error instead of guessing an id.
		studentId: -1,
		studentNumber: input.studentNumber.trim(),
		studentName: input.studentName.trim() || input.studentNumber.trim(),
		section: (input.section ?? '').trim() || '—',
		courseCode: input.courseCode,
		courseName: (input.courseName ?? '').trim() || input.courseCode,
		sessionId: input.sessionId,
		sessionCode: (input.sessionCode ?? '').trim() || `S-${input.sessionId}`,
		sessionDate: input.sessionDate ?? now,
		initiatedVia: 'quick' as ExcuseInitiatedVia,
		reason,
		status: 'approved',
		originalStatus: input.originalStatus,
		requestedAt: now,
		reviewedAt: now,
		attachmentNames: [...(input.attachmentUrls ?? [])]
	};
	nextId += 1;
	store = [row, ...store];
	return row;
};

// --- Per-record actions by integer id ---------------------------------------
//
// Wraps POST/PATCH/DELETE
// /professor/sessions/{sid}/attendance/{stid}/excuse plus POST
// /professor/sessions/{sid}/excuse-all-absent. Real API by default;
// in-memory mock store when PUBLIC_MOCK_MODE=true (same convention as
// list/review above). attachment_urls presence selects Path B
// (prof_with_evidence) server-side; reason-only stays Path A.

const excusePathSuffix = (sessionId: number, studentId: number): string =>
	`/${sessionId}/attendance/${studentId}/excuse`;

const requireIds = (row: { studentId: number; sessionId: number }): void => {
	if (!Number.isInteger(row.studentId) || row.studentId < 0) {
		throw new Error('This excuse has no resolvable student record — integer ids need backend support.');
	}
};

const requireReason = (reason: string): string => requireExcuseReason(reason);

// quickExcuseByIds — Path A quick-excuse (Path B with evidence when
// attachmentUrls are passed) for callers holding integer ids.
// Returns the backend action summary (the created row id + status flip).
export const quickExcuseByIds = async (
	sessionId: number,
	studentId: number,
	reason: string,
	attachmentUrls: string[] = []
): Promise<{ excuseRequestId: number; originalStatus: string | null; newStatus: string }> => {
	const clean = requireReason(reason);
	const urls = [...attachmentUrls];
	if (isMockMode()) {
		const now = new Date().toISOString();
		store = [
			{
				id: nextId,
				studentId,
				studentNumber: `#${studentId}`,
				studentName: `Student #${studentId}`,
				section: '—',
				courseCode: '—',
				courseName: '',
				sessionId,
				sessionCode: `S-${sessionId}`,
				sessionDate: now,
				initiatedVia: (urls.length > 0 ? 'prof_with_evidence' : 'quick') as ExcuseInitiatedVia,
				reason: clean,
				status: 'approved',
				originalStatus: 'unknown',
				requestedAt: now,
				reviewedAt: now,
				attachmentNames: urls
			},
			...store
		];
		nextId += 1;
		return { excuseRequestId: nextId - 1, originalStatus: null, newStatus: 'excused' };
	}

	const body: ExcuseActionBody = { reason: clean };
	if (urls.length > 0) body.attachment_urls = urls;
	const response = await post<ExcuseActionResponse>(
		'excuseQuick',
		body,
		undefined,
		excusePathSuffix(sessionId, studentId)
	);
	countsCache = null;
	return {
		excuseRequestId: response.excuse_request_id,
		originalStatus: response.original_status,
		newStatus: response.new_status
	};
};

// editExcuse — PATCH a professor-issued excuse (reason and/or review_notes,
// at least one required). Returns the updated queue row.
export const editExcuse = async (
	row: ExcuseRequest,
	input: { reason?: string; reviewNotes?: string }
): Promise<ExcuseRequest> => {
	const reason = (input.reason ?? '').trim();
	const notes = (input.reviewNotes ?? '').trim();
	if (reason.length > 0) requireExcuseReason(reason);
	else if (notes.length === 0) throw new Error('Provide a reason, review notes, or both.');

	if (isMockMode()) {
		const index = store.findIndex((item) => item.id === row.id);
		if (index === -1) throw new Error('Excuse request not found.');
		const updated: ExcuseRequest = {
			...store[index],
			reason: reason.length > 0 ? reason : store[index].reason,
			reviewNotes: notes.length > 0 ? notes : store[index].reviewNotes
		};
		store[index] = updated;
		return updated;
	}

	requireIds(row);
	const body: ExcuseEditBody = {};
	if (reason.length > 0) body.reason = reason;
	if (notes.length > 0) body.review_notes = notes;
	const read = await patch<ExcuseRequestReadResponse>(
		'excuseEdit',
		body,
		undefined,
		excusePathSuffix(row.sessionId, row.studentId)
	);
	countsCache = null;
	return mapReadRow(read);
};

// revokeExcuse — DELETE a professor-issued excuse. The backend marks the
// excuse rejected and restores attendance to original_status; returns what it
// reverted to.
export const revokeExcuse = async (row: ExcuseRequest): Promise<{ revertedTo: string | null }> => {
	if (isMockMode()) {
		const index = store.findIndex((item) => item.id === row.id);
		if (index === -1) throw new Error('Excuse request not found.');
		store[index] = { ...store[index], status: 'rejected' };
		return { revertedTo: store[index].originalStatus };
	}

	requireIds(row);
	const response = await del<ExcuseRevokeResponse>(
		'excuseRevoke',
		undefined,
		excusePathSuffix(row.sessionId, row.studentId)
	);
	countsCache = null;
	return { revertedTo: response.reverted_to };
};

// excuseAllAbsent — POST /professor/sessions/{sid}/excuse-all-absent.
// Idempotent server-side (only `absent` rows flip; re-run excuses 0).
export const excuseAllAbsent = async (
	sessionId: number,
	reason: string
): Promise<{ excusedCount: number }> => {
	const clean = requireReason(reason);
	if (isMockMode()) {
		let count = 0;
		store = store.map((item) => {
			if (item.sessionId === sessionId && item.status === 'pending' && item.originalStatus === 'absent') {
				count += 1;
				const now = new Date().toISOString();
				return { ...item, status: 'approved' as const, reviewedAt: now };
			}
			return item;
		});
		return { excusedCount: count };
	}

	const response = await post<ExcuseBulkResponse>(
		'excuseBulk',
		{ reason: clean },
		undefined,
		`/${sessionId}/excuse-all-absent`
	);
	countsCache = null;
	return { excusedCount: response.excused_count };
};

// resetExcuseStore — test/dev helper to restore fixtures after mutations.
export const resetExcuseStore = (): void => {
	store = EXCUSE_REQUESTS.map((row) => ({ ...row, attachmentNames: [...row.attachmentNames] }));
	nextId = Math.max(...store.map((row) => row.id)) + 1;
};
