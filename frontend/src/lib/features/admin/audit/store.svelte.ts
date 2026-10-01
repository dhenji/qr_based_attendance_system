// features/admin/audit/store.svelte.ts
// Admin audit-log state using Svelte 5 runes ($state object store).
//
// Two regions: the merged action feed (live record-creation rows + mock
// operational rows, newest first) and the academic-structure changes list
// (D38). The feed endpoint takes no sort params, so Time/User/Action header
// toggles sort client-side over the loaded page (same convention as courses).

import type {
	AuditLogFilters,
	StructureChangeResponse,
} from '$lib/shared/types';
import {
	listAuditLogs,
	listStructureChanges,
	type AuditLogRow,
} from '$lib/features/admin/audit/service';

export type AuditSortColumn = 'time' | 'user' | 'action';

export const adminAuditState = $state({
	items: [] as AuditLogRow[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AuditLogFilters, 'page' | 'size'>,
	sortBy: 'time' as AuditSortColumn,
	sortDir: 'desc' as 'asc' | 'desc',
	loading: false,
	error: null as string | null,
});

export const adminStructureState = $state({
	items: [] as StructureChangeResponse[],
	loading: false,
	error: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminAudit = async (
	filters: AuditLogFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminAuditState.loading = true;
	adminAuditState.error = null;
	try {
		const result = await listAuditLogs(filters, page, size);
		adminAuditState.items = result.items;
		adminAuditState.total = result.total;
		adminAuditState.page = result.page;
		adminAuditState.size = result.size;
		adminAuditState.filters = filters;
	} catch (e: unknown) {
		adminAuditState.error = toMessage(e, 'Failed to load audit logs');
	} finally {
		adminAuditState.loading = false;
	}
};

export const refreshAdminAudit = async (): Promise<void> => {
	await initAdminAudit(
		adminAuditState.filters,
		adminAuditState.page,
		adminAuditState.size
	);
};

export const initStructureChanges = async (): Promise<void> => {
	adminStructureState.loading = true;
	adminStructureState.error = null;
	try {
		adminStructureState.items = await listStructureChanges();
	} catch (e: unknown) {
		adminStructureState.error = toMessage(e, 'Failed to load structure changes');
	} finally {
		adminStructureState.loading = false;
	}
};

export type { AuditLogRow };
