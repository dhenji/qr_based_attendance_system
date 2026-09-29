// features/admin/programs/service.ts
// Program + year-level service backed by the live backend.
//
// Routes live on program/router.py (/api/admin/programs). Collection routes
// use "" on the backend (no trailing slash), so list/create hit the bare url
// and detail/year routes pass path segments via `suffix` (e.g. `/3`,
// `/3/years`, `/3/years/12`). Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true (see api/client.ts).
//
// Archive semantics (ADR-058): DELETE /admin/programs/{id} flips
// is_active=false on the program row ONLY — year_levels has no is_active
// column and courses carries no program FK, so there is nothing to cascade
// to. Year-level DELETE is a real delete that 409s when offerings reference
// the row (`year_has_courses`).

import { del, get, patch, post } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	Program,
	ProgramCreatePayload,
	ProgramDetail,
	ProgramDetailResponse,
	ProgramFilters,
	ProgramResponse,
	ProgramTerm,
	ProgramUpdatePayload,
	YearLevel,
	YearLevelCreatePayload,
	YearLevelResponse,
	YearLevelUpdatePayload,
} from '$lib/shared/types';

const toProgram = (p: ProgramResponse | ProgramDetailResponse): Program => ({
	id: p.id,
	code: p.code,
	name: p.name,
	description: p.description ?? undefined,
	totalYears: p.total_years,
	isActive: p.is_active,
	courseCount: p.course_count,
	yearLevelCount: p.year_level_count,
	termsCount: p.terms_count,
	createdAt: p.created_at,
	updatedAt: p.updated_at,
});

const toYearLevel = (y: YearLevelResponse): YearLevel => ({
	id: y.id,
	programId: y.program_id,
	yearNumber: y.year_number,
	label: y.label,
	terms: (y.term_structure?.terms ?? []).map((t: ProgramTerm) => ({
		code: t.code,
		label: t.label,
	})),
	sortOrder: y.sort_order,
});

const programParams = (f: ProgramFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.search) params.search = f.search;
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listPrograms = async (
	filters: ProgramFilters = {}
): Promise<{ items: Program[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<ProgramResponse>>(
		'adminPrograms',
		programParams(filters)
	);
	return {
		items: (response.items ?? []).map(toProgram),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const getProgram = async (id: number): Promise<ProgramDetail> => {
	const response = await get<ProgramDetailResponse>(
		'adminProgramDetail',
		undefined,
		`/${id}`
	);
	return {
		...toProgram(response),
		yearLevels: (response.year_levels ?? []).map(toYearLevel),
	};
};

export const createProgram = async (payload: ProgramCreatePayload): Promise<Program> => {
	const response = await post<ProgramResponse>('adminProgramCreate', {
		...payload,
		code: payload.code.trim().toUpperCase(),
	});
	return toProgram(response);
};

export const updateProgram = async (
	id: number,
	payload: ProgramUpdatePayload
): Promise<Program> => {
	const response = await patch<ProgramResponse>(
		'adminProgramDetail',
		payload,
		undefined,
		`/${id}`
	);
	return toProgram(response);
};

export const setProgramActive = async (id: number, isActive: boolean): Promise<Program> =>
	updateProgram(id, { is_active: isActive });

// Archive: soft-deactivate via is_active. Reactivate with
// setProgramActive(id, true). No cascade by design (ADR-058).
export const archiveProgram = async (id: number): Promise<void> => {
	await del<void>('adminProgramDetail', undefined, `/${id}`);
};

export const listYearLevels = async (programId: number): Promise<YearLevel[]> => {
	const response = await get<Paginated<YearLevelResponse>>(
		'adminYearLevels',
		{ page: '1', size: '50' },
		`/${programId}/years`
	);
	return (response.items ?? []).map(toYearLevel);
};

export const createYearLevel = async (
	programId: number,
	payload: YearLevelCreatePayload
): Promise<YearLevel> => {
	const response = await post<YearLevelResponse>(
		'adminYearLevelDetail',
		payload,
		undefined,
		`/${programId}/years`
	);
	return toYearLevel(response);
};

export const updateYearLevel = async (
	programId: number,
	yearId: number,
	payload: YearLevelUpdatePayload
): Promise<YearLevel> => {
	const response = await patch<YearLevelResponse>(
		'adminYearLevelDetail',
		payload,
		undefined,
		`/${programId}/years/${yearId}`
	);
	return toYearLevel(response);
};

// Hard delete — 409 `year_has_courses` when offerings still reference the row.
export const deleteYearLevel = async (programId: number, yearId: number): Promise<void> => {
	await del<void>('adminYearLevelDetail', undefined, `/${programId}/years/${yearId}`);
};
