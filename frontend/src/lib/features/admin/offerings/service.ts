// features/admin/offerings/service.ts
// Course-offering service backed by the live backend.
//
// Routes live on course/offering_router.py (/api/admin/offerings).
// Collection routes use "" on the backend (no trailing slash), so list/create
// hit the bare url and detail/sub-resource routes pass path segments via
// `suffix` (e.g. `/3`, `/3/professors`, `/3/professors/12`, `/3/students`,
// `/3/enrollments/bulk`). Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true (see api/client.ts).
//
// An offering is a program/year/semester instance of a course template (D44)
// and holds the scheduling, classroom, and window configuration. Identity
// fields (course_id, program_id, year_level_id, semester, academic_year) are
// set at creation and are NOT patchable — PATCH rejects them server-side.
// The read contract carries ids only, so course/program/year display names
// are joined client-side (see enrichOfferings); the professor assignment
// picker in features/admin/service.ts already reads this list endpoint.
//
// Professor assignment rules (D7-D9): many-to-many via course_professors with
// is_primary, effective_from, effective_to (null = ongoing), semester.
// Ending an assignment sets effective_to=today (history is never rewritten).
// Bulk enroll attaches EXISTING students via CSV upload (same columns as the
// student import template); creating new students stays on
// POST /admin/students/import.

import { del, get, patch, post, postForm } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	AdminAssignment,
	AdminAssignmentCreatePayload,
	AdminAssignmentReassignPayload,
	AdminAssignmentReopenPayload,
	AdminAssignmentResponse,
	AdminBulkEnrollResult,
	AdminCourse,
	AdminOffering,
	AdminOfferingCreatePayload,
	AdminOfferingFilters,
	AdminOfferingResponse,
	AdminOfferingUpdatePayload,
	AdminRosterFilters,
	AdminRosterItem,
	AdminRosterItemResponse,
	AdminStudent,
	OfferingComponent,
	OfferingComponentCreatePayload,
	OfferingComponentResponse,
	OfferingComponentUpdatePayload,
	Program,
	YearLevel,
} from '$lib/shared/types';

export const toComponent = (c: OfferingComponentResponse): OfferingComponent => ({
	id: c.id,
	offeringId: c.offering_id,
	sessionType: c.session_type,
	scheduleDays: c.schedule_days,
	scheduleStartTime: c.schedule_start_time,
	scheduleEndTime: c.schedule_end_time,
	classroomName: c.classroom_name ?? undefined,
	classroomLat: c.classroom_lat ?? undefined,
	classroomLng: c.classroom_lng ?? undefined,
	isActive: c.is_active,
	createdAt: c.created_at,
	updatedAt: c.updated_at,
});

export const toOffering = (o: AdminOfferingResponse): AdminOffering => {
	const components = (o.components ?? []).map(toComponent);
	// Live reads carry the distinct active types; fall back to the legacy
	// label (then lecture) for rows that predate the field.
	const sessionTypes =
		o.session_types && o.session_types.length > 0
			? [...o.session_types]
			: [o.course_type ?? 'lecture'];
	return {
		id: o.id,
		courseId: o.course_id,
		programId: o.program_id,
		yearLevelId: o.year_level_id,
		semester: o.semester,
		academicYear: o.academic_year,
		sessionsPerWeek: o.sessions_per_week,
		semesterWeeks: o.semester_weeks,
		scheduleDays: o.schedule_days,
		scheduleStartTime: o.schedule_start_time,
		scheduleEndTime: o.schedule_end_time,
		courseType: sessionTypes[0] ?? 'lecture',
		sessionTypes,
		components,
		classroomName: o.classroom_name ?? undefined,
		classroomLat: o.classroom_lat ?? undefined,
		classroomLng: o.classroom_lng ?? undefined,
		presentWindowMinutes: o.default_present_window_minutes,
		lateWindowMinutes: o.default_late_window_minutes,
		// D93: null means "inherit the app setting" (Admin -> System
		// Settings -> Geofence radius).
		defaultClassroomRadiusMeters: o.default_classroom_radius_meters ?? null,
		isActive: o.is_active,
		enrolledCount: o.enrolled_count ?? 0,
		createdAt: o.created_at,
		updatedAt: o.updated_at,
	};
};

