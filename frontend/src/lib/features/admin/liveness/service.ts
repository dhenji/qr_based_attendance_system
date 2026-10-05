// features/admin/liveness/service.ts
// Admin liveness-review queue (flagged-scan human review).
//
// GET /admin/attendance/liveness-review?status&page&size lists records whose
// face_match_score fell in the review band with validation_status pending;
// PATCH /admin/attendance/liveness-review/{id}/resolve approves (restores
// present/late) or rejects them. Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true.

import { get, patch } from '$lib/api/client';
import type {
	LivenessReviewItemResponse,
	LivenessReviewResolveBody,
	LivenessReviewResolveResponse,
	Paginated,
} from '$lib/api/endpoints';

export type LivenessStatus = 'pending' | 'approved' | 'rejected';

export type LivenessReviewFilters = {
	status?: LivenessStatus;
	page?: number;
	size?: number;
};

export const listLivenessReview = async (
	filters: LivenessReviewFilters = {}
): Promise<Paginated<LivenessReviewItemResponse>> => {
	const params: Record<string, string> = {
		status: filters.status ?? 'pending',
		page: String(filters.page ?? 1),
		size: String(Math.min(Math.max(filters.size ?? 20, 1), 100)),
	};
	return get<Paginated<LivenessReviewItemResponse>>('livenessReviewList', params);
};

export const resolveLivenessReview = async (
	id: number,
	decision: 'approve' | 'reject',
	note?: string
): Promise<LivenessReviewResolveResponse> => {
	const clean = (note ?? '').trim();
	const body: LivenessReviewResolveBody = { decision };
	if (clean.length > 0) body.note = clean.slice(0, 1000);
	return patch<LivenessReviewResolveResponse>('livenessReviewResolve', body, undefined, `/${id}/resolve`);
};
