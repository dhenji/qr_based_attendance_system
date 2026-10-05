// features/admin/excuses/service.ts
// Admin excuse queue (read-only workload view).
//
// GET /admin/excuses?status&page&size returns the same ExcuseRequest rows as
// the professor queue. Review actions stay on the professor side; this slice
// is list-only so admins can surface pending load without duplicating the
// review state machine. Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true.

import { get } from '$lib/api/client';
import type { ExcuseRequestReadResponse, Paginated } from '$lib/api/endpoints';

export type AdminExcuseStatus = 'pending' | 'approved' | 'rejected';

export type AdminExcuseFilters = {
	status?: AdminExcuseStatus;
	page?: number;
	size?: number;
};

export const listAdminExcuses = async (
	filters: AdminExcuseFilters = {}
): Promise<Paginated<ExcuseRequestReadResponse>> => {
	const params: Record<string, string> = {
		page: String(filters.page ?? 1),
		size: String(Math.min(Math.max(filters.size ?? 20, 1), 100)),
	};
	if (filters.status) params.status = filters.status;
	return get<Paginated<ExcuseRequestReadResponse>>('adminExcuses', params);
};
