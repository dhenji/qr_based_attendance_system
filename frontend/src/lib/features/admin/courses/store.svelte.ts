// features/admin/courses/store.svelte.ts
// Course-template management state using Svelte 5 runes ($state object store).
//
// Two regions: the templates list (search, status filter, pagination) and one
// loaded template detail. Mutations go through the service and refresh, so
// tables never disagree with the server. The list endpoint takes no search or
// sort params — search + Code/Name header toggles sort client-side over the
// loaded page (same convention as programs).

import type { AdminCourse, AdminCourseFilters } from '$lib/shared/types';
import {
	archiveCourse,
	getCourse,
	listCourses,
	setCourseActive,
} from '$lib/features/admin/courses/service';

export type CourseSortColumn = 'code' | 'name';

export const adminCoursesState = $state({
	items: [] as AdminCourse[],
	total: 0,
	page: 1,
	size: 20,
	filters: {} as Omit<AdminCourseFilters, 'page' | 'size'>,
	sortBy: 'code' as CourseSortColumn,
	sortDir: 'asc' as 'asc' | 'desc',
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

export const adminCourseDetailState = $state({
	course: null as AdminCourse | null,
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const initAdminCourses = async (
	filters: AdminCourseFilters = {},
	page = 1,
	size = 20
): Promise<void> => {
	adminCoursesState.loading = true;
	adminCoursesState.error = null;
	try {
		const result = await listCourses({ ...filters, page, size });
		adminCoursesState.items = result.items;
		adminCoursesState.total = result.total;
		adminCoursesState.page = result.page;
		adminCoursesState.size = result.size;
		adminCoursesState.filters = filters;
	} catch (e: unknown) {
		adminCoursesState.error = toMessage(e, 'Failed to load courses');
	} finally {
		adminCoursesState.loading = false;
	}
};

export const refreshAdminCourses = async (): Promise<void> => {
	await initAdminCourses(
		adminCoursesState.filters,
		adminCoursesState.page,
		adminCoursesState.size
	);
};

export const toggleCourseActive = async (course: AdminCourse): Promise<void> => {
	adminCoursesState.actionError = null;
	try {
		await setCourseActive(course.id, !course.isActive);
		await refreshAdminCourses();
	} catch (e: unknown) {
		// Surfaced via actionError (role=alert) — no re-throw so callers use
		// `void toggle...()` with no swallowed rejection.
		adminCoursesState.actionError = toMessage(e, 'Failed to update course status');
	}
};

export const archiveAdminCourse = async (course: AdminCourse): Promise<void> => {
	adminCoursesState.actionError = null;
	try {
		await archiveCourse(course.id);
		await refreshAdminCourses();
	} catch (e: unknown) {
		adminCoursesState.actionError = toMessage(e, 'Failed to archive course');
		throw e;
	}
};

export const initAdminCourseDetail = async (id: number): Promise<void> => {
	adminCourseDetailState.loading = true;
	adminCourseDetailState.error = null;
	adminCourseDetailState.course = null;
	try {
		adminCourseDetailState.course = await getCourse(id);
	} catch (e: unknown) {
		adminCourseDetailState.error = toMessage(e, 'Failed to load course');
	} finally {
		adminCourseDetailState.loading = false;
	}
};

export const refreshAdminCourseDetail = async (id: number): Promise<void> => {
	adminCourseDetailState.actionError = null;
	try {
		adminCourseDetailState.course = await getCourse(id);
	} catch (e: unknown) {
		adminCourseDetailState.actionError = toMessage(e, 'Failed to refresh course');
		throw e;
	}
};
