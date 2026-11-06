// features/professor/service.ts
// Professor-facing service: self profile, course directory, dashboard summary.
//
// GET /professor/profile is fully implemented on the backend
// (professor/router.py -> ProfessorService.get_self_profile), so this talks
// to the real API by default and to ProfessorProfileEndpoint.mock only when
// PUBLIC_MOCK_MODE=true. The profile is read-only by design (D32): name,
// department and assignments are all admin-managed.
//
// Password change goes through the shared forgot-password recovery wizard
// (email → security question → emailed OTP code → strong new password),
// the same process as the student settings page.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	AdminRosterItem,
	AdminRosterItemResponse,
	Professor,
	ProfessorAssignedOffering,
	ProfessorCourseSummary,
	ProfessorDashboardResponse,
	ProfessorProfileResponse,
} from '$lib/shared/types';

// Assignment history can contain several rows for one offering (an ended
// assignment plus its replacement). The server collapses these, but pages key
// course cards by offering id, so keep a defensive dedupe here too. Prefer an
// open-ended row, then the latest effective start.
const dedupeAssignments = (
	rows: ProfessorAssignedOffering[]
): ProfessorAssignedOffering[] => {
	const byOffering = new Map<number, ProfessorAssignedOffering>();
	for (const row of rows) {
		const current = byOffering.get(row.offering_id);
		const currentRank = current
			? [current.effective_to ? 0 : 1, current.effective_from ?? '']
			: [-1, ''];
		const nextRank = [row.effective_to ? 0 : 1, row.effective_from ?? ''];
		if (
			!current ||
			nextRank[0] > currentRank[0] ||
			(nextRank[0] === currentRank[0] && nextRank[1] > currentRank[1])
		) {
			byOffering.set(row.offering_id, row);
		}
	}
	return [...byOffering.values()];
};

// Profile view-model assembled from GET /professor/profile.
const toProfessor = (p: ProfessorProfileResponse): Professor => ({
	id: p.id,
	firstName: p.first_name,
	middleName: p.middle_name ?? undefined,
	lastName: p.last_name,
	email: p.email,
	department: p.department ?? undefined,
	assignedCourses: dedupeAssignments(p.assigned_courses ?? []),
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
	programId: item.program_id ?? undefined,
	yearLevelLabel: item.year_level_label,
	yearLevelId: item.year_level_id ?? undefined,
	semester: item.semester,
	academicYear: item.academic_year,
	sections: item.section ?? [],
	isPrimary: item.is_primary,
	enrolledCount: item.enrolled_count ?? 0,
	scheduleOk: item.schedule_ok ?? true,
	// The offering's own configuration (D93) — what a session for this
	// offering inherits.
	scheduleDays: item.schedule_days ?? '',
	scheduleStartTime: item.schedule_start_time ?? null,
	scheduleEndTime: item.schedule_end_time ?? null,
	classroomName: item.classroom_name ?? null,
	classroomLat: item.classroom_lat ?? null,
	classroomLng: item.classroom_lng ?? null,
	defaultPresentWindowMinutes: item.default_present_window_minutes ?? 0,
	defaultLateWindowMinutes: item.default_late_window_minutes ?? 0,
	defaultClassroomRadiusMeters: item.default_classroom_radius_meters ?? null,
	sessionTypes: item.session_types ?? [],
	components: item.components ?? [],
	nextSessionDate: item.next_session_date ?? null,
	nextSessionStart: item.next_session_start ?? null,
	nextSessionEnd: item.next_session_end ?? null,
});

export const listCourses = async (): Promise<ProfessorCourseSummary[]> => {
	const all: ProfessorAssignedOffering[] = [];
	let page = 1;
	for (;;) {
		const response = await get<Paginated<ProfessorAssignedOffering>>('professorCourses', {
			page: String(page),
			size: '100',
		});
		for (const item of response.items ?? []) all.push(item);
		const total = response.total ?? all.length;
		if ((response.items ?? []).length < 100 || all.length >= total) break;
		page += 1;
	}
	return dedupeAssignments(all).map(toCourseSummary);
};

// GET /professor/offerings/{id}/students — enrolled roster for one offering
// the signed-in professor is assigned to. Reuses the admin roster item shape
// (student_id, name, email, section, enrolled_at).
const toProfessorRosterItem = (r: AdminRosterItemResponse): AdminRosterItem => ({
	studentId: r.student_id,
	name: r.name,
	email: r.email ?? undefined,
	section: r.section ?? undefined,
	enrolledAt: r.enrolled_at,
});

export const listOfferingStudents = async (
	offeringId: number,
	filters: { section?: string; search?: string; page?: number; size?: number } = {}
): Promise<{ items: AdminRosterItem[]; total: number; page: number; size: number }> => {
	const params: Record<string, string> = {};
	if (filters.section) params.section = filters.section;
	if (filters.search) params.search = filters.search;
	params.page = String(filters.page ?? 1);
	params.size = String(filters.size ?? 20);
	const response = await get<Paginated<AdminRosterItemResponse>>(
		'professorOfferingStudents',
		params,
		`/${offeringId}/students`
	);
	return {
		items: (response.items ?? []).map(toProfessorRosterItem),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
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
