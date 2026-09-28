// api/endpoints.ts
// Typed endpoint map mirroring backend API contracts
// (from docs/architecture/api-contracts.md)
//
// Urls are relative to /api — the api client prepends that prefix. `mock` is
// optional and only consulted when PUBLIC_MOCK_MODE=true.

import type {
	MeResponse,
	TokenResponse,
} from '$lib/shared/types';
import type {
	StudentDashboardResponse,
	StudentProfileResponse,
} from '$lib/shared/types';
import type {
	AdminProfessorResponse,
	AdminStudentDetailResponse,
	AdminStudentResponse,
	ProfessorImportResult,
	StudentImportResult,
} from '$lib/shared/types';
import type { ProfessorProfileResponse } from '$lib/shared/types';
import type { ProfessorAssignedOffering } from '$lib/shared/types';
import type {
	ProfessorAttendanceItemResponse,
	SessionActiveResponse,
	SessionCloseResponse,
	SessionHistoryItemResponse,
	SessionListItemResponse,
	SessionReadResponse,
} from '$lib/shared/types';

export type ScanStatus = 'present' | 'late' | 'rejected';

export interface SessionVerificationResponse {
	session_id: number;
	offering_id: number;
	course_code: string;
	course_name: string;
	program_code: string;
	year_level_label: string;
	expires_at: string;
	scheduled_end_time: string;
	geofence: { radius: number; lat: number; lng: number };
	present_window_minutes: number;
	late_window_minutes: number;
}

export interface AttendanceScanResponse {
	id: number;
	status: ScanStatus;
	scanned_at: string;
	expires_at: string;
}

// Shared shape for the paginated collection endpoints.
export interface Paginated<T> {
	items: T[];
	total: number;
	page: number;
	size: number;
}

export interface EndpointDef<T> {
	url: string;
	method: 'GET' | 'POST' | 'PUT' | 'DELETE';
	mock?: () => T;
}

// Session QR payload (D18)
export const SessionQREndpoint: EndpointDef<SessionVerificationResponse> = {
	url: '/student/sessions/verify-code',
	method: 'POST',
	mock: () => ({
		session_id: 1,
		offering_id: 1,
		course_code: 'CS101',
		course_name: 'Software Engineering 1',
		program_code: 'BSCS',
		year_level_label: 'Year 1',
		expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		geofence: {
			radius: 50,
			lat: 13.7563,
			lng: 100.5018,
		},
		present_window_minutes: 15,
		late_window_minutes: 5,
	}),
};

// Attendance scan (D18)
export const AttendanceScanEndpoint: EndpointDef<AttendanceScanResponse> = {
	url: '/student/attendance/scan',
	method: 'POST',
	mock: () => ({
		id: 1,
		status: 'present',
		scanned_at: new Date().toISOString(),
		expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
	}),
};

// Session CRUD (professor) — real routes on features/session/router.py.
//
// The live QR payload keys the offering as `offering` (backend QRPayload);
// course display names are joined client-side from GET /professor/courses.
export const SessionListEndpoint: EndpointDef<Paginated<SessionListItemResponse>> = {
	url: '/professor/sessions',
	method: 'GET',
	mock: () => ({
		items: [
			{
				id: 1,
				offering_id: 1,
				session_code: '7X-9K2M',
				created_at: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
				expires_at: new Date(Date.now() + 40 * 60 * 1000).toISOString(),
				duration_minutes: 60,
				present_count: 15,
				late_count: 3,
				absent_count: 2,
				status: 'active',
			},
		],
		total: 1,
		page: 1,
		size: 20,
	}),
};

export const SessionCreateEndpoint: EndpointDef<SessionReadResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: () => ({
		id: Math.floor(Math.random() * 1000) + 1,
		session_code: `A${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
		offering_id: 1,
		qr_payload: {
			v: 1,
			code: `A${Math.random().toString(36).substring(2, 4).toUpperCase()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
			offering: 1,
			radius: 50,
			pw: 15,
			lw: 5,
		},
		expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		created_at: new Date().toISOString(),
	}),
};

