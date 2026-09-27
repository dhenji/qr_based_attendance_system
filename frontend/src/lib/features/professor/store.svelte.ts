// features/professor/store.svelte.ts
// Professor self-profile state using Svelte 5 runes ($state object store).

import type { Professor, ProfessorCourseSummary } from '$lib/shared/types';
import { getProfile, listCourses } from '$lib/features/professor/service';

// Professor state
// Read-only self profile for /professor/profile, plus the course-assignment
// list for /professor/courses. Deliberately lighter than studentState — no
// dashboard, schedule, history, or scan flow lives here.
export const professorState = $state({
	professor: null as Professor | null,
	loading: false,
	error: null as string | null,
	courses: [] as ProfessorCourseSummary[],
	coursesLoading: false,
	coursesError: null as string | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

// init
// One-shot bootstrap: loads GET /professor/profile into state. A 404 means
// the signed-in user has no claimed professor row (unclaimed roster) — the
// profile page renders its empty state for that case.
export const initProfessor = async (): Promise<void> => {
	professorState.loading = true;
	professorState.error = null;
	try {
		professorState.professor = await getProfile();
	} catch (e: unknown) {
		professorState.error = toMessage(e, 'Failed to load professor data');
	} finally {
		professorState.loading = false;
	}
};

// initProfessorCourses
// One-shot bootstrap for /professor/courses: loads GET /professor/courses
// into state. A 404 means the signed-in user has no claimed professor row
// (unclaimed roster) — the page renders its empty state for that case.
export const initProfessorCourses = async (): Promise<void> => {
	professorState.coursesLoading = true;
	professorState.coursesError = null;
	try {
		professorState.courses = await listCourses();
	} catch (e: unknown) {
		professorState.coursesError = toMessage(e, 'Failed to load course assignments');
	} finally {
		professorState.coursesLoading = false;
	}
};
