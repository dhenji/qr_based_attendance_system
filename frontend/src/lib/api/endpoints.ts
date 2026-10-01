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
import type {
	ProgramDetailResponse,
	ProgramResponse,
	YearLevelResponse,
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
	// Mocks receive the same inputs as the real call so stateful fixtures
	// (e.g. admin roster CRUD) can read path ids from `suffix` and payloads
	// from `body`, and branch on `method` when one def serves several verbs.
	mock?: (
		params?: Record<string, string>,
		suffix?: string,
		body?: unknown,
		method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
	) => T;
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
		email: 'jose.p.rizal@isu.edu.ph',
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
		email: 'jose.p.rizal@isu.edu.ph',
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

export type StudentHistoryStatus =
	| 'present'
	| 'late'
	| 'absent'
	| 'excused'
	| 'pending'
	| 'rejected';

export interface StudentHistoryItemResponse {
	id: number;
	session_id: number;
	course_code: string;
	course_name: string;
	status: StudentHistoryStatus;
	original_status?: StudentHistoryStatus | null;
	excuse_reason?: string | null;
	scanned_at: string;
	scanned_via?: string | null;
}

export interface StudentHistoryResponse {
	items: StudentHistoryItemResponse[];
	total: number;
	page: number;
	size: number;
	summary: {
		compliance_rate: number;
		participation_rate: number;
		counts: {
			present: number;
			late: number;
			absent: number;
			excused: number;
			rejected: number;
		};
	};
}

// Student attendance history — live on features/attendance/router.py
// (GET /student/attendance/history). Query: ?program_id&year_level_id&semester&
// course_id&status&date_from&date_to&sort_by=date|course|section|status|time&
// sort_dir&page&size. Summary covers the FULL filter set, not just the page.
export const StudentHistoryEndpoint: EndpointDef<StudentHistoryResponse> = {
	url: '/student/attendance/history',
	method: 'GET',
	mock: () => ({
		items: [],
		total: 0,
		page: 1,
		size: 20,
		summary: {
			compliance_rate: 0,
			participation_rate: 0,
			counts: { present: 0, late: 0, absent: 0, excused: 0, rejected: 0 },
		},
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

const MOCK_ADMIN_STUDENT_ROWS: AdminStudentResponse[] = [
	{
		id: 1,
			student_id: '24-2132',
		first_name: 'Alice',
		middle_name: 'M',
		last_name: 'Santos',
		email: 'alice.santos@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '3rd Year',
		section: 'A',
		is_active: true,
		face_enrolled: true,
		created_at: '2024-06-01T08:00:00.000Z',
		scan_count: 42,
	},
	{
		id: 2,
			student_id: '24-1045',
		first_name: 'Bob',
		middle_name: null,
		last_name: 'Cruz',
		email: 'bob.cruz@isu.edu.ph',
		program_code: 'BSIT',
		year_level_label: '2nd Year',
		section: 'B',
		is_active: true,
		face_enrolled: false,
		created_at: '2024-06-02T08:00:00.000Z',
		scan_count: 18,
	},
	{
		id: 3,
		student_id: '24-3107',
		first_name: 'Carla',
		middle_name: 'D',
		last_name: 'Reyes',
		email: 'carla.reyes@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '3rd Year',
		section: 'A',
		is_active: false,
		face_enrolled: false,
		created_at: '2024-06-03T08:00:00.000Z',
		scan_count: 5,
	},
	{
		id: 4,
		student_id: '24-0892',
		first_name: 'Dan',
		middle_name: null,
		last_name: 'Aquino',
		email: 'dan.aquino@isu.edu.ph',
		program_code: 'BSECE',
		year_level_label: '1st Year',
		section: 'C',
		is_active: true,
		face_enrolled: true,
		created_at: '2024-06-04T08:00:00.000Z',
		scan_count: 30,
	},
	{
		id: 5,
		student_id: '24-5561',
		first_name: 'Ella',
		middle_name: 'F',
		last_name: 'Bautista',
		email: 'ella.bautista@isu.edu.ph',
		program_code: 'BSIT',
		year_level_label: '2nd Year',
		section: 'B',
		is_active: false,
		face_enrolled: false,
		created_at: '2024-06-05T08:00:00.000Z',
		scan_count: 0,
	},
	{
		id: 6,
		student_id: '24-7784',
		first_name: 'Felix',
		middle_name: null,
		last_name: 'Ocampo',
		email: 'felix.ocampo@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '4th Year',
		section: 'A',
		is_active: true,
		face_enrolled: true,
		created_at: '2024-06-06T08:00:00.000Z',
		scan_count: 51,
	},
	{
		id: 7,
		student_id: '24-1290',
		first_name: 'Gia',
		middle_name: 'H',
		last_name: 'Navarro',
		email: 'gia.navarro@isu.edu.ph',
		program_code: 'BSECE',
		year_level_label: '1st Year',
		section: 'C',
		is_active: true,
		face_enrolled: false,
		created_at: '2024-06-07T08:00:00.000Z',
		scan_count: 12,
	},
	{
		id: 8,
		student_id: '24-4436',
		first_name: 'Hugo',
		middle_name: null,
		last_name: 'Torres',
		email: 'hugo.torres@isu.edu.ph',
		program_code: 'BSIT',
		year_level_label: '3rd Year',
		section: 'A',
		is_active: true,
		face_enrolled: true,
		created_at: '2024-06-08T08:00:00.000Z',
		scan_count: 27,
	},
	{
		id: 9,
		student_id: '24-9021',
		first_name: 'Ivy',
		middle_name: 'J',
		last_name: 'Lim',
		email: 'ivy.lim@isu.edu.ph',
		program_code: 'BSCS',
		year_level_label: '2nd Year',
		section: 'B',
		is_active: true,
		face_enrolled: false,
		created_at: '2024-06-09T08:00:00.000Z',
		scan_count: 9,
	},
	{
		id: 10,
		student_id: '24-6178',
		first_name: 'Jonas',
		middle_name: null,
		last_name: 'Mendoza',
		email: 'jonas.mendoza@isu.edu.ph',
		program_code: 'BSECE',
		year_level_label: '2nd Year',
		section: 'A',
		is_active: false,
		face_enrolled: true,
		created_at: '2024-06-10T08:00:00.000Z',
		scan_count: 22,
	},
];

const MOCK_ADMIN_STUDENTS: Paginated<AdminStudentResponse> = {
	items: MOCK_ADMIN_STUDENT_ROWS.slice(0, 2),
	total: 2,
	page: 1,
	size: 20,
};

const mockAdminStudentsList = (
	params?: Record<string, string>
): Paginated<AdminStudentResponse> => {
	let rows = [...MOCK_ADMIN_STUDENT_ROWS];

	const search = params?.search?.trim().toLowerCase();
	if (search) {
		rows = rows.filter((r) =>
			[r.student_id, r.first_name, r.middle_name ?? '', r.last_name, r.email]
				.join(' ')
				.toLowerCase()
				.includes(search)
		);
	}

	if (params?.is_active !== undefined) {
		const wantActive = params.is_active === 'true';
		rows = rows.filter((r) => r.is_active === wantActive);
	}

	const section = params?.section?.trim().toLowerCase();
	if (section) {
		rows = rows.filter((r) => (r.section ?? '').toLowerCase() === section);
	}

	// program_id/year_level_id mirror the backend list filters. The mock rows
	// carry codes/labels rather than FK ids, so resolve through the programs
	// mock (same source the filter dropdowns read).
	if (params?.program_id) {
		const program = MOCK_PROGRAMS.items.find((p) => String(p.id) === params.program_id);
		rows = program ? rows.filter((r) => r.program_code === program.code) : [];
	}

	if (params?.year_level_id) {
		const year = MOCK_YEARS.find((y) => String(y.id) === params.year_level_id);
		rows = year ? rows.filter((r) => r.year_level_label === year.label) : [];
	}

	const sortBy = params?.sort_by;
	const dir = params?.sort_dir === 'desc' ? -1 : 1;
	if (sortBy === 'last_name' || sortBy === 'student_id' || sortBy === 'created_at') {
		rows.sort((a, b) => {
			if (sortBy === 'last_name') {
				return (
					a.last_name.localeCompare(b.last_name) ||
					a.first_name.localeCompare(b.first_name)
				) * dir;
			}
			return String(a[sortBy]).localeCompare(String(b[sortBy])) * dir;
		});
	}

	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);

	return {
		items: rows.slice((page - 1) * size, page * size),
		total,
		page,
		size,
	};
};

export const AdminStudentsEndpoint: EndpointDef<Paginated<AdminStudentResponse>> = {
	url: '/admin/students',
	method: 'GET',
	mock: (params) => mockAdminStudentsList(params),
};

interface MockStudentPayload {
	student_id?: unknown;
	first_name?: unknown;
	middle_name?: unknown;
	last_name?: unknown;
	email?: unknown;
	program_id?: unknown;
	year_level_id?: unknown;
	section?: unknown;
	is_active?: unknown;
}

// In-memory roster so mock-mode Add/Edit/Deactivate/Delete actually stick.
// Keyed off MOCK_ADMIN_STUDENT_ROWS; list/create/detail/delete all share it.
const findMockStudentRow = (suffix?: string): AdminStudentResponse => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_STUDENT_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Student not found.');
	return row;
};

const mockProgramCodeFor = (programId: number): string =>
	MOCK_PROGRAMS.items.find((p) => p.id === programId)?.code ?? 'BSCS';

const mockYearLabelFor = (yearLevelId: number): string =>
	MOCK_YEARS.find((y) => y.id === yearLevelId)?.label ?? '1st Year';

const toMockDetail = (row: AdminStudentResponse): AdminStudentDetailResponse => ({
	...row,
	face_enrolled_at: null,
	face_embedding_version: 1,
});

export const AdminStudentCreateEndpoint: EndpointDef<AdminStudentResponse> = {
	url: '/admin/students',
	method: 'POST',
	mock: (_params, _suffix, body) => {
		const p = (body ?? {}) as MockStudentPayload;
		const studentId = String(p.student_id ?? '').trim().toUpperCase();
		const email = String(p.email ?? '').trim().toLowerCase();
		if (MOCK_ADMIN_STUDENT_ROWS.some((r) => r.student_id === studentId)) {
			throw new Error('Student ID already exists.');
		}
		if (MOCK_ADMIN_STUDENT_ROWS.some((r) => r.email.toLowerCase() === email)) {
			throw new Error('Email already exists.');
		}
		const row: AdminStudentResponse = {
			id: Math.max(...MOCK_ADMIN_STUDENT_ROWS.map((r) => r.id), 0) + 1,
			student_id: studentId,
			first_name: String(p.first_name ?? ''),
			middle_name: (p.middle_name as string | null) ?? null,
			last_name: String(p.last_name ?? ''),
			email,
			program_code: mockProgramCodeFor(Number(p.program_id)),
			year_level_label: mockYearLabelFor(Number(p.year_level_id)),
			section: p.section ? String(p.section) : null,
			is_active: true,
			face_enrolled: false,
			created_at: new Date().toISOString(),
			scan_count: 0,
		};
		MOCK_ADMIN_STUDENT_ROWS.push(row);
		return row;
	},
};

export const AdminStudentDetailEndpoint: EndpointDef<AdminStudentDetailResponse> = {
	url: '/admin/students',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
		if (method === 'DELETE') {
			const row = findMockStudentRow(suffix);
			if (row.is_active) throw new Error('Only inactive students can be deleted.');
			MOCK_ADMIN_STUDENT_ROWS.splice(MOCK_ADMIN_STUDENT_ROWS.indexOf(row), 1);
			return undefined as unknown as AdminStudentDetailResponse;
		}
		if (method === 'PATCH') {
			const row = findMockStudentRow(suffix);
			const p = (body ?? {}) as MockStudentPayload;
			if (p.first_name !== undefined) row.first_name = String(p.first_name);
			if (p.last_name !== undefined) row.last_name = String(p.last_name);
			if (p.email !== undefined) row.email = String(p.email).trim().toLowerCase();
			if (p.section !== undefined) row.section = p.section ? String(p.section) : null;
			if (typeof p.is_active === 'boolean') row.is_active = p.is_active;
			if (p.program_id !== undefined)
				row.program_code = mockProgramCodeFor(Number(p.program_id));
			if (p.year_level_id !== undefined)
				row.year_level_label = mockYearLabelFor(Number(p.year_level_id));
			return toMockDetail(row);
		}
		return toMockDetail(findMockStudentRow(suffix));
	},
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

// --- Admin programs (Phase A: 4.5a + 4.5b) ----------------------------------
//
// Live routes on program/router.py (/api/admin/programs). Collection routes
// use "" on the backend (no trailing slash); detail/year routes pass path
// segments via the client's `suffix` option (e.g. `/3`, `/3/years`,
// `/3/years/12`). Aggregates on ProgramResponse (course_count,
// year_level_count, terms_count) are derived per request server-side.

const MOCK_PROGRAMS: Paginated<ProgramResponse> = {
	items: [
		{
			id: 1,
			code: 'BSCS',
			name: 'BS Computer Science',
			description: null,
			total_years: 4,
			is_active: true,
			course_count: 24,
			year_level_count: 4,
			terms_count: 9,
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		},
		{
			id: 2,
			code: 'BSIT',
			name: 'BS Information Technology',
			description: null,
			total_years: 4,
			is_active: true,
			course_count: 20,
			year_level_count: 4,
			terms_count: 8,
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
		},
	],
	total: 2,
	page: 1,
	size: 20,
};

const ordinal = (n: number): string =>
	n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`;

const mockYear = (id: number, programId: number, yearNumber: number): YearLevelResponse => ({
	id,
	program_id: programId,
	year_number: yearNumber,
	label: `${ordinal(yearNumber)} Year`,
	term_structure: {
		terms: [
			{ code: '1st', label: '1st Semester' },
			{ code: '2nd', label: '2nd Semester' },
		],
	},
	sort_order: yearNumber,
});

// 1st-6th Year for every mock program (ids 1-6 → program 1, 7-12 → program 2).
const MOCK_YEARS: YearLevelResponse[] = [
	...[1, 2, 3, 4, 5, 6].map((n, i) => mockYear(i + 1, 1, n)),
	...[1, 2, 3, 4, 5, 6].map((n, i) => mockYear(i + 7, 2, n)),
];

export const AdminProgramsEndpoint: EndpointDef<Paginated<ProgramResponse>> = {
	url: '/admin/programs',
	method: 'GET',
	mock: () => MOCK_PROGRAMS,
};

export const AdminProgramCreateEndpoint: EndpointDef<ProgramResponse> = {
	url: '/admin/programs',
	method: 'POST',
	mock: () => MOCK_PROGRAMS.items[0],
};

export const AdminProgramDetailEndpoint: EndpointDef<ProgramDetailResponse> = {
	url: '/admin/programs',
	method: 'GET',
	mock: (_params, suffix) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		const program = MOCK_PROGRAMS.items.find((p) => p.id === id) ?? MOCK_PROGRAMS.items[0];
		return {
			...program,
			year_levels: MOCK_YEARS.filter((y) => y.program_id === program.id),
		};
	},
};

export const AdminYearLevelsEndpoint: EndpointDef<Paginated<YearLevelResponse>> = {
	url: '/admin/programs',
	method: 'GET',
	mock: (_params, suffix) => {
		// Suffix looks like `/3/years` — only that program's years come back.
		const programId = parseInt(suffix?.match(/\/(\d+)\/years/)?.[1] ?? '', 10);
		const items =
			Number.isFinite(programId) && programId > 0
				? MOCK_YEARS.filter((y) => y.program_id === programId)
				: [...MOCK_YEARS];
		return { items, total: items.length, page: 1, size: 50 };
	},
};

export const AdminYearLevelDetailEndpoint: EndpointDef<YearLevelResponse> = {
	url: '/admin/programs',
	method: 'GET',
	mock: () => MOCK_YEARS[0],
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
	studentHistory: StudentHistoryEndpoint,
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
	// Admin programs (Phase A)
	adminPrograms: AdminProgramsEndpoint,
	adminProgramCreate: AdminProgramCreateEndpoint,
	adminProgramDetail: AdminProgramDetailEndpoint,
	adminYearLevels: AdminYearLevelsEndpoint,
	adminYearLevelDetail: AdminYearLevelDetailEndpoint,
};
