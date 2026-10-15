// features/admin/courses/service.ts
// Course-template service backed by the live backend.
//
// Routes live on course/router.py (/api/admin/courses). Collection routes use
// "" on the backend (no trailing slash), so list/create hit the bare url and
// detail/archive routes pass the id via `suffix` (e.g. `/3`). Real API by
// default; mocks only when PUBLIC_MOCK_MODE=true (see api/client.ts).
//
// A course is a standalone reusable template (D44) — no program, year-level,
// scheduling, or classroom fields. Those live on offerings
// (features/admin/offerings). The list query takes only ?is_active&page&size,
// so search + Code/Name sorts run client-side over the loaded page (same
// convention as programs).
//
// Status semantics: Deactivate/Reactivate PATCHes is_active. DELETE archives
// (soft, is_active=false, 204) — same effect, kept as a separate call so the
// UI can offer both like the students/professors slices do.

import { del, get, getText, patch, post, postForm, TEXT_EXPORTS } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	AdminCourse,
	AdminCourseCreatePayload,
	AdminCourseFilters,
	AdminCourseResponse,
	AdminCourseUpdatePayload,
	CourseImportResult,
} from '$lib/shared/types';

export const toCourse = (c: AdminCourseResponse): AdminCourse => ({
	id: c.id,
	courseCode: c.course_code,
	courseName: c.course_name,
	units: c.units,
	sessionDurationHours: c.session_duration_hours,
	// Course templates carry no type (D77) — the badge UI derives
	// Lecture/Lab/Mixed from the course's offerings instead.
	courseType: c.course_type ?? 'lecture',
	isActive: c.is_active,
	createdAt: c.created_at,
	updatedAt: c.updated_at,
});

const courseParams = (f: AdminCourseFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listCourses = async (
	filters: AdminCourseFilters = {}
): Promise<{ items: AdminCourse[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<AdminCourseResponse>>(
		'adminCourses',
		courseParams(filters)
	);
	return {
		items: (response.items ?? []).map(toCourse),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const getCourse = async (id: number): Promise<AdminCourse> => {
	const response = await get<AdminCourseResponse>(
		'adminCourseDetail',
		undefined,
		`/${id}`
	);
	return toCourse(response);
};

export const createCourse = async (
	payload: AdminCourseCreatePayload
): Promise<AdminCourse> => {
	const response = await post<AdminCourseResponse>('adminCourseCreate', {
		...payload,
		course_code: payload.course_code.trim().toUpperCase(),
	});
	return toCourse(response);
};

export const updateCourse = async (
	id: number,
	payload: AdminCourseUpdatePayload
): Promise<AdminCourse> => {
	const response = await patch<AdminCourseResponse>(
		'adminCourseDetail',
		payload.course_code !== undefined
			? { ...payload, course_code: payload.course_code.trim().toUpperCase() }
			: payload,
		undefined,
		`/${id}`
	);
	return toCourse(response);
};

export const setCourseActive = async (id: number, isActive: boolean): Promise<AdminCourse> =>
	updateCourse(id, { is_active: isActive });

// Soft archive — 204, flips is_active=false server-side.
export const archiveCourse = async (id: number): Promise<void> => {
	await del<void>('adminCourseDetail', undefined, `/${id}`);
};

export const importCourses = async (file: File): Promise<CourseImportResult> => {
	const form = new FormData();
	form.append('file', file);
	return postForm<CourseImportResult>('adminCourseImport', form);
};

// CSV template. Server text in live mode; the static header keeps
// mock-mode/offline imports working when the template route is unreachable.
const COURSE_TEMPLATE_FALLBACK = 'course_code,course_name,units,session_duration_hours\n';

export const downloadCourseTemplate = async (): Promise<string> => {
	try {
		return await getText(TEXT_EXPORTS.courseTemplate);
	} catch {
		return COURSE_TEMPLATE_FALLBACK;
	}
};
