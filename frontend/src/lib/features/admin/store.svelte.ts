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
	setProfessorActive,
	setStudentActive,
} from '$lib/features/admin/service';

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
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminStudents = async (
	filters: AdminStudentFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminStudentsState.loading = true;
	adminStudentsState.error = null;
	try {
		const result = await listStudents({ ...filters, page, size });
		adminStudentsState.items = result.items;
		adminStudentsState.total = result.total;
		adminStudentsState.page = result.page;
		adminStudentsState.size = result.size;
		adminStudentsState.filters = filters;
	} catch (e: unknown) {
		adminStudentsState.error = toMessage(e, 'Failed to load students');
	} finally {
		adminStudentsState.loading = false;
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
	try {
		await setStudentActive(student.id, !student.isActive);
		await refreshAdminStudents();
	} catch (e: unknown) {
		// Surfaced via actionError (role=alert in the pages) — no re-throw so
		// callers use `void toggle...()` with no swallowed rejection.
		adminStudentsState.actionError = toMessage(e, 'Failed to update student status');
	}
};

export const deleteArchivedStudent = async (id: number): Promise<void> => {
	adminStudentsState.actionError = null;
	try {
		await hardDeleteStudent(id);
		await refreshAdminStudents();
	} catch (e: unknown) {
		adminStudentsState.actionError = toMessage(e, 'Failed to delete student');
		throw e;
	}
};

export const initAdminProfessors = async (
	filters: AdminProfessorFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminProfessorsState.loading = true;
	adminProfessorsState.error = null;
	try {
		const result = await listProfessors({ ...filters, page, size });
		adminProfessorsState.items = result.items;
		adminProfessorsState.total = result.total;
		adminProfessorsState.page = result.page;
		adminProfessorsState.size = result.size;
		adminProfessorsState.filters = filters;
	} catch (e: unknown) {
		adminProfessorsState.error = toMessage(e, 'Failed to load professors');
	} finally {
		adminProfessorsState.loading = false;
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
	try {
		await setProfessorActive(professor.id, !professor.isActive);
		await refreshAdminProfessors();
	} catch (e: unknown) {
		// Surfaced via actionError (role=alert in the pages) — no re-throw so
		// callers use `void toggle...()` with no swallowed rejection.
		adminProfessorsState.actionError = toMessage(e, 'Failed to update professor status');
	}
};

export const deleteArchivedProfessor = async (id: number): Promise<void> => {
	adminProfessorsState.actionError = null;
	try {
		await hardDeleteProfessor(id);
		await refreshAdminProfessors();
	} catch (e: unknown) {
		adminProfessorsState.actionError = toMessage(e, 'Failed to delete professor');
		throw e;
	}
};

// Admin users (super_admin only): list state for /admin/users. Create returns
// the temp password once (held by the page, not the store); deactivate is
// one-way — the backend mounts no reactivate route.
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
	} catch (e: unknown) {
		adminUsersState.actionError = toMessage(e, 'Failed to deactivate user');
		throw e;
	}
};
