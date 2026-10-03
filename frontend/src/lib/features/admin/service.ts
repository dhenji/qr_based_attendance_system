// features/admin/service.ts
// Admin roster service: students + professors CRUD backed by the live backend.
//
// Student routes live on student/admin_router.py (/api/admin/students);
// professor routes live on professor/admin_router.py (/api/admin/professors).
// Collection routes use "" on the backend (no trailing slash), so list/create
// hit the bare url and detail routes pass the id via `suffix` (e.g. `/123`,
// `/123/archive`). Real API by default; mocks only when PUBLIC_MOCK_MODE=true
// (see api/client.ts). There is deliberately no reset-password here: the
// backend mounts no such route (api-contracts lists it, routers do not), so
// the UI omits the button rather than calling a 404.

import { del, get, getText, patch, post, postForm } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import type {
	AdminOffering,
	AdminOfferingFilters,
	AdminOfferingResponse,
	AdminProfessor,
	AdminProfessorCreatePayload,
	AdminProfessorFilters,
	AdminProfessorResponse,
	AdminProfessorUpdatePayload,
	AdminStudent,
	AdminStudentCreatePayload,
	AdminStudentDetailResponse,
	AdminStudentFilters,
	AdminStudentResponse,
	AdminStudentUpdatePayload,
	AdminUser,
	AdminUserCreatePayload,
	AdminUserCreateResponse,
	AdminUserFilters,
	AdminUserResponse,
	AdminUserRole,
	ProfessorImportResult,
	StudentImportResult,
} from '$lib/shared/types';

// --- Students ---------------------------------------------------------------

const toStudent = (s: AdminStudentResponse | AdminStudentDetailResponse): AdminStudent => ({
	id: s.id,
	studentId: s.student_id,
	firstName: s.first_name,
	middleName: s.middle_name ?? undefined,
	lastName: s.last_name,
	email: s.email,
	programCode: s.program_code,
	yearLevelLabel: s.year_level_label,
	section: s.section ?? undefined,
	isActive: s.is_active,
	faceEnrolled: s.face_enrolled,
	createdAt: s.created_at,
	scanCount: s.scan_count,
	faceEnrolledAt:
		'face_enrolled_at' in s && s.face_enrolled_at ? s.face_enrolled_at : undefined,
	faceEmbeddingVersion:
		'face_embedding_version' in s ? s.face_embedding_version : undefined,
});

