// features/admin/audit/store.svelte.ts
// Admin audit-log state using Svelte 5 runes ($state object store).
//
// Two regions: the merged action feed (audit-trail rows from
// GET /admin/audit-logs + record-creation rows derived from roster created_at,
// newest first) and the academic-structure changes list (D38).
//
// The name lookups live in a lazy resolver rather than in the page, because
// they are shared by both tabs and they should be fetched once, not once per
// render. Which rosters are needed depends on the rows on screen, so the
// resolver is asked for exactly those (see `labels.ts`).

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
import {
	AuditLabelResolver,
	neededLabelKinds,
} from '$lib/features/admin/audit/labels';
import { listCourses } from '$lib/features/admin/courses/service';
import { listOfferings } from '$lib/features/admin/offerings/service';
import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
import { listProfessors, listStudents, listUsers } from '$lib/features/admin/service';
import { isSuperAdmin } from '$lib/features/auth/store.svelte';

// The server caps a page at 200 rows (`shared/pagination.py::MAX_PAGE_SIZE`).
// A larger roster than that leaves the name map incomplete, which the UI
// says out loud rather than showing a partial map as if it were whole.
const LABEL_PAGE_SIZE = 200;

const labelResolver = new AuditLabelResolver({
	programs: async () => {
		const res = await listPrograms({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
	yearLevels: async (programId) => {
		const res = await listYearLevels(programId);
		return { items: res, total: res.length };
	},
	courses: async () => {
		const res = await listCourses({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
	students: async () => {
		const res = await listStudents({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
	professors: async () => {
		const res = await listProfessors({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
	offerings: async () => {
		const res = await listOfferings({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
	users: async () => {
		const res = await listUsers({ page: 1, size: LABEL_PAGE_SIZE });
		return { items: res.items, total: res.total };
	},
});

export type AuditSortColumn = 'time' | 'user' | 'action';

export const adminAuditState = $state({
	/** Every merged row the feed holds, newest first. */
	all: [] as AuditLogRow[],
	total: 0,
	/** The server's own count for the filtered audit trail. */
	trailTotal: 0,
	/** How many trail rows were actually fetched (the page-size cap). */
	trailLoaded: 0,
	/** Derived roster rows in this feed — an inference, not an audited event. */
	rosterCount: 0,
	/** True when the derived rows hit their scan cap, so the count is partial. */
	rosterTruncated: false,
	page: 1,
	size: 20,
	filters: {} as Omit<AuditLogFilters, 'page' | 'size'>,
	sortBy: 'time' as AuditSortColumn,
	sortDir: 'desc' as 'asc' | 'desc',
	loading: false,
	error: null as string | null,
	/** True when the users map is available, so actor names can be resolved. */
	actorNamesAvailable: false,
	/** True when at least one roster was too large to load in full. */
	labelsPartial: false,
	/**
	 * Bumped whenever the name lookups change.
	 *
	 * The lookups live in a plain (non-reactive) resolver, so a derived that
	 * reads them would not know to recompute. Reading this counter is the
	 * dependency that makes it do so.
	 */
	labelVersion: 0,
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

/**
 * Fetch the lookups the given rows need, once each.
 *
 * The users map is only reachable by a super-admin
 * (`backend/src/features/admin/router.py:37` guards `GET /admin/users` with
 * `require_role(SUPER_ADMIN)`), so a plain admin never attempts it and
 * instead sees "User #<id>" for the account rows. The account snapshot
 * deliberately carries no email, so there is nothing to read from the row
 * itself.
 */
export const ensureAuditLabels = async (rows: AuditLogRow[]): Promise<void> => {
	const kinds = neededLabelKinds(rows);
	adminAuditState.actorNamesAvailable = isSuperAdmin();
	// The users map is the actor filter's source as well as the actor
	// label's, so a super-admin loads it whether or not the current page
	// happens to contain an account row.
	if (adminAuditState.actorNamesAvailable) kinds.add('users');
	else kinds.delete('users');
	await labelResolver.ensure(kinds);
	// Sticky: once a roster has been seen to be larger than the page the
	// resolver can load, the name map is incomplete for the rest of the
	// session, and the UI keeps saying so.
	adminAuditState.labelsPartial =
		adminAuditState.labelsPartial ||
		[...kinds].some((kind) => labelResolver.isPartial(kind));
	adminAuditState.labelVersion += 1;
};

export const auditLabelContext = () => labelResolver.context();

export const initAdminAudit = async (
	filters: AuditLogFilters = {},
	page = 1
): Promise<void> => {
	adminAuditState.loading = true;
	adminAuditState.error = null;
	try {
		const result: AuditFeed = await listAuditLogs(filters);
		adminAuditState.all = result.all;
		adminAuditState.total = result.total;
		adminAuditState.trailTotal = result.trailTotal;
		adminAuditState.trailLoaded = result.trailLoaded;
		adminAuditState.rosterCount = result.rosterCount;
		adminAuditState.rosterTruncated = result.rosterTruncated;
		adminAuditState.page = page;
		adminAuditState.filters = filters;
		await ensureAuditLabels(result.all);
	} catch (e: unknown) {
		adminAuditState.error = toMessage(e, 'Failed to load audit logs');
	} finally {
		adminAuditState.loading = false;
	}
};

export const refreshAdminAudit = async (): Promise<void> => {
	await initAdminAudit(adminAuditState.filters, adminAuditState.page);
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
		await ensureAuditLabels(
			result.items.map((row) => ({ ...row, origin: 'trail' as const }))
		);
	} catch (e: unknown) {
		adminStructureState.error = toMessage(e, 'Failed to load structure changes');
	} finally {
		adminStructureState.loading = false;
	}
};

export type { AuditLogRow };
