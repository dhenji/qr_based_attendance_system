// features/admin/store.svelte.ts
// Admin roster state using Svelte 5 runes ($state object store).
//
// Owns list state for /admin/students and /admin/professors: items, total,
// filters, pagination, and loading/error flags. Mutations go through the
// service and then refresh the current page, so the table never disagrees
// with the server. Mirrors professor/store.svelte.ts one-shot init style.

import type {
	AdminProfessor,
	AdminProfessorFilters,
	AdminStudent,
	AdminStudentFilters,
	AdminUser,
	AdminUserFilters,
} from '$lib/shared/types';
import {
	deactivateUser,
	hardDeleteProfessor,
	hardDeleteStudent,
	listProfessors,
	listStudents,
	listUsers,
	reactivateUser,
	setProfessorActive,
	setStudentActive,
} from '$lib/features/admin/service';
import { friendlyDeleteError, friendlyActionError } from '$lib/shared/utils/deleteErrors';
import { APIError } from '$lib/api/client';
import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
import { createRequestTokenGuard } from '$lib/shared/requestToken';

// One guard per roster: a load that starts later always wins.
const studentsListGuard = createRequestTokenGuard();
const professorsListGuard = createRequestTokenGuard();

export const adminStudentsState = $state({
	items: [] as AdminStudent[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AdminStudentFilters, 'page' | 'size'>,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

export const adminProfessorsState = $state({
	items: [] as AdminProfessor[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AdminProfessorFilters, 'page' | 'size'>,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	friendlyActionError(e, e instanceof Error && e.message ? e.message : fallback);

export const initAdminStudents = async (
	filters: AdminStudentFilters = {},
	page = 1,
	size = 20,
	opts?: { signal?: AbortSignal | null }
): Promise<void> => {
	const token = studentsListGuard.begin();
	adminStudentsState.loading = true;
	adminStudentsState.error = null;
	try {
		const result = await listStudents({ ...filters, page, size }, opts);
		if (!studentsListGuard.isCurrent(token)) return;
		adminStudentsState.items = result.items;
		adminStudentsState.total = result.total;
		adminStudentsState.page = result.page;
		adminStudentsState.size = result.size;
		adminStudentsState.filters = filters;
	} catch (e: unknown) {
		if (!studentsListGuard.isCurrent(token)) return;
		if (e instanceof APIError && e.code === 'request_cancelled') {
			// Superseded search — a newer request is provably in flight. Leave
			// the current rows alone rather than flashing an error.
			return;
		}
		// `request_timeout` is NOT a superseded search: nothing is in flight,
		// and swallowing it strands the previous rows with error = null — the
		// admin reads the page as current when the query never applied.
		adminStudentsState.error = e instanceof APIError && e.code === 'request_timeout' ? 'The request timed out. Try again.' : toMessage(e, 'Failed to load students');
	} finally {
		// Only the newest request owns the loading flag, so a stale response
		// cannot clear a spinner belonging to its successor.
		if (studentsListGuard.isCurrent(token)) adminStudentsState.loading = false;
	}
};

export const refreshAdminStudents = async (): Promise<void> => {
	await initAdminStudents(
		adminStudentsState.filters,
		adminStudentsState.page,
		adminStudentsState.size
	);
};

export const toggleStudentActive = async (student: AdminStudent): Promise<void> => {
	adminStudentsState.actionError = null;
	// Optimistic flip so the row responds instantly; the refresh after the
	// write reconciles with the server (still 1 GET on success).
	// Snapshot first: callers pass the live store row, so `row === student`
	// and reading student.isActive after mutating row would un-flip the value.
	const next = !student.isActive;
	const row = adminStudentsState.items.find((s) => s.id === student.id);
	const prev = row?.isActive;
	if (row) row.isActive = next;
	try {
		await setStudentActive(student.id, next);
		await refreshAdminStudents();
		notifyEntityChanged('students');
	} catch (e: unknown) {
		if (row && prev !== undefined) row.isActive = prev;
		// Surfaced via actionError (role=alert in the pages) — no re-throw so
		// callers use `void toggle...()` with no swallowed rejection.
		adminStudentsState.actionError = toMessage(e, 'Failed to update student status');
	}
};

export const deleteArchivedStudent = async (id: number): Promise<void> => {
	adminStudentsState.actionError = null;
	try {
		await hardDeleteStudent(id);
		// Deleting the last row on a page > 1 would leave an empty page —
		// step back first so the refresh lands on a populated one (the
		// programs/courses/offerings stores do the same).
		if (adminStudentsState.items.length === 1 && adminStudentsState.page > 1) {
			adminStudentsState.page -= 1;
		}
		await refreshAdminStudents();
		notifyEntityChanged('students');
	} catch (e: unknown) {
		adminStudentsState.actionError = friendlyDeleteError(e, 'Failed to delete student');
		throw e;
	}
};

export const initAdminProfessors = async (
	filters: AdminProfessorFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	const token = professorsListGuard.begin();
	adminProfessorsState.loading = true;
	adminProfessorsState.error = null;
	try {
		const result = await listProfessors({ ...filters, page, size });
		if (!professorsListGuard.isCurrent(token)) return;
		adminProfessorsState.items = result.items;
		adminProfessorsState.total = result.total;
		adminProfessorsState.page = result.page;
		adminProfessorsState.size = result.size;
		adminProfessorsState.filters = filters;
	} catch (e: unknown) {
		if (!professorsListGuard.isCurrent(token)) return;
		adminProfessorsState.error = toMessage(e, 'Failed to load professors');
	} finally {
		if (professorsListGuard.isCurrent(token)) adminProfessorsState.loading = false;
	}
};

export const refreshAdminProfessors = async (): Promise<void> => {
	await initAdminProfessors(
		adminProfessorsState.filters,
		adminProfessorsState.page,
		adminProfessorsState.size
	);
};

export const toggleProfessorActive = async (professor: AdminProfessor): Promise<void> => {
	adminProfessorsState.actionError = null;
	// Optimistic flip (see toggleStudentActive): instant row, 1 GET on success.
	// Snapshot first — the passed row aliases the store item.
	const next = !professor.isActive;
	const row = adminProfessorsState.items.find((p) => p.id === professor.id);
	const prev = row?.isActive;
	if (row) row.isActive = next;
	try {
		await setProfessorActive(professor.id, next);
		await refreshAdminProfessors();
		notifyEntityChanged('professors');
	} catch (e: unknown) {
		if (row && prev !== undefined) row.isActive = prev;
		// Surfaced via actionError (role=alert in the pages) — no re-throw so
		// callers use `void toggle...()` with no swallowed rejection.
		adminProfessorsState.actionError = toMessage(e, 'Failed to update professor status');
	}
};

export const deleteArchivedProfessor = async (id: number): Promise<void> => {
	adminProfessorsState.actionError = null;
	try {
		await hardDeleteProfessor(id);
		// Same last-row-on-page step-back as deleteArchivedStudent.
		if (adminProfessorsState.items.length === 1 && adminProfessorsState.page > 1) {
			adminProfessorsState.page -= 1;
		}
		await refreshAdminProfessors();
		notifyEntityChanged('professors');
	} catch (e: unknown) {
		adminProfessorsState.actionError = friendlyDeleteError(e, 'Failed to delete professor');
		throw e;
	}
};

// Admin users (super_admin only): list state for /admin/users. Create returns
// the temp password once (held by the page, not the store); deactivate and
// reactivate are symmetric PATCHes on the user's is_active flag.
export const adminUsersState = $state({
	items: [] as AdminUser[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AdminUserFilters, 'page' | 'size'>,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

// resetAdminRosterStates
// Logout hygiene (doLogout): clear the roster/user lists between logins on
// shared devices — items, filters, pagination, and any in-flight error belong
// to the signed-out session.
export const resetAdminRosterStates = (): void => {
	adminStudentsState.items = [];
	adminStudentsState.total = 0;
	adminStudentsState.page = 1;
	adminStudentsState.filters = {};
	adminStudentsState.loading = false;
	adminStudentsState.error = null;
	adminStudentsState.actionError = null;
	adminProfessorsState.items = [];
	adminProfessorsState.total = 0;
	adminProfessorsState.page = 1;
	adminProfessorsState.filters = {};
	adminProfessorsState.loading = false;
	adminProfessorsState.error = null;
	adminProfessorsState.actionError = null;
	adminUsersState.items = [];
	adminUsersState.total = 0;
	adminUsersState.page = 1;
	adminUsersState.filters = {};
	adminUsersState.loading = false;
	adminUsersState.error = null;
	adminUsersState.actionError = null;
};

export const initAdminUsers = async (
	filters: AdminUserFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminUsersState.loading = true;
	adminUsersState.error = null;
	try {
		const result = await listUsers({ ...filters, page, size });
		adminUsersState.items = result.items;
		adminUsersState.total = result.total;
		adminUsersState.page = result.page;
		adminUsersState.size = result.size;
		adminUsersState.filters = filters;
	} catch (e: unknown) {
		adminUsersState.error = toMessage(e, 'Failed to load users');
	} finally {
		adminUsersState.loading = false;
	}
};

export const refreshAdminUsers = async (): Promise<void> => {
	await initAdminUsers(adminUsersState.filters, adminUsersState.page, adminUsersState.size);
};

export const deactivateAdminUser = async (user: AdminUser): Promise<void> => {
	adminUsersState.actionError = null;
	try {
		await deactivateUser(user.id);
		await refreshAdminUsers();
		notifyEntityChanged('users');
	} catch (e: unknown) {
		adminUsersState.actionError = toMessage(e, 'Failed to deactivate user');
		throw e;
	}
};

export const reactivateAdminUser = async (user: AdminUser): Promise<void> => {
	adminUsersState.actionError = null;
	try {
		await reactivateUser(user.id);
		await refreshAdminUsers();
		notifyEntityChanged('users');
	} catch (e: unknown) {
		adminUsersState.actionError = toMessage(e, 'Failed to reactivate user');
		throw e;
	}
};
