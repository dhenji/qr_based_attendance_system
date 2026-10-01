// features/excuse/service.ts
// Professor excuse queue (D21 Paths A/B/C).
//
// Real API by default; in-memory mock only when PUBLIC_MOCK_MODE=true (see
// api/client.ts). List + review hit the live backend
// (features/excuse/professor_router.py); quick-excuse stays mock-only because
// its route needs an integer student_id in the path and no professor endpoint
// returns student ids (only numbers/names) — there is nothing to resolve a
// typed student number with, so wiring it needs backend help.
//
// The list row is deliberately bare (ids only): session/course labels join
// client-side from the session + courses directory, the same convention as
// the professor attendance ledger. Two fields have no professor-visible
// source at all and read as fallbacks in real mode: student identity
// (`Student #<id>`) and originalStatus (`unknown`).
//
// Contract refs (docs/architecture/api-contracts.md):
// - GET /professor/excuse-requests?status=&page=&size=
//   -> { items, total, page, size }
// - POST /professor/excuse-requests/{rid}/review { status, review_notes? }
//   -> { id, status, reviewed_at }
// - POST /professor/sessions/{id}/attendance/{sid}/excuse (quick-excuse)
//   -> { excuse_request_id, status: "approved", original_status, new_status }

import { EXCUSE_REQUESTS } from '$lib/features/excuse/mock';
import { get, isMockMode, post } from '$lib/api/client';
import type {
	ExcuseRequestReadResponse,
	ExcuseReviewBody,
	Paginated,
} from '$lib/api/endpoints';
import { listSessions } from '$lib/features/session/service';
import {
	initProfessorCourses,
	professorState,
} from '$lib/features/professor/store.svelte';
import type {
	ExcuseInitiatedVia,
	ExcuseOriginalStatus,
	ExcuseRequest,
	ExcuseStatus
} from '$lib/shared/types/excuse';

// Mock only when the whole app runs without a backend. Defaults to real API.
const MOCK = isMockMode();

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

// --- Real-mode joins ------------------------------------------------------
// The excuse list row carries no display identity, so session/course labels
// join client-side (attendance-ledger convention). Warmed once per page load;
// rows whose session falls outside the directory render em dashes.

type SessionDirectory = Map<
	number,
	{ offeringId: number; sessionCode: string; createdAt: string }
>;

let directoryReady = false;
let sessionDirectory: SessionDirectory = new Map();

const ensureDirectory = async (): Promise<void> => {
	if (directoryReady) return;
	directoryReady = true;
	if (professorState.courses.length === 0 && !professorState.coursesError) {
		await initProfessorCourses();
	}
	try {
		const { items } = await listSessions({ size: 100 });
		sessionDirectory = new Map(
			items.map((session) => [
				session.id,
				{
					offeringId: session.offeringId,
					sessionCode: session.sessionCode,
					createdAt: session.createdAt,
				},
			])
		);
	} catch {
		sessionDirectory = new Map();
	}
};

const courseIdentityFor = (offeringId: number): { code: string; name: string } => {
	const course = professorState.courses.find((item) => item.offeringId === offeringId) ?? null;
	return {
		code: course?.courseCode ?? `Offering ${offeringId}`,
		name: course?.courseName ?? '',
	};
};

const initiatedViaFor = (value: string): ExcuseInitiatedVia =>
	value === 'quick' || value === 'prof_with_evidence' || value === 'request'
		? value
		: 'request';

const statusFor = (value: string): ExcuseStatus =>
	value === 'pending' || value === 'approved' || value === 'rejected' ? value : 'pending';

// Map one bare backend row to the queue view-model. Student identity and the
// pre-excuse status have no professor-visible source, so they read as honest
// fallbacks rather than joined guesses.
const mapReadRow = (read: ExcuseRequestReadResponse): ExcuseRequest => {
	const session = sessionDirectory.get(read.session_id);
	const identity = session ? courseIdentityFor(session.offeringId) : null;
	return {
		id: read.id,
		studentNumber: `#${read.student_id}`,
		studentName: `Student #${read.student_id}`,
		section: '—',
		courseCode: identity?.code ?? '—',
		courseName: identity?.name ?? '',
		sessionId: read.session_id,
		sessionCode: session?.sessionCode ?? '—',
		sessionDate: session?.createdAt ?? read.requested_at,
		initiatedVia: initiatedViaFor(read.initiated_via),
		reason: read.reason,
		status: statusFor(read.status),
		originalStatus: 'unknown',
		requestedAt: read.requested_at,
		reviewedAt: read.reviewed_at ?? undefined,
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
	if (MOCK) {
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

	await ensureDirectory();

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

	if (MOCK) {
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

	await ensureDirectory();

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
// MOCK-ONLY even in real mode: the live route needs an integer student_id in
// the path and no professor endpoint returns student ids, so a typed student
// number cannot be resolved without backend help. New rows live in the
// in-memory store (visible until reload).
// Reason min 10 chars per excuse-workflow.md Path A modal spec. Path B
// (prof_with_evidence file upload) stays a TODO until S3 presigned flow (D24)
// exists — the service accepts attachment names but the page does not collect
// files yet.
// Contract: POST /professor/sessions/{id}/attendance/{sid}/excuse
export const quickExcuse = async (input: QuickExcuseInput): Promise<ExcuseRequest> => {
	const reason = input.reason.trim();
	if (reason.length < 10) throw new Error('Reason must be at least 10 characters.');
	if (input.studentNumber.trim().length === 0) throw new Error('Student number is required.');

	const now = new Date().toISOString();
	const row: ExcuseRequest = {
		id: nextId,
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
		attachmentNames: []
	};
	nextId += 1;
	store = [row, ...store];
	return row;
};

// resetExcuseStore — test/dev helper to restore fixtures after mutations.
export const resetExcuseStore = (): void => {
	store = EXCUSE_REQUESTS.map((row) => ({ ...row, attachmentNames: [...row.attachmentNames] }));
	nextId = Math.max(...store.map((row) => row.id)) + 1;
};