// Session history (professor) — wireframe 3.5, GET /professor/sessions/history.
// Rates ride the rows; averages are derived client-side (the envelope carries
// items/total/page/size only).
export const SessionHistoryEndpoint: EndpointDef<Paginated<SessionHistoryItemResponse>> = {
	url: '/professor/sessions/history',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

// Live session detail (professor projector view).
// The session id rides the path: GET /professor/sessions/active/{id} —
// callers pass it via the client's `suffix` option.
// Poll-friendly: unscanned students read as absent server-side.
export const SessionActiveEndpoint: EndpointDef<SessionActiveResponse> = {
	url: '/professor/sessions/active',
	method: 'GET',
	mock: () => ({
		id: 1,
		offering: 1,
		session_code: '7X-9K2M',
		scan_window_remaining: 2400,
		scheduled_end_time: new Date(Date.now() + 40 * 60 * 1000).toISOString(),
		status: 'active',
		enrolled_count: 30,
		remaining: 12,
		pending_sync_count: 0,
		students: [],
		counts: { present: 15, late: 3, pending: 10, absent: 2, excused: 0 },
	}),
};

// Close session (professor).
// The session id rides the path: POST /professor/sessions/{id}/close —
// callers pass it via the client's `suffix` option.
export const SessionCloseEndpoint: EndpointDef<SessionCloseResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: () => ({ id: 0, status: 'closed' as const, final_counts: { present: 0, late: 0, pending: 0, absent: 0, excused: 0 } }),
};

// Attendance records (professor) — GET /professor/attendance.
// Filtered by course_id/offering_id (not course code); course display names
// join client-side from GET /professor/courses.
export const AttendanceListEndpoint: EndpointDef<Paginated<ProfessorAttendanceItemResponse>> = {
	url: '/professor/attendance',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
	}),
};

// --- Auth -------------------------------------------------------------------
//
// The backend's TokenResponse carries no user object; identity always comes
// from GET /auth/me. Mock mode fills in a test-data student (24-0001).

const MOCK_TOKENS: TokenResponse = {
	access_token: 'mock-access-token',
	refresh_token: 'mock-refresh-token',
	mfa_pending: false,
	preauth_token: null,
	must_change_password: false,
};

export const AuthOtpRequestEndpoint: EndpointDef<void> = {
	url: '/auth/otp/request',
	method: 'POST',
	mock: () => undefined,
};

export const AuthOtpVerifyEndpoint: EndpointDef<void> = {
	url: '/auth/otp/verify',
	method: 'POST',
	mock: () => undefined,
};

export const AuthRegisterEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/register',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthLoginEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/login',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthRefreshEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/refresh',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthMeEndpoint: EndpointDef<MeResponse> = {
	url: '/auth/me',
	method: 'GET',
	mock: () => ({
		id: 1,
		role: 'student',
		first_name: 'Jose',
		last_name: 'Rizal',
		email: 'jose.rizal@isu.edu.ph',
		mfa_enabled: false,
		security_question_set: true,
		must_change_password: false,
		last_login: null,
		face_enrolled: false,
		face_enrolled_at: null,
		face_embedding_version: 0,
		claim_status: null,
	}),
};

export const AuthMfaVerifyEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/mfa/verify',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthChangePasswordEndpoint: EndpointDef<void> = {
	url: '/auth/change-password',
	method: 'POST',
	mock: () => undefined,
};

// --- Student ----------------------------------------------------------------

export const StudentProfileEndpoint: EndpointDef<StudentProfileResponse> = {
	url: '/student/profile',
	method: 'GET',
	mock: () => ({
		student_number: '24-0001',
		first_name: 'Jose',
		middle_name: null,
		last_name: 'Rizal',
		email: 'jose.rizal@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '1st Year',
		section: 'A',
		is_active: true,
		face_enrolled: false,
		face_enrolled_at: null,
		face_embedding_version: 0,
		created_at: new Date().toISOString(),
		scan_count: 0,
	}),
};

export const StudentDashboardEndpoint: EndpointDef<StudentDashboardResponse> = {
	url: '/student/dashboard',
	method: 'GET',
	mock: () => ({
		compliance_rate: 0,
		scans_today: 0,
		total_scans: 0,
		today_schedule: [],
		recent_activity: [],
	}),
};

// --- Professor --------------------------------------------------------------
//
// GET /professor/profile is fully implemented on the backend
// (professor/router.py -> ProfessorService.get_self_profile). Password change
// reuses POST /auth/change-password (authChangePassword above) — it calls the
// same auth_service.change_password logic as PATCH /professor/profile/password,
// so no separate endpoint def is needed.

