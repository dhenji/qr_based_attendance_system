// features/professor/store.svelte.ts
// Professor self-profile state using Svelte 5 runes ($state object store).

import type { Professor, ProfessorCourseSummary } from '$lib/shared/types';
import { getProfile, listCourses } from '$lib/features/professor/service';
import { createRequestTokenGuard } from '$lib/shared/requestToken';

// A course load that starts later always wins over an earlier one.
const coursesListGuard = createRequestTokenGuard();

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
	const token = coursesListGuard.begin();
	professorState.coursesLoading = true;
	professorState.coursesError = null;
	try {
		const courses = await listCourses();
		if (!coursesListGuard.isCurrent(token)) return;
		professorState.courses = courses;
	} catch (e: unknown) {
		if (!coursesListGuard.isCurrent(token)) return;
		professorState.coursesError = toMessage(e, 'Failed to load course assignments');
	} finally {
		if (coursesListGuard.isCurrent(token)) professorState.coursesLoading = false;
	}
};

// resetProfessorState
// Logout hygiene (doLogout): drop the profile and course-assignment list
// between logins. Without this, an A→B professor switch kept the previous
// account's courses (and ensureCourses' warm-when-empty gate never re-warmed
// them for B).
export const resetProfessorState = (): void => {
	professorState.professor = null;
	professorState.loading = false;
	professorState.error = null;
	professorState.courses = [];
	professorState.coursesLoading = false;
	professorState.coursesError = null;
};
