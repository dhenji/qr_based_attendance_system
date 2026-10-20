// features/admin/audit/store.svelte.ts
// Admin audit-log state using Svelte 5 runes ($state object store).
//
// Two regions: the action feed (GET /admin/audit-logs) and the
// academic-structure changes list (GET /admin/system/academic-structure).
//
// Both are server-paged and server-sorted, so a page is a page of the
// whole trail rather than a slice of what happens to be loaded. There is no
// local merge and no local inference: the trail is what the server recorded.

import type {
	AuditLogFilters,
	StructureChangeResponse,
} from '$lib/shared/types';
import {
	listAuditLogs,
	listStructureChanges,
	type AuditFeed,
	type AuditLogRow,
} from '$lib/features/admin/audit/service';

export type AuditSortColumn = 'time' | 'actor' | 'action';

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
	total: 0,
	page: 1,
	size: 20,
	loading: false,
	error: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminAudit = async (
	filters: AuditLogFilters = {},
	page = 1
): Promise<void> => {
	adminAuditState.loading = true;
	adminAuditState.error = null;
	try {
		const result: AuditFeed = await listAuditLogs({
			...filters,
			page,
			size: adminAuditState.size,
		});
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
		{
			...adminAuditState.filters,
			sort_by: adminAuditState.sortBy,
			sort_dir: adminAuditState.sortDir,
		},
		adminAuditState.page
	);
};

export const initStructureChanges = async (
	page = 1,
	size = 20
): Promise<void> => {
	adminStructureState.loading = true;
	adminStructureState.error = null;
	try {
		const result = await listStructureChanges({ page, size });
		adminStructureState.items = result.items;
		adminStructureState.total = result.total;
		adminStructureState.page = result.page;
		adminStructureState.size = result.size;
	} catch (e: unknown) {
		adminStructureState.error = toMessage(e, 'Failed to load structure changes');
	} finally {
		adminStructureState.loading = false;
	}
};

export type { AuditLogRow };