export const ProfessorProfileEndpoint: EndpointDef<ProfessorProfileResponse> = {
	url: '/professor/profile',
	method: 'GET',
	mock: () => ({
		id: 1,
		first_name: 'John',
		middle_name: 'A',
		last_name: 'Smith',
		email: 'john.smith@isu.edu.ph',
		department: 'Computer Science',
		assigned_courses: [
			{
				offering_id: 1,
				course_id: 1,
				course_code: 'CS101',
				course_name: 'Software Engineering 1',
				program_code: 'BSCS',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['A'],
				is_primary: true,
				enrolled_count: 30,
			},
			{
				offering_id: 2,
				course_id: 2,
				course_code: 'MATH202',
				course_name: 'Calculus 2',
				program_code: 'BSCS',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['A'],
				is_primary: true,
				enrolled_count: 35,
			},
			{
				offering_id: 3,
				course_id: 1,
				course_code: 'CS101',
				course_name: 'Software Engineering 1',
				program_code: 'BSIT',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['B'],
				is_primary: false,
				enrolled_count: 25,
			},
		],
		claim_status: 'Claimed',
		created_at: new Date().toISOString(),
		session_count: 87,
	}),
};

// GET /professor/courses — own active assignments, paginated. The wire rows
// carry no schedule clock-times, classroom, or window defaults (those columns
// live on courses/offerings per D44, not on the assignment), so cards render
// those slots as TBA until the contract grows them.
export const ProfessorCoursesEndpoint: EndpointDef<Paginated<ProfessorAssignedOffering>> = {
	url: '/professor/courses',
	method: 'GET',
	mock: () => ({
		items: [
			{
				offering_id: 1,
				course_id: 1,
				course_code: 'CS101',
				course_name: 'Software Engineering 1',
				program_code: 'BSCS',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['A'],
				is_primary: true,
				enrolled_count: 30,
				units: 3,
			},
			{
				offering_id: 2,
				course_id: 2,
				course_code: 'MATH202',
				course_name: 'Calculus 2',
				program_code: 'BSCS',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['A'],
				is_primary: true,
				enrolled_count: 35,
				units: 4,
			},
			{
				offering_id: 3,
				course_id: 1,
				course_code: 'CS101',
				course_name: 'Software Engineering 1',
				program_code: 'BSIT',
				year_level_label: '1st Year',
				semester: '1st Sem',
				academic_year: '2025-2026',
				section: ['B'],
				is_primary: false,
				enrolled_count: 25,
				units: 3,
			},
		],
		total: 3,
		page: 1,
		size: 50,
	}),
};

// --- Admin (Phase 3 MVP: students + professors) -------------------------------
//
// Live routes on student/admin_router.py and professor/admin_router.py.
// Collection routes use "" on the backend (no trailing slash), so callers must
// not append "/" — list/create hit the bare url, detail routes pass the id via
// the client's `suffix` option (e.g. `/123`, `/123/archive`, `/import`).

const MOCK_ADMIN_STUDENTS: Paginated<AdminStudentResponse> = {
	items: [
		{
			id: 1,
			student_id: '2021-001',
			first_name: 'Alice',
			middle_name: 'M',
			last_name: 'Santos',
			email: 'alice.santos@isu.edu.ph',
			program_code: 'BSCS',
			year_level_label: '3rd Year',
			section: 'A',
			is_active: true,
			face_enrolled: true,
			created_at: new Date().toISOString(),
			scan_count: 42,
		},
		{
			id: 2,
			student_id: '2022-002',
			first_name: 'Bob',
			middle_name: null,
			last_name: 'Cruz',
			email: 'bob.cruz@isu.edu.ph',
			program_code: 'BSIT',
			year_level_label: '2nd Year',
			section: 'B',
			is_active: true,
			face_enrolled: false,
			created_at: new Date().toISOString(),
			scan_count: 18,
		},
	],
	total: 2,
	page: 1,
	size: 20,
};

export const AdminStudentsEndpoint: EndpointDef<Paginated<AdminStudentResponse>> = {
	url: '/admin/students',
	method: 'GET',
	mock: () => MOCK_ADMIN_STUDENTS,
};