const studentParams = (f: AdminStudentFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.search) params.search = f.search;
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.section) params.section = f.section;
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	if (f.sort_by) params.sort_by = f.sort_by;
	if (f.sort_dir) params.sort_dir = f.sort_dir;
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listStudents = async (
	filters: AdminStudentFilters = {}
): Promise<{ items: AdminStudent[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<AdminStudentResponse>>(
		'adminStudents',
		studentParams(filters)
	);
	return {
		items: (response.items ?? []).map(toStudent),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const getStudent = async (id: number): Promise<AdminStudent> => {
	const response = await get<AdminStudentDetailResponse>(
		'adminStudentDetail',
		undefined,
		`/${id}`
	);
	return toStudent(response);
};

export const createStudent = async (
	payload: AdminStudentCreatePayload
): Promise<AdminStudent> => {
	const response = await post<AdminStudentResponse>('adminStudentCreate', payload);
	return toStudent(response);
};

export const updateStudent = async (
	id: number,
	payload: AdminStudentUpdatePayload
): Promise<AdminStudent> => {
	const response = await patch<AdminStudentResponse>(
		'adminStudentDetail',
		payload,
		undefined,
		`/${id}`
	);
	return toStudent(response);
};

// Archive toggle: PATCH with is_active (soft). Hard delete only from the
// archive screen via hardDeleteStudent below.
export const setStudentActive = async (id: number, isActive: boolean): Promise<AdminStudent> =>
	updateStudent(id, { is_active: isActive });

// Permanent delete — backend allows it only on archived (is_active=false)
// students with no enrollments/attendance/excuse records, else 409
// `student_has_records` (FKs stay RESTRICT on purpose, ADR-057).
export const hardDeleteStudent = async (id: number): Promise<void> => {
	await del<void>('adminStudentDetail', undefined, `/${id}/archive`);
};

export const importStudents = async (file: File): Promise<StudentImportResult> => {
	const form = new FormData();
	form.append('file', file);
	return postForm<StudentImportResult>('adminStudentImport', form);
};

// Roster CSV template. Server text in live mode; the static header keeps
// mock-mode/offline imports working when the template route is unreachable.
const STUDENT_TEMPLATE_FALLBACK =
	'student_id,first_name,middle_name,last_name,email,program_code,section,year_level\n';

export const downloadStudentTemplate = async (): Promise<string> => {
	try {
		return await getText('/admin/students/import/template');
	} catch {
		return STUDENT_TEMPLATE_FALLBACK;
	}
};

// --- Professors -------------------------------------------------------------

const toProfessor = (p: AdminProfessorResponse): AdminProfessor => ({
	...p,
	firstName: p.first_name,
	middleName: p.middle_name ?? undefined,
	lastName: p.last_name,
	claimStatus: p.claim_status,
	isActive: p.is_active,
	createdAt: p.created_at,
});

const professorParams = (f: AdminProfessorFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.search) params.search = f.search;
	if (f.department) params.department = f.department;
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	if (f.sort_by) params.sort_by = f.sort_by;
	if (f.sort_dir) params.sort_dir = f.sort_dir;
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listProfessors = async (
	filters: AdminProfessorFilters = {}
): Promise<{ items: AdminProfessor[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<AdminProfessorResponse>>(
		'adminProfessors',
		professorParams(filters)
	);
	return {
		items: (response.items ?? []).map(toProfessor),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const getProfessor = async (id: number): Promise<AdminProfessor> => {
	const response = await get<AdminProfessorResponse>(
		'adminProfessorDetail',
		undefined,
		`/${id}`
	);
	return toProfessor(response);
};

export const createProfessor = async (
	payload: AdminProfessorCreatePayload
): Promise<AdminProfessor> => {
	const response = await post<AdminProfessorResponse>('adminProfessorCreate', payload);
	return toProfessor(response);
};

export const updateProfessor = async (
	id: number,
	payload: AdminProfessorUpdatePayload
): Promise<AdminProfessor> => {
	const response = await patch<AdminProfessorResponse>(
		'adminProfessorDetail',
		payload,
		undefined,
		`/${id}`
	);
	return toProfessor(response);
};

export const setProfessorActive = async (id: number, isActive: boolean): Promise<AdminProfessor> =>
	updateProfessor(id, { is_active: isActive });

// Permanent delete — same archive-first + 409 `professor_has_records` guard as
// students (`sessions` is RESTRICT; `course_professors` is CASCADE).
export const hardDeleteProfessor = async (id: number): Promise<void> => {
	await del<void>('adminProfessorDetail', undefined, `/${id}/archive`);
};

export const importProfessors = async (file: File): Promise<ProfessorImportResult> => {
	const form = new FormData();
	form.append('file', file);
	return postForm<ProfessorImportResult>('adminProfessorImport', form);
};

// --- Users (super_admin only) --------------------------------------------------
//
// Wraps backend features/admin/router.py (/api/admin/users): list (search /
// role / is_active / page / size), create (201 + temp_password returned once),
// deactivate (PATCH /{id}/deactivate, 204, rejects self-deactivation).
// Collection routes use the bare url (no trailing slash); the id rides the
// `suffix`. Real API by default; mocks only when PUBLIC_MOCK_MODE=true.

export const toAdminUser = (u: AdminUserResponse | AdminUserCreateResponse): AdminUser => ({
	id: u.id,
	email: u.email,
	username: u.username ?? undefined,
	role: u.role as AdminUserRole,
	firstName: u.first_name ?? undefined,
	lastName: u.last_name ?? undefined,
	isActive: u.is_active,
	mustChangePassword: u.must_change_password,
	lastLogin: u.last_login ?? undefined,
	createdAt: u.created_at,
});

const userParams = (f: AdminUserFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.search) params.search = f.search;
	if (f.role) params.role = f.role;
	if (f.is_active !== undefined) params.is_active = String(f.is_active);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listUsers = async (
	filters: AdminUserFilters = {}
): Promise<{ items: AdminUser[]; total: number; page: number; size: number }> => {
	const response = await get<Paginated<AdminUserResponse>>('adminUsers', userParams(filters));
	return {
		items: (response.items ?? []).map(toAdminUser),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const createUser = async (
	payload: AdminUserCreatePayload
): Promise<{ user: AdminUser; tempPassword: string }> => {
	const response = await post<AdminUserCreateResponse>('adminUserCreate', payload);
	return { user: toAdminUser(response), tempPassword: response.temp_password };
};

export const deactivateUser = async (id: number): Promise<void> => {
	await patch<void>('adminUserDeactivate', undefined, undefined, `/${id}/deactivate`);
};

// --- Offerings (professor assignment picker) ---------------------------------

const toOffering = (o: AdminOfferingResponse): AdminOffering => ({
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
	classroomName: o.classroom_name ?? undefined,
	classroomLat: o.classroom_lat ?? undefined,
	classroomLng: o.classroom_lng ?? undefined,
	presentWindowMinutes: o.default_present_window_minutes,
	lateWindowMinutes: o.default_late_window_minutes,
	isActive: o.is_active,
	enrolledCount: o.enrolled_count ?? 0,
	createdAt: o.created_at,
	updatedAt: o.updated_at,
});

export const offeringLabel = (o: AdminOffering): string =>
	`Offering ${o.id} · Course ${o.courseId} · ${o.semester} ${o.academicYear}`;

export const listOfferings = async (
	filters: AdminOfferingFilters = {}
): Promise<{ items: AdminOffering[]; total: number; page: number; size: number }> => {
	const params: Record<string, string> = {};
	if (filters.program_id !== undefined) params.program_id = String(filters.program_id);
	if (filters.year_level_id !== undefined) params.year_level_id = String(filters.year_level_id);
	if (filters.semester) params.semester = filters.semester;
	if (filters.course_id !== undefined) params.course_id = String(filters.course_id);
	if (filters.is_active !== undefined) params.is_active = String(filters.is_active);
	params.page = String(filters.page ?? 1);
	params.size = String(filters.size ?? 50);
	const response = await get<Paginated<AdminOfferingResponse>>('adminOfferings', params);
	return {
		items: (response.items ?? []).map(toOffering),
		total: response.total ?? 0,
		page: response.page ?? 1,
		size: response.size ?? 50,
	};
};
