// features/admin/offerings/store.svelte.ts
// Course-offering management state using Svelte 5 runes ($state object store).
//
// Two regions: the offerings list (full cascade filters + pagination) and one
// loaded offering detail (offering + professor assignments + roster).
// Mutations go through the service and refresh, so tables never disagree with
// the server. The list endpoint takes no search/sort params, so filtering is
// server-side via the cascade and any text narrowing sorts client-side over
// the loaded page.

import type {
	AdminAssignment,
	AdminOffering,
	AdminOfferingFilters,
	AdminRosterItem,
} from '$lib/shared/types';
import {
	archiveOffering,
	assignProfessor,
	bulkEnroll,
	endAssignment,
	getOffering,
	getRoster,
	listAssignments,
	listOfferings,
	setOfferingActive,
	updateOffering,
} from '$lib/features/admin/offerings/service';
import type {
	AdminAssignmentCreatePayload,
	AdminOfferingUpdatePayload,
} from '$lib/shared/types';

export const adminOfferingsState = $state({
	items: [] as AdminOffering[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AdminOfferingFilters, 'page' | 'size'>,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

export const adminOfferingDetailState = $state({
	offering: null as AdminOffering | null,
	assignments: [] as AdminAssignment[],
	roster: [] as AdminRosterItem[],
	rosterTotal: 0,
	rosterPage: 1,
	loading: false,
	assignmentsLoading: false,
	rosterLoading: false,
	error: null as string | null,
	actionError: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminOfferings = async (
	filters: AdminOfferingFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminOfferingsState.loading = true;
	adminOfferingsState.error = null;
	try {
		const result = await listOfferings({ ...filters, page, size });
		adminOfferingsState.items = result.items;
		adminOfferingsState.total = result.total;
		adminOfferingsState.page = result.page;
		adminOfferingsState.size = result.size;
		adminOfferingsState.filters = filters;
	} catch (e: unknown) {
		adminOfferingsState.error = toMessage(e, 'Failed to load offerings');
	} finally {
		adminOfferingsState.loading = false;
	}
};

export const refreshAdminOfferings = async (): Promise<void> => {
	await initAdminOfferings(
		adminOfferingsState.filters,
		adminOfferingsState.page,
		adminOfferingsState.size
	);
};

export const toggleOfferingActive = async (offering: AdminOffering): Promise<void> => {
	adminOfferingsState.actionError = null;
	try {
		await setOfferingActive(offering.id, !offering.isActive);
		await refreshAdminOfferings();
	} catch (e: unknown) {
		// Surfaced via actionError (role=alert) — no re-throw so callers use
		// `void toggle...()` with no swallowed rejection.
		adminOfferingsState.actionError = toMessage(e, 'Failed to update offering status');
	}
};

export const archiveAdminOffering = async (offering: AdminOffering): Promise<void> => {
	adminOfferingsState.actionError = null;
	try {
		await archiveOffering(offering.id);
		await refreshAdminOfferings();
	} catch (e: unknown) {
		adminOfferingsState.actionError = toMessage(e, 'Failed to archive offering');
		throw e;
	}
};

export const initAdminOfferingDetail = async (id: number): Promise<void> => {
	adminOfferingDetailState.loading = true;
	adminOfferingDetailState.error = null;
	adminOfferingDetailState.offering = null;
	adminOfferingDetailState.assignments = [];
	adminOfferingDetailState.roster = [];
	try {
		adminOfferingDetailState.offering = await getOffering(id);
	} catch (e: unknown) {
		adminOfferingDetailState.error = toMessage(e, 'Failed to load offering');
	} finally {
		adminOfferingDetailState.loading = false;
	}
};

export const refreshAdminOfferingDetail = async (id: number): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		adminOfferingDetailState.offering = await getOffering(id);
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to refresh offering');
		throw e;
	}
};

export const updateAdminOffering = async (
	id: number,
	payload: AdminOfferingUpdatePayload
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		adminOfferingDetailState.offering = await updateOffering(id, payload);
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to update offering');
		throw e;
	}
};

export const loadOfferingAssignments = async (id: number): Promise<void> => {
	adminOfferingDetailState.assignmentsLoading = true;
	try {
		adminOfferingDetailState.assignments = await listAssignments(id);
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to load assignments');
	} finally {
		adminOfferingDetailState.assignmentsLoading = false;
	}
};

export const assignOfferingProfessor = async (
	id: number,
	payload: AdminAssignmentCreatePayload
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await assignProfessor(id, payload);
		await loadOfferingAssignments(id);
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to assign professor');
		throw e;
	}
};

export const endOfferingAssignment = async (
	offeringId: number,
	professorId: number
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await endAssignment(offeringId, professorId);
		await loadOfferingAssignments(offeringId);
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to end assignment');
		throw e;
	}
};

export const loadOfferingRoster = async (
	id: number,
	section?: string,
	page = 1,
	size = 20
): Promise<void> => {
	adminOfferingDetailState.rosterLoading = true;
	try {
		const result = await getRoster(id, { section, page, size });
		adminOfferingDetailState.roster = result.items;
		adminOfferingDetailState.rosterTotal = result.total;
		adminOfferingDetailState.rosterPage = result.page;
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to load roster');
	} finally {
		adminOfferingDetailState.rosterLoading = false;
	}
};

export const bulkEnrollOffering = async (id: number, file: File) => {
	adminOfferingDetailState.actionError = null;
	try {
		const result = await bulkEnroll(id, file);
		await loadOfferingRoster(id);
		await refreshAdminOfferingDetail(id);
		return result;
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Bulk enroll failed');
		throw e;
	}
};