// Client-side joins for display: the OfferingRead contract carries ids only.
// Looks up course/program/year metadata already loaded for the filter
// dropdowns, so no extra requests are needed.
export const enrichOfferings = (
	items: AdminOffering[],
	courses: AdminCourse[],
	programs: Program[],
	years: YearLevel[]
): AdminOffering[] => {
	const courseById = new Map(courses.map((c) => [c.id, c]));
	const programById = new Map(programs.map((p) => [p.id, p]));
	const yearById = new Map(years.map((y) => [y.id, y]));
	return items.map((o) => ({
		...o,
		courseCode: courseById.get(o.courseId)?.courseCode,
		courseName: courseById.get(o.courseId)?.courseName,
		programCode: programById.get(o.programId)?.code,
		yearLevelLabel: yearById.get(o.yearLevelId)?.label,
	}));
};

// 409 rescue for `offering_exists`: the unique key is
// (course_id, program_id, semester, academic_year) — the year level does not
// disambiguate — so the conflicting row may sit under a different year level
// than the one the admin is looking at. The list endpoint has no
// academic-year filter, so match it client-side from a narrow page.
export interface OfferingConflictQuery {
	course_id: number;
	program_id: number;
	semester: string;
	academic_year: string;
}

export const findConflictingOffering = async (
	query: OfferingConflictQuery
): Promise<AdminOffering | null> => {
	const { items } = await listOfferings({
		course_id: query.course_id,
		program_id: query.program_id,
		semester: query.semester,
		size: 50,
	});
	const wantYear = query.academic_year.trim().toLowerCase();
	return (
		items.find((o) => o.academicYear.trim().toLowerCase() === wantYear) ?? null
	);
};

// Display title for an offering row. Prefers joined names, falls back to ids
// (same fallback the professor assignment picker uses).
export const offeringTitle = (o: AdminOffering): string => {
	const course = o.courseCode ?? `Course ${o.courseId}`;
	const cohort = [o.programCode, o.yearLevelLabel].filter(Boolean).join(' · ');
	const when = `${o.semester} ${o.academicYear}`;
	return [course, cohort, when].filter(Boolean).join(' · ');
};

