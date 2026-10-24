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
	assignProfessor,
	reassignProfessor,
	reopenAssignment,
	bulkEnroll,
	deleteOffering,
	endAssignment,
	getOffering,
	permanentlyRemoveAssignment,
	getRoster,
	listAssignments,
	listOfferings,
	setOfferingActive,
	unenrollStudent,
	updateOffering,
} from '$lib/features/admin/offerings/service';
import type {
	AdminAssignmentCreatePayload,
	AdminAssignmentReassignPayload,
	AdminOfferingUpdatePayload,
} from '$lib/shared/types';
import { friendlyDeleteError } from '$lib/shared/utils/deleteErrors';
import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';

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

// resetAdminOfferingsStates
// Logout hygiene (doLogout): drop the list and any loaded offering detail
// (assignments + roster included).
export const resetAdminOfferingsStates = (): void => {
	adminOfferingsState.items = [];
	adminOfferingsState.total = 0;
	adminOfferingsState.page = 1;
	adminOfferingsState.filters = {};
	adminOfferingsState.loading = false;
	adminOfferingsState.error = null;
	adminOfferingsState.actionError = null;
	adminOfferingDetailState.offering = null;
	adminOfferingDetailState.assignments = [];
	adminOfferingDetailState.roster = [];
	adminOfferingDetailState.rosterTotal = 0;
	adminOfferingDetailState.rosterPage = 1;
	adminOfferingDetailState.loading = false;
	adminOfferingDetailState.assignmentsLoading = false;
	adminOfferingDetailState.rosterLoading = false;
	adminOfferingDetailState.error = null;
	adminOfferingDetailState.actionError = null;
};

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
	// Optimistic flip: instant row, 1 GET (the refresh) on success.
	// Snapshot first — the passed row aliases the store item.
	const next = !offering.isActive;
	const row = adminOfferingsState.items.find((o) => o.id === offering.id);
	const prev = row?.isActive;
	if (row) row.isActive = next;
	try {
		await setOfferingActive(offering.id, next);
		await refreshAdminOfferings();
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		if (row && prev !== undefined) row.isActive = prev;
		// Surfaced via actionError (role=alert) — no re-throw so callers use
		// `void toggle...()` with no swallowed rejection.
		adminOfferingsState.actionError = toMessage(e, 'Failed to update offering status');
	}
};

export const deleteArchivedOffering = async (id: number): Promise<void> => {
	adminOfferingsState.actionError = null;
	try {
		await deleteOffering(id);
		// Deleting the last row on a page > 1 would leave an empty page —
		// step back first so the refresh lands on a populated one.
		if (adminOfferingsState.items.length === 1 && adminOfferingsState.page > 1) {
			adminOfferingsState.page -= 1;
		}
		await refreshAdminOfferings();
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingsState.actionError = friendlyDeleteError(e, 'Failed to delete offering');
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
		notifyEntityChanged('offerings');
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
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to assign professor');
		throw e;
	}
};

export const endOfferingAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await endAssignment(offeringId, professorId, effectiveFrom);
		await loadOfferingAssignments(offeringId);
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to end assignment');
		throw e;
	}
};

export const permanentlyRemoveOfferingAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await permanentlyRemoveAssignment(offeringId, professorId, effectiveFrom);
		await loadOfferingAssignments(offeringId);
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = friendlyDeleteError(
			e,
			'Failed to permanently remove assignment'
		);
		throw e;
	}
};

export const reassignOfferingProfessor = async (
	offeringId: number,
	oldProfessorId: number,
	payload: AdminAssignmentReassignPayload
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await reassignProfessor(offeringId, oldProfessorId, payload);
		await loadOfferingAssignments(offeringId);
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to reassign professor');
		throw e;
	}
};

export const reopenOfferingAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string,
	isPrimary?: boolean
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await reopenAssignment(offeringId, professorId, effectiveFrom, isPrimary);
		await loadOfferingAssignments(offeringId);
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to reopen assignment');
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
		notifyEntityChanged('offerings');
		return result;
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Bulk enroll failed');
		throw e;
	}
};

export const unenrollStudentFromOffering = async (
	id: number,
	studentNumber: string
): Promise<void> => {
	adminOfferingDetailState.actionError = null;
	try {
		await unenrollStudent(id, studentNumber);
		await loadOfferingRoster(id);
		await refreshAdminOfferingDetail(id);
		notifyEntityChanged('offerings');
	} catch (e: unknown) {
		adminOfferingDetailState.actionError = toMessage(e, 'Failed to remove student');
		throw e;
	}
};
