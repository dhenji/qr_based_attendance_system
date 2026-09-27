// features/excuse/service.ts
// Professor excuse queue (mock-only, D21 Paths A/B/C).
//
// The backend excuse slice is model-only and GET /professor/excuse-requests
// has no live endpoint yet, so every function below operates on the in-memory
// copy of EXCUSE_REQUESTS. Swap to real fetch calls when the endpoints land
// and delete mock.ts with the MOCK flag.
//
// Contract refs (docs/architecture/api-contracts.md):
// - GET /professor/excuse-requests?status=&page=&size=
//   -> { items, total, page, size }
// - POST /professor/excuse-requests/{rid}/review { status, review_notes? }
//   -> { id, status, reviewed_at }
// - POST /professor/sessions/{id}/attendance/{sid}/excuse (quick-excuse)
//   -> { excuse_request_id, status: "approved", original_status, new_status }

import { EXCUSE_REQUESTS } from '$lib/features/excuse/mock';
import type {
	ExcuseInitiatedVia,
	ExcuseOriginalStatus,
	ExcuseRequest,
	ExcuseStatus
} from '$lib/shared/types/excuse';

// MOCK flag — swap to false when the backend excuse endpoints land
const MOCK = true;

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
export const listExcuseRequests = async (filters: ExcuseFilters = {}): Promise<ExcuseListResult> => {
	if (!MOCK) return { items: [], total: 0, page: 1, size: 20, counts: { pending: 0, approved: 0, rejected: 0 } };

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
};

// reviewExcuseRequest
// Approve or reject a pending student request (Path C review).
// Reject requires review_notes (contract state-machine row); approve leaves
// notes optional. Mutates the mock store so the queue + counts update.
// Contract: POST /professor/excuse-requests/{rid}/review
export const reviewExcuseRequest = async (
	id: number,
	input: { status: 'approved' | 'rejected'; review_notes?: string }
): Promise<ExcuseRequest> => {
	const index = store.findIndex((row) => row.id === id);
	if (index === -1) throw new Error('Excuse request not found.');
	const current = store[index];
	if (current.status !== 'pending') throw new Error('Only pending requests can be reviewed.');

	const notes = (input.review_notes ?? '').trim();
	if (input.status === 'rejected' && notes.length === 0)
		throw new Error('A rejection reason is required.');

	const updated: ExcuseRequest = {
		...current,
		status: input.status,
		reviewedAt: new Date().toISOString(),
		reviewNotes: notes.length > 0 ? notes : undefined
	};
	store[index] = updated;
	return updated;
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
