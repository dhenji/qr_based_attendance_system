// features/professor/service.ts
// Professor-facing service: self profile, course directory, dashboard summary.
//
// GET /professor/profile is fully implemented on the backend
// (professor/router.py -> ProfessorService.get_self_profile), so this talks
// to the real API by default and to ProfessorProfileEndpoint.mock only when
// PUBLIC_MOCK_MODE=true. The profile is read-only by design (D32): name,
// department and assignments are all admin-managed.
//
// Password change is NOT owned here — the settings page reuses
// auth/store.svelte.ts doChangePassword (POST /auth/change-password), which
// calls the same auth_service.change_password logic as
// PATCH /professor/profile/password.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	Professor,
	ProfessorAssignedOffering,
	ProfessorCourseSummary,
	ProfessorDashboardResponse,
	ProfessorProfileResponse,
} from '$lib/shared/types';

// Profile view-model assembled from GET /professor/profile.
const toProfessor = (p: ProfessorProfileResponse): Professor => ({
	id: p.id,
	firstName: p.first_name,
	middleName: p.middle_name ?? undefined,
	lastName: p.last_name,
	email: p.email,
	department: p.department ?? undefined,
	assignedCourses: p.assigned_courses ?? [],
	claimStatus: p.claim_status,
	createdAt: p.created_at,
	sessionCount: p.session_count,
});

export const getProfile = async (): Promise<Professor | null> => {
	const response = await get<ProfessorProfileResponse>('professorProfile');
	return toProfessor(response);
};

// Own active course assignments from GET /professor/courses.
//
// Paged to exhaustion (size 100 is the server max) so professors with many
// assignments never truncate — grouping happens client-side on the page.
// `section` arrives as a string array (possibly empty), so it is passed
// through untouched and joined at render.
const toCourseSummary = (item: ProfessorAssignedOffering): ProfessorCourseSummary => ({
	offeringId: item.offering_id,
	courseId: item.course_id,
	courseCode: item.course_code,
	courseName: item.course_name,
	units: item.units ?? 0,
	programCode: item.program_code,
	yearLevelLabel: item.year_level_label,
	semester: item.semester,
	academicYear: item.academic_year,
	sections: item.section ?? [],
	isPrimary: item.is_primary,
	enrolledCount: item.enrolled_count ?? 0,
});

export const listCourses = async (): Promise<ProfessorCourseSummary[]> => {
	const all: ProfessorCourseSummary[] = [];
	let page = 1;
	for (;;) {
		const response = await get<Paginated<ProfessorAssignedOffering>>('professorCourses', {
			page: String(page),
			size: '100',
		});
		for (const item of response.items ?? []) all.push(toCourseSummary(item));
		const total = response.total ?? all.length;
		if ((response.items ?? []).length < 100 || all.length >= total) break;
		page += 1;
	}
	return all;
};

// GET /professor/dashboard — today's session counts, the enrolled roster, and
// the term-wide compliance headline, in one call.
//
// The session tiles carry no course identity, so the dashboard page still lists
// today's sessions through GET /professor/sessions for the code/name/section
// columns and joins these counts on `session_id`. Same convention as the
// professor attendance ledger.
export const getDashboard = async (): Promise<ProfessorDashboardResponse> =>
	get<ProfessorDashboardResponse>('professorDashboard');