export const AdminStudentCreateEndpoint: EndpointDef<AdminStudentResponse> = {
	url: '/admin/students',
	method: 'POST',
	mock: () => MOCK_ADMIN_STUDENTS.items[0],
};

export const AdminStudentDetailEndpoint: EndpointDef<AdminStudentDetailResponse> = {
	url: '/admin/students',
	method: 'GET',
	mock: () => ({ ...MOCK_ADMIN_STUDENTS.items[0], face_enrolled_at: null, face_embedding_version: 1 }),
};

export const AdminStudentImportEndpoint: EndpointDef<StudentImportResult> = {
	url: '/admin/students/import',
	method: 'POST',
	mock: () => ({ imported: 25, duplicates: 0, errors: [] }),
};

const MOCK_ADMIN_PROFESSORS: Paginated<AdminProfessorResponse> = {
	items: [
		{
			id: 1,
			first_name: 'John',
			middle_name: 'A',
			last_name: 'Smith',
			email: 'john.smith@isu.edu.ph',
			department: 'Computer Science',
			is_active: true,
			claim_status: 'Claimed',
			assigned_courses: [{ offering_id: 1, course_code: 'CS101' }],
			created_at: new Date().toISOString(),
		},
		{
			id: 2,
			first_name: 'Maria',
			middle_name: null,
			last_name: 'Garcia',
			email: 'maria.garcia@isu.edu.ph',
			department: 'Mathematics',
			is_active: true,
			claim_status: 'Unclaimed',
			assigned_courses: [],
			created_at: new Date().toISOString(),
		},
	],
	total: 2,
	page: 1,
	size: 20,
};

export const AdminProfessorsEndpoint: EndpointDef<Paginated<AdminProfessorResponse>> = {
	url: '/admin/professors',
	method: 'GET',
	mock: () => MOCK_ADMIN_PROFESSORS,
};

export const AdminProfessorCreateEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'POST',
	mock: () => MOCK_ADMIN_PROFESSORS.items[0],
};

export const AdminProfessorDetailEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'GET',
	mock: () => MOCK_ADMIN_PROFESSORS.items[0],
};

export const AdminProfessorImportEndpoint: EndpointDef<ProfessorImportResult> = {
	url: '/admin/professors/import',
	method: 'POST',
	mock: () => ({ imported: 5, duplicates: 0, errors: [] }),
};

// Endpoint registry
// Named, strongly-typed endpoint definitions keyed for the apiCall() layer.
export const endpoints = {
	// Session QR
	sessionQR: SessionQREndpoint,
	// Attendance scan
	attendanceScan: AttendanceScanEndpoint,
	// Session CRUD
	sessionList: SessionListEndpoint,
	sessionCreate: SessionCreateEndpoint,
	sessionHistory: SessionHistoryEndpoint,
	sessionActive: SessionActiveEndpoint,
	sessionClose: SessionCloseEndpoint,
	// Attendance
	attendanceList: AttendanceListEndpoint,
	// Auth
	authOtpRequest: AuthOtpRequestEndpoint,
	authOtpVerify: AuthOtpVerifyEndpoint,
	authRegister: AuthRegisterEndpoint,
	authLogin: AuthLoginEndpoint,
	authRefresh: AuthRefreshEndpoint,
	authMe: AuthMeEndpoint,
	authMfaVerify: AuthMfaVerifyEndpoint,
	authChangePassword: AuthChangePasswordEndpoint,
	// Student
	studentProfile: StudentProfileEndpoint,
	studentDashboard: StudentDashboardEndpoint,
	// Professor
	professorProfile: ProfessorProfileEndpoint,
	professorCourses: ProfessorCoursesEndpoint,
	// Admin (students + professors)
	adminStudents: AdminStudentsEndpoint,
	adminStudentCreate: AdminStudentCreateEndpoint,
	adminStudentDetail: AdminStudentDetailEndpoint,
	adminStudentImport: AdminStudentImportEndpoint,
	adminProfessors: AdminProfessorsEndpoint,
	adminProfessorCreate: AdminProfessorCreateEndpoint,
	adminProfessorDetail: AdminProfessorDetailEndpoint,
	adminProfessorImport: AdminProfessorImportEndpoint,
};
