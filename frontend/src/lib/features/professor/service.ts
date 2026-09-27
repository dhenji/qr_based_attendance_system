// features/professor/service.ts
// Professor-facing service: self profile.
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
// One page (size 50, the backend default) — grouping happens client-side on
// the page. `section` arrives as a string array (possibly empty), so it is
// passed through untouched and joined at render.
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
	const response = await get<Paginated<ProfessorAssignedOffering>>('professorCourses', {
		page: '1',
		size: '50',
	});
	return (response.items ?? []).map(toCourseSummary);
};
