// features/admin/programs/store.svelte.ts
// Program management state using Svelte 5 runes ($state object store).
//
// Two regions: the programs list (4.5a: search, status filter, pagination)
// and one loaded program detail (4.5b: program + year levels). Mutations go
// through the service and refresh, so tables never disagree with the server.
// Note the list endpoint takes no sort params — Code/Name header toggles sort
// client-side over the loaded page.

import type { Program, ProgramDetail, ProgramFilters } from '$lib/shared/types';
import {
	deleteYearLevel,
	getProgram,
	listPrograms,
	setProgramActive,
} from '$lib/features/admin/programs/service';

export type ProgramSortColumn = 'code' | 'name';

export const adminProgramsState = $state({
	items: [] as Program[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<ProgramFilters, 'page' | 'size'>,
	sortBy: 'code' as ProgramSortColumn,
	sortDir: 'asc' as 'asc' | 'desc',
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

export const adminProgramDetailState = $state({
	program: null as ProgramDetail | null,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminPrograms = async (
	filters: ProgramFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminProgramsState.loading = true;
	adminProgramsState.error = null;
	try {
		const result = await listPrograms({ ...filters, page, size });
		adminProgramsState.items = result.items;
		adminProgramsState.total = result.total;
		adminProgramsState.page = result.page;
		adminProgramsState.size = result.size;
		adminProgramsState.filters = filters;
	} catch (e: unknown) {
		adminProgramsState.error = toMessage(e, 'Failed to load programs');
	} finally {
		adminProgramsState.loading = false;
	}
};

export const refreshAdminPrograms = async (): Promise<void> => {
	await initAdminPrograms(
		adminProgramsState.filters,
		adminProgramsState.page,
		adminProgramsState.size
	);
};

export const toggleProgramActive = async (program: Program): Promise<void> => {
	adminProgramsState.actionError = null;
	try {
		await setProgramActive(program.id, !program.isActive);
		await refreshAdminPrograms();
	} catch (e: unknown) {
		// Surfaced via actionError (role=alert) — no re-throw so callers use
		// `void toggle...()` with no swallowed rejection.
		adminProgramsState.actionError = toMessage(e, 'Failed to update program status');
	}
};

export const initAdminProgramDetail = async (id: number): Promise<void> => {
	adminProgramDetailState.loading = true;
	adminProgramDetailState.error = null;
	adminProgramDetailState.program = null;
	try {
		adminProgramDetailState.program = await getProgram(id);
	} catch (e: unknown) {
		adminProgramDetailState.error = toMessage(e, 'Failed to load program');
	} finally {
		adminProgramDetailState.loading = false;
	}
};

export const refreshAdminProgramDetail = async (id: number): Promise<void> => {
	adminProgramDetailState.actionError = null;
	try {
		adminProgramDetailState.program = await getProgram(id);
	} catch (e: unknown) {
		adminProgramDetailState.actionError = toMessage(e, 'Failed to refresh program');
		throw e;
	}
};

export const deleteProgramYear = async (programId: number, yearId: number): Promise<void> => {
	adminProgramDetailState.actionError = null;
	try {
		await deleteYearLevel(programId, yearId);
		await refreshAdminProgramDetail(programId);
	} catch (e: unknown) {
		adminProgramDetailState.actionError = toMessage(e, 'Failed to delete year level');
		throw e;
	}
};