const offeringParams = (f: AdminOfferingFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	if (f.course_id !== undefined) params.course_id = String(f.course_id);
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listOfferings = async (
	filters: AdminOfferingFilters = {}
): Promise<{ items: AdminOffering[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<AdminOfferingResponse>>(
		'adminOfferings',
		offeringParams(filters)
	);
	return {
		items: (response.items ?? []).map(toOffering),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const getOffering = async (id: number): Promise<AdminOffering> => {
	const response = await get<AdminOfferingResponse>(
		'adminOfferingDetail',
		undefined,
		`/${id}`
	);
	return toOffering(response);
};

export const createOffering = async (
	payload: AdminOfferingCreatePayload
): Promise<AdminOffering> => {
	const response = await post<AdminOfferingResponse>('adminOfferingCreate', {
		...payload,
		schedule_days: payload.schedule_days.trim().toUpperCase(),
	});
	return toOffering(response);
};

export const updateOffering = async (
	id: number,
	payload: AdminOfferingUpdatePayload
): Promise<AdminOffering> => {
	const response = await patch<AdminOfferingResponse>(
		'adminOfferingDetail',
		payload.schedule_days !== undefined
			? { ...payload, schedule_days: payload.schedule_days.trim().toUpperCase() }
			: payload,
		undefined,
		`/${id}`
	);
	return toOffering(response);
};

export const setOfferingActive = async (id: number, isActive: boolean): Promise<AdminOffering> =>
	updateOffering(id, { is_active: isActive });

// Permanent delete — 409 `not_archived` when still active,
// `offering_has_enrollments` / `offering_has_sessions` /
// `offering_has_assignments` when dependents remain. Archive via PATCH,
// like programs.
export const deleteOffering = async (id: number): Promise<void> => {
	await del<void>('adminOfferingDetail', undefined, `/${id}`);
};

// --- Offering components (D77: per-type schedules) -------------------------


export const listComponents = async (offeringId: number): Promise<OfferingComponent[]> => {
	const response = await get<OfferingComponentResponse[]>(
		'adminOfferingComponents',
		undefined,
		`/${offeringId}/components`
	);
	return (response ?? []).map(toComponent);
};

export const createComponent = async (
	offeringId: number,
	payload: OfferingComponentCreatePayload
): Promise<OfferingComponent> => {
	const response = await post<OfferingComponentResponse>(
		'adminOfferingComponentCreate',
		{
			...payload,
			schedule_days: payload.schedule_days.trim().toUpperCase(),
		},
		undefined,
		`/${offeringId}/components`
	);
	return toComponent(response);
};

export const updateComponent = async (
	offeringId: number,
	componentId: number,
	payload: OfferingComponentUpdatePayload
): Promise<OfferingComponent> => {
	const response = await patch<OfferingComponentResponse>(
		'adminOfferingComponentDetail',
		payload.schedule_days !== undefined
			? { ...payload, schedule_days: payload.schedule_days.trim().toUpperCase() }
			: payload,
		undefined,
		`/${offeringId}/components/${componentId}`
	);
	return toComponent(response);
};

// Soft archive — 204, flips is_active=false server-side.
export const archiveComponent = async (
	offeringId: number,
	componentId: number
): Promise<void> => {
	await del<void>(
		'adminOfferingComponentDetail',
		undefined,
		`/${offeringId}/components/${componentId}`
	);
};

// --- Professor assignments ---------------------------------------------------

const toAssignment = (a: AdminAssignmentResponse): AdminAssignment => ({
	offeringId: a.offering_id,
	professorId: a.professor_id,
	isPrimary: a.is_primary,
	effectiveFrom: a.effective_from,
	effectiveTo: a.effective_to ?? undefined,
	semester: a.semester,
	hasSessions: Boolean(a.has_sessions),
	assignedBy: a.assigned_by,
	assignedAt: a.assigned_at,
});

export const listAssignments = async (offeringId: number): Promise<AdminAssignment[]> => {
	const response = await get<AdminAssignmentResponse[] | AdminAssignmentResponse>(
		'adminOfferingProfessors',
		undefined,
		`/${offeringId}/professors`
	);
	const rows = Array.isArray(response) ? response : [response];
	return rows.map(toAssignment);
};

export const assignProfessor = async (
	offeringId: number,
	payload: AdminAssignmentCreatePayload
): Promise<AdminAssignment> => {
	const response = await post<AdminAssignmentResponse>(
		'adminOfferingProfessors',
		payload,
		undefined,
		`/${offeringId}/professors`
	);
	return toAssignment(response);
};

// End an assignment — sets effective_to=today server-side and returns it.
export const endAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string
): Promise<string> => {
	const response = await del<{ effective_to: string }>(
		'adminOfferingProfessors',
		{ effective_from: effectiveFrom },
		`/${offeringId}/professors/${professorId}`
	);
	return response.effective_to;
};

// Permanently erase an assignment that never opened a session. The backend
// returns 409 assignment_has_sessions for rows with history, so End must be
// used instead.
export const permanentlyRemoveAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string
): Promise<void> => {
	await del<void>(
		'adminOfferingProfessors',
		{ effective_from: effectiveFrom },
		`/${offeringId}/professors/${professorId}/permanent`
	);
};

// Replace a professor on an offering — ends the old assignment and opens a
// new one in one transaction.
export const reassignProfessor = async (
	offeringId: number,
	oldProfessorId: number,
	payload: AdminAssignmentReassignPayload
): Promise<AdminAssignment> => {
	const response = await post<AdminAssignmentResponse>(
		'adminOfferingProfessors',
		payload,
		undefined,
		`/${offeringId}/professors/${oldProfessorId}/reassign`
	);
	return toAssignment(response);
};

// Undo an accidental End by clearing the exact row's effective_to. Passing
// isPrimary=false reopens a former primary as an assistant when another
// primary already covers the dates; omitting it restores the previous role.
export const reopenAssignment = async (
	offeringId: number,
	professorId: number,
	effectiveFrom: string,
	isPrimary?: boolean
): Promise<AdminAssignment> => {
	const payload: AdminAssignmentReopenPayload = {
		effective_from: effectiveFrom,
	};
	if (isPrimary !== undefined) payload.is_primary = isPrimary;

	const response = await post<AdminAssignmentResponse>(
		'adminOfferingProfessors',
		payload,
		undefined,
		`/${offeringId}/professors/${professorId}/reopen`
	);
	return toAssignment(response);
};

// --- Roster + bulk enroll ----------------------------------------------------

const toRosterItem = (r: AdminRosterItemResponse): AdminRosterItem => ({
	studentId: r.student_id,
	name: r.name,
	section: r.section ?? undefined,
	enrolledAt: r.enrolled_at,
});

export const getRoster = async (
	offeringId: number,
	filters: AdminRosterFilters = {}
): Promise<{ items: AdminRosterItem[]; total: number; page: number; size: number }> => {
	const params: Record<string, string> = {};
	if (filters.section) params.section = filters.section;
	params.page = String(filters.page ?? 1);
	params.size = String(filters.size ?? 20);
	const response = await get<Paginated<AdminRosterItemResponse>>(
		'adminOfferingRoster',
		params,
		`/${offeringId}/students`
	);
	return {
		items: (response.items ?? []).map(toRosterItem),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const bulkEnroll = async (
	offeringId: number,
	file: File
): Promise<AdminBulkEnrollResult> => {
	const form = new FormData();
	form.append('file', file);
	return postForm<AdminBulkEnrollResult>(
		'adminOfferingBulkEnroll',
		form,
		undefined,
		`/${offeringId}/enrollments/bulk`
	);
};

// Bulk-enroll CSV built in the browser for the Add-student modal: the same
// validated upload as a file, so manual adds inherit the email/program checks,
// the per-row dedupe (already-enrolled → skipped), and a single audit row for
// the whole batch. `section` stays blank on purpose — a value would overwrite
// the student's section for every offering they are in, not just this one.
// Rows are emitted in the caller's order so a reported error line can be mapped
// back to the student at that index (the parser numbers data rows from line 2).
const ENROLL_CSV_HEADER =
	'student_id,first_name,middle_name,last_name,email,program_code,year_level,section';

const csvCell = (value: string | undefined): string => {
	const text = value ?? '';
	return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export const buildEnrollCsv = (students: AdminStudent[]): File => {
	const rows = students.map((student) =>
		[
			student.studentId,
			student.firstName,
			student.middleName ?? '',
			student.lastName,
			student.email,
			student.programCode,
			student.yearLevelLabel,
			'',
		]
			.map(csvCell)
			.join(',')
	);
	return new File([`${ENROLL_CSV_HEADER}\n${rows.join('\n')}\n`], 'enroll.csv', {
		type: 'text/csv',
	});
};

// Unenroll one student — 204, link row only. `studentNumber` is the roster
// string id (e.g. "24-2111"), matching the Enrolled tab row key.
export const unenrollStudent = async (
	offeringId: number,
	studentNumber: string
): Promise<void> => {
	await del<void>(
		'adminOfferingUnenroll',
		undefined,
		`/${offeringId}/students/${encodeURIComponent(studentNumber)}`
	);
};
