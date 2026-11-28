// api/endpoints.mock.ts
// In-memory fixtures and handlers for PUBLIC_MOCK_MODE=true. Every handler is
// typed from the endpoint definition it backs, so mock output stays in sync
// with the contract. Imported by api/endpoints.ts; type-only imports here
// keep the module graph acyclic at runtime.

import type * as defs from './endpoints';
import type {
	Paginated,
	StudentExcuseSubmitBody,
	StudentExcuseItemResponse,
	PresignedUrlRequest,
	SystemSettingsResponse,
	BackupLogItemResponse,
	ExcuseRequestReadResponse,
	ProfessorReportsAllCoursesItemResponse,
	LivenessReviewItemResponse,
	LivenessReviewResolveBody,
} from './endpoints';
import type {
	AdminAssignmentResponse,
	AdminCourseResponse,
	AdminOfferingResponse,
	AdminPasswordResetResponse,
	AdminProfessorResponse,
	AdminRosterItemResponse,
	AdminStudentDetailResponse,
	AdminStudentResponse,
	AdminUserResponse,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewItemResponse,
	AttendanceRecordItemResponse,
	AuditChangeResponse,
	AuditLogItemResponse,
	OfferingComponentResponse,
	ProgramResponse,
	StructureChangeResponse,
	TokenResponse,
	YearLevelResponse,
} from '$lib/shared/types';
import { DEFAULT_TERM_WEEKS } from '$lib/shared/constants/terms';

// Mock 204 No Content: the live client returns `undefined as T` for empty
// responses, and callers issue these deletes as `del<void>`, so a mock
// DELETE produces no value either. `never` is assignable to every T, which
// keeps the single cast here instead of an `as unknown as X` at each site.
const mockNoContent = (): never => undefined as unknown as never;

// Mock session registry: deterministic per mock-mode run so an opened session
// can be inspected and closed by id. Random ids made open→close unmatchable
// (close echoed a fixed id:0 and could collide) and the QR payload carried a
// different code than the session itself.
let mockSessionSeq = 1000;

const mockSessions = new Map<number, string>();

const mockSessionCode = (seq: number): string => {
	const base = seq.toString(36).toUpperCase().padStart(6, '0').slice(-6);
	return `${base.slice(0, 2)}-${base.slice(2)}`;
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
	otp_pending: false,
	otp_token: null,
	must_change_password: false,
};

// In-memory student excuse rows so mock-mode submits visibly stick.
const MOCK_STUDENT_EXCUSE_ROWS: StudentExcuseItemResponse[] = [];

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
		program_id: 1,
		year_level_label: '3rd Year',
		year_level_id: 3,
		section: 'A',
		is_active: true,
		face_enrolled: true,
		claim_status: 'Claimed',
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
		program_id: 2,
		year_level_label: '2nd Year',
		year_level_id: 8,
		section: 'B',
		is_active: true,
		face_enrolled: false,
		claim_status: 'Claimed',
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
		program_id: 1,
		year_level_label: '3rd Year',
		year_level_id: 3,
		section: 'A',
		is_active: false,
		face_enrolled: false,
		claim_status: 'Unclaimed',
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
		program_id: 1,
		year_level_label: '1st Year',
		year_level_id: 1,
		section: 'C',
		is_active: true,
		face_enrolled: true,
		claim_status: 'Claimed',
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
		program_id: 2,
		year_level_label: '2nd Year',
		year_level_id: 8,
		section: 'B',
		is_active: false,
		face_enrolled: false,
		claim_status: 'Unclaimed',
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
		program_id: 1,
		year_level_label: '4th Year',
		year_level_id: 4,
		section: 'A',
		is_active: true,
		face_enrolled: true,
		claim_status: 'Claimed',
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
		program_id: 1,
		year_level_label: '1st Year',
		year_level_id: 1,
		section: 'C',
		is_active: true,
		face_enrolled: false,
		claim_status: 'Claimed',
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
		program_id: 2,
		year_level_label: '3rd Year',
		year_level_id: 9,
		section: 'A',
		is_active: true,
		face_enrolled: true,
		claim_status: 'Claimed',
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
		program_id: 1,
		year_level_label: '2nd Year',
		year_level_id: 2,
		section: 'B',
		is_active: true,
		face_enrolled: false,
		claim_status: 'Claimed',
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
		program_id: 1,
		year_level_label: '2nd Year',
		year_level_id: 2,
		section: 'A',
		is_active: false,
		face_enrolled: true,
		claim_status: 'Unclaimed',
		created_at: '2024-06-10T08:00:00.000Z',
		scan_count: 22,
	},
];

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

// Mock CSV import: derives counts from the uploaded file's real rows when
// postForm forwards them (see client.ts postForm), so duplicate/error paths
// are testable in mock mode. Without file info it keeps the legacy fixed
// fixture. Line numbers are 1-based file lines (header is line 1); a repeat
// first-column value counts as a duplicate, a wrong column count or a blank
// first cell counts as an error.
const mockCsvImport = (
	body: unknown,
	legacyImported: number
): { imported: number; duplicates: number; errors: { line: number; reason: string }[] } => {
	const fileText = (body as { fileText?: unknown } | undefined)?.fileText;
	if (typeof fileText !== 'string')
		return { imported: legacyImported, duplicates: 0, errors: [] };
	const lines = fileText.split(/\r?\n/);
	const expectedCols = (lines[0] ?? '').split(',').length;
	let imported = 0;
	let duplicates = 0;
	const errors: { line: number; reason: string }[] = [];
	const seen = new Set<string>();
	lines.slice(1).forEach((line, index) => {
		if (line.trim() === '') return;
		const lineNo = index + 2;
		const cells = line.split(',');
		const key = (cells[0] ?? '').trim().toLowerCase();
		if (cells.length !== expectedCols || key === '') {
			errors.push({
				line: lineNo,
				reason:
					cells.length !== expectedCols
						? `Expected ${expectedCols} columns, found ${cells.length}.`
						: 'Missing identifier in the first column.',
			});
			return;
		}
		if (seen.has(key)) {
			duplicates += 1;
			return;
		}
		seen.add(key);
		imported += 1;
	});
	return { imported, duplicates, errors };
};

// Mock face-enrollment state per roster id (the detail mock carries no
// per-row enrollment stamp, so the upload/status mocks keep their own).
const MOCK_FACE_VERSIONS = new Map<number, number>();

const MOCK_FACE_ENROLLED_AT = new Map<number, string>();

// In-memory professor roster so mock-mode list/create/edit/deactivate/delete
// behave like the backend. Mirrors the student mock above: list filters/sorts/
// paginates, detail handles GET/PATCH/DELETE via suffix + method.
const MOCK_ADMIN_PROFESSOR_ROWS: AdminProfessorResponse[] = [
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
];

const mockAdminProfessorsList = (
	params?: Record<string, string>
): Paginated<AdminProfessorResponse> => {
	let rows = [...MOCK_ADMIN_PROFESSOR_ROWS];

	const search = params?.search?.trim().toLowerCase();
	if (search) {
		rows = rows.filter((r) =>
			[r.first_name, r.middle_name ?? '', r.last_name, r.email]
				.join(' ')
				.toLowerCase()
				.includes(search)
		);
	}

	const department = params?.department?.trim().toLowerCase();
	if (department) {
		rows = rows.filter((r) => (r.department ?? '').toLowerCase() === department);
	}

	if (params?.is_active !== undefined) {
		const wantActive = params.is_active === 'true';
		rows = rows.filter((r) => r.is_active === wantActive);
	}

	const sortBy = params?.sort_by;
	const dir = params?.sort_dir === 'desc' ? -1 : 1;
	if (sortBy === 'last_name' || sortBy === 'email' || sortBy === 'created_at') {
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

interface MockProfessorPayload {
	first_name?: unknown;
	last_name?: unknown;
	email?: unknown;
	department?: unknown;
	is_active?: unknown;
	courses?: unknown;
}

const findMockProfessorRow = (suffix?: string): AdminProfessorResponse => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_PROFESSOR_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Professor not found.');
	return row;
};

const mockCourseCodeFor = (offeringId: number): string => {
	const found = MOCK_ADMIN_PROFESSOR_ROWS.flatMap((r) => r.assigned_courses).find(
		(c) => c.offering_id === offeringId
	);
	return found?.course_code ?? `Offering ${offeringId}`;
};

// --- Admin offerings (professor assignment picker) ---------------------------
//
// Live route on course/offering_router.py (GET /admin/offerings). The
// OfferingRead contract carries no course_code, so option labels fall back to
// `Offering {id}` with course/semester/year context. Filter params mirror the
// backend list query; the mock honors is_active + pagination.
const MOCK_ADMIN_OFFERINGS: AdminOfferingResponse[] = [
	{
		id: 1,
		course_id: 1,
		program_id: 1,
		year_level_id: 1,
		semester: '1st Sem',
		academic_year: '2025-2026',
		sessions_per_week: 2,
		semester_weeks: 18,
		schedule_days: 'MWF',
		schedule_start_time: '09:00:00',
		schedule_end_time: '10:30:00',
		course_type: 'lecture',
		session_types: ['lecture'],
		components: [
			{
				id: 1,
				offering_id: 1,
				session_type: 'lecture',
				schedule_days: 'MWF',
				schedule_start_time: '09:00:00',
				schedule_end_time: '10:30:00',
				classroom_name: 'Lab 101',
				classroom_lat: null,
				classroom_lng: null,
				is_active: true,
				created_at: new Date().toISOString(),
				updated_at: new Date().toISOString(),
			},
		],
		classroom_name: 'Lab 101',
		classroom_lat: null,
		classroom_lng: null,
		default_present_window_minutes: 5,
		default_late_window_minutes: 10,
		default_classroom_radius_meters: null,
		enrolled_count: 30,
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
	{
		id: 2,
		course_id: 2,
		program_id: 1,
		year_level_id: 1,
		semester: '1st Sem',
		academic_year: '2025-2026',
		sessions_per_week: 2,
		semester_weeks: 18,
		schedule_days: 'TH',
		schedule_start_time: '11:00:00',
		schedule_end_time: '12:30:00',
		course_type: 'lecture',
		session_types: ['lecture'],
		components: [
			{
				id: 2,
				offering_id: 2,
				session_type: 'lecture',
				schedule_days: 'TH',
				schedule_start_time: '11:00:00',
				schedule_end_time: '12:30:00',
				classroom_name: 'Room 203',
				classroom_lat: null,
				classroom_lng: null,
				is_active: true,
				created_at: new Date().toISOString(),
				updated_at: new Date().toISOString(),
			},
		],
		classroom_name: 'Room 203',
		classroom_lat: null,
		classroom_lng: null,
		default_present_window_minutes: 5,
		default_late_window_minutes: 10,
		default_classroom_radius_meters: null,
		enrolled_count: 35,
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
	{
		id: 3,
		course_id: 1,
		program_id: 2,
		year_level_id: 7,
		semester: '1st Sem',
		academic_year: '2025-2026',
		sessions_per_week: 2,
		semester_weeks: 18,
		schedule_days: 'MWF',
		schedule_start_time: '09:00:00',
		schedule_end_time: '10:30:00',
		course_type: 'lecture',
		session_types: ['lecture'],
		components: [
			{
				id: 3,
				offering_id: 3,
				session_type: 'lecture',
				schedule_days: 'MWF',
				schedule_start_time: '09:00:00',
				schedule_end_time: '10:30:00',
				classroom_name: 'Lab 101',
				classroom_lat: null,
				classroom_lng: null,
				is_active: true,
				created_at: new Date().toISOString(),
				updated_at: new Date().toISOString(),
			},
		],
		classroom_name: 'Lab 101',
		classroom_lat: null,
		classroom_lng: null,
		default_present_window_minutes: 5,
		default_late_window_minutes: 10,
		default_classroom_radius_meters: null,
		enrolled_count: 25,
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
];

// --- Admin courses (templates, D44) ------------------------------------------
//
// Live routes on course/router.py (/api/admin/courses). Collection routes use
// "" on the backend (no trailing slash); detail routes pass the id via the
// client's `suffix` option (e.g. `/3`). The list query takes only
// ?is_active&page&size — search + Code/Name sorts run client-side over the
// loaded page (same convention as programs). DELETE is a permanent delete
// guarded server-side — only archived courses with no offerings go through
// (409 `not_archived` / `course_has_offerings`).

const MOCK_ADMIN_COURSE_ROWS: AdminCourseResponse[] = [
	{
		id: 1,
		course_code: 'CS101',
		course_name: 'Software Engineering 1',
		units: 3,
		session_duration_hours: 1.5,
		course_type: 'lecture',
		is_active: true,
		created_at: '2024-06-01T08:00:00.000Z',
		updated_at: '2024-06-01T08:00:00.000Z',
	},
	{
		id: 2,
		course_code: 'CS102',
		course_name: 'Data Structures',
		units: 3,
		session_duration_hours: 1.5,
		course_type: 'lecture',
		is_active: true,
		created_at: '2024-06-02T08:00:00.000Z',
		updated_at: '2024-06-02T08:00:00.000Z',
	},
	{
		id: 3,
		course_code: 'MATH101',
		course_name: 'Calculus 1',
		units: 4,
		session_duration_hours: 2,
		course_type: 'lecture',
		is_active: true,
		created_at: '2024-06-03T08:00:00.000Z',
		updated_at: '2024-06-03T08:00:00.000Z',
	},
	{
		id: 4,
		course_code: 'GE001',
		course_name: 'Ethics',
		units: 2,
		session_duration_hours: 1,
		course_type: 'lecture',
		is_active: false,
		created_at: '2024-06-04T08:00:00.000Z',
		updated_at: '2024-06-04T08:00:00.000Z',
	},
];

interface MockCoursePayload {
	course_code?: unknown;
	course_name?: unknown;
	units?: unknown;
	session_duration_hours?: unknown;
	course_type?: unknown;
	is_active?: unknown;
}

const findMockCourseRow = (suffix?: string): AdminCourseResponse => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_COURSE_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Course not found.');
	return row;
};

// --- Admin offering detail: CRUD + professors + roster + bulk enroll ---------
//
// Live routes on course/offering_router.py (/api/admin/offerings). Same
// suffix convention as above: `/{oid}`, `/{oid}/professors`,
// `/{oid}/professors/{pid}`, `/{oid}/students`, `/{oid}/enrollments/bulk`.

interface MockOfferingPayload {
	course_id?: unknown;
	program_id?: unknown;
	year_level_id?: unknown;
	semester?: unknown;
	academic_year?: unknown;
	sessions_per_week?: unknown;
	schedule_days?: unknown;
	schedule_start_time?: unknown;
	schedule_end_time?: unknown;
	course_type?: unknown;
	components?: unknown;
	classroom_name?: unknown;
	classroom_lat?: unknown;
	classroom_lng?: unknown;
	default_present_window_minutes?: unknown;
	default_late_window_minutes?: unknown;
	default_classroom_radius_meters?: unknown;
	is_active?: unknown;
}

const findMockOfferingRow = (suffix?: string): AdminOfferingResponse => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_OFFERINGS.find((r) => r.id === id);
	if (!row) throw new Error('Offering not found.');
	return row;
};

// Session weeks are term-scoped (D86): the mock derives them from its own
// year-level term structure rather than accepting them on a payload.
const mockTermWeeks = (yearLevelId: number, semester: string): number => {
	const year = MOCK_YEARS.find((y) => y.id === yearLevelId);
	const term = year?.term_structure.terms.find((t) => t.code === semester);
	return term?.weeks ?? DEFAULT_TERM_WEEKS;
};

// D77 mock components: the offering rows above are the single source of
// truth (each carries its components array); these helpers build and
// maintain them the way the live service does.
const mockComponentId = (): number =>
	Math.max(0, ...MOCK_ADMIN_OFFERINGS.flatMap((r) => r.components.map((c) => c.id))) + 1;

const refreshMockSessionTypes = (row: AdminOfferingResponse): void => {
	// D95: the types the offering can open — the ones it configures as
	// active meetings, or a lecture when it has none. The server owns the
	// rule; the mock follows it.
	const types = [
		...new Set(
			row.components.filter((c) => c.is_active).map((c) => c.session_type)
		)
	];
	row.session_types = types.length > 0 ? types : ['lecture'];
	row.updated_at = new Date().toISOString();
};

interface MockComponentPayload {
	session_type?: unknown;
	schedule_days?: unknown;
	schedule_start_time?: unknown;
	schedule_end_time?: unknown;
	classroom_name?: unknown;
	classroom_lat?: unknown;
	classroom_lng?: unknown;
	is_active?: unknown;
}

const mockComponentFromPayload = (
	offeringId: number,
	p: MockComponentPayload,
	fallback: { days: string; start: string; end: string; name: string | null; lat: number | null; lng: number | null }
): OfferingComponentResponse => {
	const session_type = p.session_type === 'lab' ? 'lab' : 'lecture';
	const days = String(p.schedule_days ?? fallback.days).trim().toUpperCase();
	const start = String(p.schedule_start_time ?? fallback.start);
	const end = String(p.schedule_end_time ?? fallback.end);
	if (end <= start) throw new Error('schedule_end_time must be after schedule_start_time');
	return {
		id: mockComponentId(),
		offering_id: offeringId,
		session_type,
		schedule_days: days,
		schedule_start_time: start,
		schedule_end_time: end,
		classroom_name:
			p.classroom_name === undefined
				? fallback.name
				: p.classroom_name
					? String(p.classroom_name)
					: null,
		classroom_lat:
			p.classroom_lat === undefined || p.classroom_lat === null
				? (p.classroom_lat === null ? null : fallback.lat)
				: Number(p.classroom_lat),
		classroom_lng:
			p.classroom_lng === undefined || p.classroom_lng === null
				? (p.classroom_lng === null ? null : fallback.lng)
				: Number(p.classroom_lng),
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	};
};

const mockComponentsForCreate = (
	row: AdminOfferingResponse,
	raw: unknown
): OfferingComponentResponse[] => {
	const items = Array.isArray(raw) ? (raw as MockComponentPayload[]) : [];
	const fallback = {
		days: row.schedule_days,
		start: row.schedule_start_time,
		end: row.schedule_end_time,
		name: row.classroom_name,
		lat: row.classroom_lat,
		lng: row.classroom_lng,
	};
	const list = (
		items.length > 0
			? items
			: [{ session_type: 'lecture' as const }]
	).map((p) => mockComponentFromPayload(row.id, p, fallback));
	const seen = new Set<string>();
	for (const c of list) {
		const key = `${c.session_type}|${c.schedule_days}|${c.schedule_start_time}`;
		if (seen.has(key)) throw new Error('Offering already has a component on that schedule.');
		seen.add(key);
	}
	return list;
};

const findMockComponentRow = (
	suffix?: string
): { offering: AdminOfferingResponse; component: OfferingComponentResponse } => {
	const offering = findMockOfferingRow(suffix);
	const id = parseInt(suffix?.match(/\/components\/(\d+)/)?.[1] ?? '', 10);
	const component = offering.components.find((c) => c.id === id);
	if (!component) throw new Error('Offering component not found.');
	return { offering, component };
};

// In-memory professor assignments so mock-mode assign/end stick. Seeded with
// one primary assignment on offering 1 (mirrors the professor mock rows).
const MOCK_ADMIN_ASSIGNMENTS: AdminAssignmentResponse[] = [
	{
		offering_id: 1,
		professor_id: 1,
		is_primary: true,
		effective_from: '2026-01-01',
		effective_to: null,
		semester: '1st Sem',
		has_sessions: false,
		assigned_by: 1,
		assigned_at: new Date().toISOString(),
	},
];

interface MockAssignmentPayload {
	professor_id?: unknown;
	new_professor_id?: unknown;
	is_primary?: unknown;
	old_effective_from?: unknown;
	effective_from?: unknown;
	effective_to?: unknown;
}

// Open-ended dates compare as a far-future sentinel, mirroring the backend
// overlap check (NULL effective_to = ongoing).
const mockDateOrOngoing = (value: string | null | undefined): string =>
	value ?? '9999-12-31';

const mockDayBefore = (iso: string): string => {
	const date = new Date(`${iso}T00:00:00Z`);
	date.setUTCDate(date.getUTCDate() - 1);
	return date.toISOString().slice(0, 10);
};

// At most one primary assignment may cover an offering on any date. Mock rows
// mirror the backend's inclusive interval check so mock mode rejects the same
// conflicting writes instead of only the live API doing so.
const mockPrimaryConflict = (
	offeringId: number,
	effectiveFrom: string,
	effectiveTo: string | null,
	exclude?: AdminAssignmentResponse
): AdminAssignmentResponse | undefined =>
	MOCK_ADMIN_ASSIGNMENTS.find(
		(a) =>
			a.offering_id === offeringId &&
			a !== exclude &&
			a.is_primary &&
			mockDateOrOngoing(a.effective_to) >= effectiveFrom &&
			mockDateOrOngoing(effectiveTo) >= a.effective_from
	);

const mockPrimaryConflictError = (assignment: AdminAssignmentResponse): Error =>
	new Error(
		`This offering already has a primary professor from ${assignment.effective_from} to ${assignment.effective_to ?? 'ongoing'}. Assign this professor as an assistant, or end/change the existing primary assignment first.`
	);

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
			{ code: '1st', label: '1st Semester', weeks: DEFAULT_TERM_WEEKS },
			{ code: '2nd', label: '2nd Semester', weeks: DEFAULT_TERM_WEEKS },
		],
	},
	sort_order: yearNumber,
});

// 1st-6th Year for every mock program (ids 1-6 → program 1, 7-12 → program 2).
const MOCK_YEARS: YearLevelResponse[] = [
	...[1, 2, 3, 4, 5, 6].map((n, i) => mockYear(i + 1, 1, n)),
	...[1, 2, 3, 4, 5, 6].map((n, i) => mockYear(i + 7, 2, n)),
];

// --- Admin analytics & attendance overview (Phase 7, D33-D37) -----------------
//
// The analytics + attendance-overview routers landed in backend #136/#138, so
// the defs below hit the real API by default; mocks only when
// PUBLIC_MOCK_MODE=true (see api/client.ts). The mock sessions feed every tab
// (overview, comparison, trends, attendance overview, recent scans) so the
// numbers can never contradict each other.

interface MockAnalyticsSession {
	date: string;
	courseId: number;
	courseCode: string;
	courseName: string;
	programId: number;
	programCode: string;
	yearLevelId: number;
	yearLevelLabel: string;
	semester: string;
	enrolled: number;
	present: number;
	late: number;
	excused: number;
}

// Deterministic daily sessions for the last 30 days across three cohorts
// (same course under two cohorts — D6/D34). Built once; every mock derives
// from this table.
const buildMockAnalyticsSessions = (): MockAnalyticsSession[] => {
	const cohorts = [
		{ courseId: 1, courseCode: 'CS101', courseName: 'Software Engineering 1', programId: 1, programCode: 'BSCS', yearLevelId: 1, yearLevelLabel: '1st Year', enrolled: 30, base: 0.88 },
		{ courseId: 3, courseCode: 'MATH101', courseName: 'Calculus 1', programId: 1, programCode: 'BSCS', yearLevelId: 1, yearLevelLabel: '1st Year', enrolled: 35, base: 0.72 },
		{ courseId: 1, courseCode: 'CS101', courseName: 'Software Engineering 1', programId: 2, programCode: 'BSIT', yearLevelId: 7, yearLevelLabel: '1st Year', enrolled: 25, base: 0.91 },
	];
	const sessions: MockAnalyticsSession[] = [];
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	cohorts.forEach((cohort, cohortIdx) => {
		for (let dayAgo = 29; dayAgo >= 0; dayAgo--) {
			// ~3 sessions a week per cohort (Mon/Wed/Fri cadence).
			const weekday = (today.getDay() - dayAgo % 7 + 70) % 7;
			if (![1, 3, 5].includes(weekday)) continue;
			const date = new Date(today);
			date.setDate(today.getDate() - dayAgo);
			const dateKey = date.toISOString().slice(0, 10);
			// Deterministic wiggle ±6pp so trends have shape without randomness.
			const seed = cohortIdx * 1000 + (29 - dayAgo);
			const wiggle = (((seed * 9301 + 49297) % 233280) / 233280 - 0.5) * 0.12;
			const presentShare = Math.min(0.98, Math.max(0.4, cohort.base + wiggle));
			const present = Math.round(cohort.enrolled * presentShare);
			const late = Math.round(cohort.enrolled * 0.06);
			const excused = Math.round(cohort.enrolled * 0.02);
			sessions.push({
				date: dateKey,
				courseId: cohort.courseId,
				courseCode: cohort.courseCode,
				courseName: cohort.courseName,
				programId: cohort.programId,
				programCode: cohort.programCode,
				yearLevelId: cohort.yearLevelId,
				yearLevelLabel: cohort.yearLevelLabel,
				semester: '1st Sem',
				enrolled: cohort.enrolled,
				present,
				late,
				excused,
			});
		}
	});
	return sessions;
};

const MOCK_ANALYTICS_SESSIONS: MockAnalyticsSession[] = buildMockAnalyticsSessions();

const defaultMockRange = (params?: Record<string, string>): { from: string; to: string } => {
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	const to = params?.date_to ?? today.toISOString().slice(0, 10);
	const fromDate = new Date(today);
	fromDate.setDate(today.getDate() - 29);
	const from = params?.date_from ?? fromDate.toISOString().slice(0, 10);
	return from <= to ? { from, to } : { from: to, to: from };
};

const filterMockSessions = (
	params?: Record<string, string>,
	courseIds?: number[]
): MockAnalyticsSession[] => {
	const { from, to } = defaultMockRange(params);
	return MOCK_ANALYTICS_SESSIONS.filter(
		(s) =>
			s.date >= from &&
			s.date <= to &&
			(!params?.program_id || String(s.programId) === params.program_id) &&
			(!params?.year_level_id || String(s.yearLevelId) === params.year_level_id) &&
			(!params?.semester || s.semester.toLowerCase() === params.semester.trim().toLowerCase()) &&
			(!courseIds || courseIds.length === 0 || courseIds.includes(s.courseId))
	);
};

const parseCourseIds = (params?: Record<string, string>): number[] | undefined => {
	if (!params?.course_ids) return undefined;
	const ids = params.course_ids
		.split(',')
		.map((v) => Number(v.trim()))
		.filter((v) => Number.isInteger(v) && v > 0);
	return ids.length > 0 ? ids : undefined;
};

const summarizeMockSessions = (sessions: MockAnalyticsSession[]) => {
	let present = 0;
	let eligible = 0;
	let seats = 0;
	for (const s of sessions) {
		present += s.present;
		eligible += s.present + s.late + s.excused;
		seats += s.enrolled;
	}
	return {
		compliance: seats === 0 ? 0 : present / seats,
		participation: seats === 0 ? 0 : eligible / seats,
	};
};

// In-memory at-risk rows so mock-mode refresh visibly recomputes
// (computed_at bumps to now). Thresholds mirror D35.
const MOCK_AT_RISK_ROWS: AnalyticsAtRiskItemResponse[] = [
	{ student_id: '24-2132', student_name: 'Alice Santos', program: 'BSCS', year_level: '1st Year', offering_id: 2, course_code: 'MATH101', course_name: 'Calculus 1', absence_rate: 0.42, max_streak: 5, trend_slope: -0.12, risk_level: 'high', computed_at: new Date().toISOString() },
	{ student_id: '24-1045', student_name: 'Bob Cruz', program: 'BSIT', year_level: '1st Year', offering_id: 3, course_code: 'CS101', course_name: 'Software Engineering 1', absence_rate: 0.28, max_streak: 3, trend_slope: -0.08, risk_level: 'medium', computed_at: new Date().toISOString() },
	{ student_id: '24-3107', student_name: 'Carla Reyes', program: 'BSCS', year_level: '1st Year', offering_id: 1, course_code: 'CS101', course_name: 'Software Engineering 1', absence_rate: 0.18, max_streak: 1, trend_slope: -0.06, risk_level: 'medium', computed_at: new Date().toISOString() },
	{ student_id: '24-0892', student_name: 'Dan Aquino', program: 'BSCS', year_level: '1st Year', offering_id: 1, course_code: 'CS101', course_name: 'Software Engineering 1', absence_rate: 0.15, max_streak: 0, trend_slope: 0.01, risk_level: 'low', computed_at: new Date().toISOString() },
	{ student_id: '24-5561', student_name: 'Ella Bautista', program: 'BSIT', year_level: '1st Year', offering_id: 3, course_code: 'CS101', course_name: 'Software Engineering 1', absence_rate: 0.08, max_streak: 0, trend_slope: 0.03, risk_level: 'low', computed_at: new Date().toISOString() },
	{ student_id: '24-7784', student_name: 'Felix Ocampo', program: 'BSCS', year_level: '1st Year', offering_id: 2, course_code: 'MATH101', course_name: 'Calculus 1', absence_rate: 0.35, max_streak: 4, trend_slope: -0.02, risk_level: 'high', computed_at: new Date().toISOString() },
];

const mockBucketKey = (dateKey: string, granularity: string): { key: string; date: string } => {
	if (granularity === 'monthly') return { key: dateKey.slice(0, 7), date: `${dateKey.slice(0, 7)}-01` };
	if (granularity === 'weekly') {
		const [y, m, d] = dateKey.split('-').map(Number);
		const date = new Date(y, m - 1, d);
		const monday = new Date(date);
		monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
		const key = monday.toISOString().slice(0, 10);
		return { key, date: key };
	}
	return { key: dateKey, date: dateKey };
};

const MOCK_SYSTEM_SETTINGS: SystemSettingsResponse = {
	geofence_default_radius: 50,
	present_window_default: 5,
	late_window_default: 10,
	session_early_open_minutes: 30,
	session_late_open_minutes: 0,
	backup_retention_daily: 30,
	backup_retention_monthly: 12,
	attendance_attempt_limit_default: 3,
	pending_sync_count: 3
};

const mockBackupAt = (daysAgo: number, time: string): string => {
	const date = new Date();
	date.setHours(0, 0, 0, 0);
	date.setDate(date.getDate() - daysAgo);
	return `${date.toISOString().slice(0, 10)}T${time}.000Z`;
};

const MOCK_BACKUP_ROWS: BackupLogItemResponse[] = [
	{
		id: 31,
		filename: 'attendance_full_2026-09-28T030000Z.dump.gpg',
		kind: 'full',
		size_bytes: 43_008_512,
		storage_backend: 'local',
		started_at: mockBackupAt(1, '03:00:00'),
		finished_at: mockBackupAt(1, '03:04:12'),
		status: 'completed'
	},
	{
		id: 30,
		filename: 'attendance_full_2026-09-27T030000Z.dump.gpg',
		kind: 'full',
		size_bytes: 41_943_040,
		storage_backend: 'local',
		started_at: mockBackupAt(2, '03:00:00'),
		finished_at: mockBackupAt(2, '03:03:58'),
		status: 'completed'
	}
];

// --- Admin audit logs (live backend, api-contracts §System Settings & Backups) --
//
// GET /admin/audit-logs?entity_type&action&performed_by&actor&date_from&date_to
//   &sort_by&sort_dir&page&size
// returns { items: [{ id, action, entity_type, entity_id, old_value, new_value,
// performed_by, performed_at, actor, subject, summary, action_label, changes }],
// total, page, size }. Mocks only when PUBLIC_MOCK_MODE=true.
//
// The fixtures below mirror the CONTRACT shape, not a friendlier invention
// of it:
//   - `performed_by` is a `users.id` in the MOCK_ADMIN_USER_ROWS id space
//     (1 super_admin, 2 admin, 3 professor, 4 student) — never a name.
//   - `old_value`/`new_value` are the JSON snapshots the server's
//     `_<entity>_snapshot` methods actually take.
//   - every `action` is a real `AuditAction`, and every `entity_type` a real
//     `AuditEntityType`.
//
// The previous fixtures used readable strings for all three, which meant mock
// mode rendered a page the real API never produces — and hid every rendering
// bug that came with the real shape.
//
// The DERIVED part of the contract (actor, subject, summary, action_label,
// changes) is produced here by `mockAuditRow`, which is this file's stand-in
// for the server's `features/system/audit_labels.py`. A test double
// reimplements enough of the behaviour to be useful; it is not the
// reference — the server is.

const mockAuditAt = (daysAgo: number, time: string): string => {
	const date = new Date();
	date.setHours(0, 0, 0, 0);
	date.setDate(date.getDate() - daysAgo);
	return `${date.toISOString().slice(0, 10)}T${time}.000Z`;
};

const MOCK_ACTORS: Record<number, { name: string; email: string; role: string }> = {
	1: { name: 'Super Admin', email: 'superadmin@isu.edu.ph', role: 'super_admin' },
	2: { name: 'Admin User', email: 'admin@isu.edu.ph', role: 'admin' },
	3: {
		name: 'Maria Dela Cruz',
		email: 'maria.c.delacruz@isu.edu.ph',
		role: 'professor',
	},
	4: { name: 'Juan Dela Cruz', email: 'juan.delacruz@isu.edu.ph', role: 'student' },
};

const MOCK_ACTION_LABELS: Record<string, string> = {
	create: 'Created',
	update: 'Updated',
	archive: 'Archived',
	delete: 'Deleted',
	import: 'Imported',
	enroll: 'Enrolled',
	unenroll: 'Removed',
	assign: 'Assigned',
	reassign: 'Reassigned',
	reopen: 'Reopened',
	unassign: 'Assignment ended',
	open: 'Opened',
	close: 'Closed',
	approve: 'Approved',
	reject: 'Rejected',
	revoke: 'Revoked',
	lock: 'Locked',
	unlock: 'Unlocked',
	login_failed: 'Sign-in failed',
	password_reset: 'Password reset',
};

const MOCK_FIELD_LABELS: Record<string, string> = {
	code: 'Code',
	name: 'Name',
	description: 'Description',
	total_years: 'Years in the program',
	is_active: 'Status',
	program_id: 'Program',
	year_number: 'Year number',
	label: 'Label',
	term_structure: 'Terms',
	sort_order: 'Order',
	course_code: 'Course code',
	course_name: 'Course name',
	units: 'Units',
	session_duration_hours: 'Session length (hours)',
	course_id: 'Course',
	year_level_id: 'Year level',
	semester: 'Term',
	academic_year: 'Academic year',
	sessions_per_week: 'Sessions per week',
	schedule_days: 'Meeting days',
	schedule_start_time: 'Starts',
	schedule_end_time: 'Ends',
	classroom_name: 'Classroom',
	offering_id: 'Offering',
	session_type: 'Session type',
	student_id: 'Student',
	first_name: 'First name',
	last_name: 'Last name',
	email: 'Email',
	section: 'Section',
	face_enrolled_at: 'Face enrolled at',
	department: 'Department',
	professor_id: 'Professor',
	session_code: 'Session code',
	scheduled_start_time: 'Scheduled start',
	scheduled_end_time: 'Scheduled end',
	expires_at: 'Expires at',
	failed_login_attempts: 'Failed sign-in attempts',
	is_locked: 'Account locked',
	locked_at: 'Locked at',
	must_change_password: 'Must change password',
	role: 'Role',
	is_primary: 'Role',
	effective_from: 'Effective from',
	effective_to: 'Effective to',
	initiated_by: 'Initiated by',
	initiated_via: 'Submitted via',
	reason: 'Reason',
	attachment_count: 'Attachments',
	status: 'Status',
	reviewed_by: 'Reviewed by',
	review_notes: 'Review notes',
	kind: 'Backup type',
	filename: 'File',
	size_bytes: 'File size',
	storage_backend: 'Storage',
	sha256: 'Checksum',
	imported: 'Imported',
	duplicates: 'Skipped (already existed)',
	errors: 'Errors',
	enrolled: 'Enrolled',
	skipped: 'Skipped',
	processed: 'Processed',
	succeeded: 'Succeeded',
	failed: 'Failed',
	validation_status: 'Attendance status',
	review_note: 'Review note',
	face_embedding_version: 'Face template version',
};

const MOCK_DAYS: Record<string, string> = {
	M: 'Mon',
	T: 'Tue',
	W: 'Wed',
	H: 'Thu',
	F: 'Fri',
	S: 'Sat',
	U: 'Sun',
};

const mockValue = (field: string, value: unknown): string => {
	if (field === 'is_active') return value === true ? 'Active' : value === false ? 'Archived' : '—';
	if (field === 'is_locked') return value === true ? 'Locked' : value === false ? 'Not locked' : '—';
	if (field === 'must_change_password')
		return value === true ? 'Yes — must change at next sign-in' : value === false ? 'No' : '—';
	if (field === 'enrolled')
		return typeof value === 'number'
			? String(value)
			: value === true
				? 'Yes'
				: value === false
					? 'No'
					: '—';
	if (field === 'is_primary') return value === true ? 'Primary' : value === false ? 'Assistant' : '—';
	if (field === 'schedule_days' && typeof value === 'string') {
		const days = value
			.toUpperCase()
			.split('')
			.map((letter) => MOCK_DAYS[letter])
			.filter((day): day is string => !!day);
		return days.length > 0 ? days.join(', ') : value;
	}
	if (field === 'offering_id') return value === null || value === undefined ? '—' : `Offering #${String(value)}`;
	if (field === 'professor_id') return value === null || value === undefined ? '—' : `Professor #${String(value)}`;
	if (field === 'course_id') return value === null || value === undefined ? '—' : `Course #${String(value)}`;
	if (field === 'program_id') return value === null || value === undefined ? '—' : `Program #${String(value)}`;
	if (field === 'year_level_id') return value === null || value === undefined ? '—' : `Year level #${String(value)}`;
	if (field === 'student_id' && typeof value === 'number')
		return `Student #${String(value)}`;
	if (field === 'term_structure' && typeof value === 'object' && value !== null) {
		const terms = (value as { terms?: unknown }).terms;
		if (!Array.isArray(terms)) return '—';
		const labels = terms
			.map((term) =>
				typeof term === 'object' && term !== null
					? String((term as { label?: unknown }).label ?? '')
					: String(term)
			)
			.filter((label) => label.length > 0);
		return labels.length > 0 ? `${labels.length} terms: ${labels.join(', ')}` : 'No terms';
	}
	if (value === null || value === undefined) return '—';
	if (typeof value === 'boolean') return value ? 'Yes' : 'No';
	if (typeof value === 'object') return JSON.stringify(value);
	return String(value);
};

const mockChanges = (
	oldValue: Record<string, unknown> | null,
	newValue: Record<string, unknown> | null
): AuditChangeResponse[] => {
	const before = oldValue ?? {};
	const after = newValue ?? {};
	const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
	const changes: AuditChangeResponse[] = [];
	for (const key of keys) {
		const from = before[key];
		const to = after[key];
		if (oldValue !== null && newValue !== null && JSON.stringify(from) === JSON.stringify(to))
			continue;
		if (oldValue === null && (to === null || to === undefined)) continue;
		if (newValue === null && (from === null || from === undefined)) continue;
		changes.push({
			field: key,
			label: MOCK_FIELD_LABELS[key] ?? key.replace(/_/g, ' '),
			before: oldValue === null ? '—' : mockValue(key, from),
			after: newValue === null ? '—' : mockValue(key, to),
		});
	}
	return changes;
};

const mockSubject = (
	row: Omit<AuditLogItemResponse, 'actor' | 'subject' | 'summary' | 'action_label' | 'changes'>
): { label: string; sublabel: string | null } => {
	const s = row.new_value ?? row.old_value ?? {};
	const str = (v: unknown) => (typeof v === 'string' ? v : '');
	const importCaption = () => {
		const imported = s.imported;
		if (typeof imported !== 'number') return null;
		return `${imported} imported · ${Number(s.duplicates ?? 0)} already existed · ${Number(s.errors ?? 0)} errors`;
	};
	// A batch row has no id: it describes an import, not a record.
	if (row.entity_id === null && s.imported !== undefined) {
		const kind =
			row.entity_type === 'program'
				? 'Program'
				: row.entity_type === 'course'
					? 'Course'
					: row.entity_type === 'student'
						? 'Student'
						: row.entity_type === 'professor'
							? 'Professor'
							: 'Record';
		return { label: `${kind} import`, sublabel: importCaption() };
	}
	switch (row.entity_type) {
		case 'program':
			return { label: `${str(s.code)} · ${str(s.name)}`, sublabel: str(s.description) || null };
		case 'course':
			return { label: `${str(s.course_code)} · ${str(s.course_name)}`, sublabel: `${String(s.units ?? '')} units` };
		case 'student':
			return {
				label: `${str(s.student_id)} · ${str(s.first_name)} ${str(s.last_name)}`,
				sublabel: str(s.email) || null,
			};
		case 'professor':
			return { label: `${str(s.first_name)} ${str(s.last_name)}`, sublabel: str(s.email) || null };
		case 'year_level':
			return { label: str(s.label), sublabel: null };
		case 'session':
			return { label: str(s.session_code), sublabel: 'Lecture' };
		case 'excuse':
			return { label: `Excuse request #${row.entity_id}`, sublabel: str(s.reason) || null };
		case 'course_professor':
			return {
				label: `Professor #${String(s.professor_id ?? '')} → offering #${String(s.offering_id ?? '')}`,
				sublabel: s.is_primary === true ? 'Primary' : 'Assistant',
			};
		case 'user':
			return { label: str(s.email) || `User #${row.entity_id}`, sublabel: str(s.role) || null };
		case 'backup':
			return { label: str(s.filename), sublabel: `${str(s.kind)} · ${String(s.size_bytes ?? '')} bytes` };
		case 'face_enrollment':
			return { label: `Face template #${row.entity_id}`, sublabel: null };
		case 'app_setting':
			return { label: 'System settings', sublabel: Object.keys(s).join(', ') };
		case 'maintenance':
			return { label: 'Maintenance run', sublabel: null };
		case 'enrollment':
			return {
				label: row.entity_id === null ? 'Bulk enrollment' : `Enrollment #${row.entity_id}`,
				sublabel: null,
			};
		case 'course_offering':
			return {
				label: `Course #${String(s.course_id ?? '')}`,
				sublabel: `${str(s.semester)} Sem · ${str(s.academic_year)}`,
			};
		case 'offering_component':
			return {
				label: `Schedule component of offering #${String(s.offering_id ?? '')}`,
				sublabel: mockValue('schedule_days', s.schedule_days),
			};
		case 'attendance_record':
			return { label: `Attendance record #${row.entity_id}`, sublabel: null };
		default:
			return { label: `${row.entity_type} #${row.entity_id}`, sublabel: null };
	}
};

const mockAuditRow = (
	stored: Omit<AuditLogItemResponse, 'actor' | 'subject' | 'summary' | 'action_label' | 'changes'>
): AuditLogItemResponse => {
	const actor = stored.performed_by === null ? undefined : MOCK_ACTORS[stored.performed_by];
	const subject = mockSubject(stored);
	const actionLabel = MOCK_ACTION_LABELS[stored.action] ?? stored.action.replace(/_/g, ' ');
	return {
		...stored,
		actor: actor
			? {
					kind: 'user',
					id: actor === MOCK_ACTORS[stored.performed_by!] ? stored.performed_by : null,
					name: actor.name,
					email: actor.email,
					role: actor.role,
				}
			: { kind: 'anonymous', id: null, name: 'No signed-in user', email: null, role: null },
		subject: {
			type: stored.entity_type,
			id: stored.entity_id,
			label: subject.label,
			sublabel: subject.sublabel,
		},
		summary: `${actionLabel} ${subject.label}`,
		action_label: actionLabel,
		changes: mockChanges(stored.old_value, stored.new_value),
	};
};

const MOCK_AUDIT_ROWS: AuditLogItemResponse[] = [
	mockAuditRow({
		id: 1,
		action: 'open',
		entity_type: 'session',
		entity_id: 41,
		old_value: null,
		new_value: {
			offering_id: 3,
			professor_id: 3,
			session_type: 'lecture',
			session_code: '482913',
			scheduled_start_time: '2026-10-20T08:00:00+00:00',
			scheduled_end_time: '2026-10-20T09:00:00+00:00',
			expires_at: '2026-10-20T09:15:00+00:00',
		},
		performed_by: 3,
		performed_at: mockAuditAt(0, '08:55:00'),
	}),
	mockAuditRow({
		id: 2,
		action: 'import',
		entity_type: 'student',
		entity_id: null,
		old_value: null,
		new_value: { imported: 25, duplicates: 0, errors: 2 },
		performed_by: 2,
		performed_at: mockAuditAt(0, '08:30:00'),
	}),
	mockAuditRow({
		id: 3,
		action: 'update',
		entity_type: 'year_level',
		entity_id: 2,
		old_value: {
			program_id: 1,
			year_number: 2,
			label: '2nd Year',
			term_structure: {
				terms: [
					{ code: '1st', label: '1st Semester' },
					{ code: '2nd', label: '2nd Semester' },
				],
			},
			sort_order: 2,
		},
		new_value: {
			program_id: 1,
			year_number: 2,
			label: '2nd Year',
			term_structure: {
				terms: [
					{ code: '1st', label: '1st Semester' },
					{ code: '2nd', label: '2nd Semester' },
					{ code: 'mid', label: 'Midyear' },
				],
			},
			sort_order: 2,
		},
		performed_by: 1,
		performed_at: mockAuditAt(0, '08:00:00'),
	}),
	mockAuditRow({
		id: 4,
		action: 'approve',
		entity_type: 'excuse',
		entity_id: 7,
		old_value: {
			student_id: 4,
			session_id: 41,
			initiated_by: 'student',
			initiated_via: 'request',
			reason: 'Medical appointment',
			attachment_count: 1,
			status: 'pending',
			reviewed_by: null,
			review_notes: null,
		},
		new_value: {
			student_id: 4,
			session_id: 41,
			initiated_by: 'student',
			initiated_via: 'request',
			reason: 'Medical appointment',
			attachment_count: 1,
			status: 'approved',
			reviewed_by: 3,
			review_notes: 'Medical certificate verified.',
		},
		performed_by: 3,
		performed_at: mockAuditAt(1, '15:20:00'),
	}),
	mockAuditRow({
		id: 5,
		action: 'assign',
		entity_type: 'course_professor',
		entity_id: null,
		old_value: null,
		new_value: {
			offering_id: 3,
			professor_id: 3,
			is_primary: true,
			effective_from: '2026-08-01',
			effective_to: null,
		},
		performed_by: 2,
		performed_at: mockAuditAt(1, '14:05:00'),
	}),
	mockAuditRow({
		id: 6,
		action: 'update',
		entity_type: 'maintenance',
		entity_id: null,
		old_value: null,
		new_value: { processed: 90, succeeded: 88, failed: 2 },
		performed_by: null,
		performed_at: mockAuditAt(1, '11:47:00'),
	}),
	mockAuditRow({
		id: 7,
		action: 'enroll',
		entity_type: 'enrollment',
		entity_id: null,
		old_value: null,
		new_value: { offering_id: 3, enrolled: 3, skipped: 1, errors: 0 },
		performed_by: 2,
		performed_at: mockAuditAt(2, '16:33:00'),
	}),
	mockAuditRow({
		id: 8,
		action: 'update',
		entity_type: 'face_enrollment',
		entity_id: 4,
		old_value: { enrolled: false, face_enrolled_at: null, face_embedding_version: 0 },
		new_value: {
			enrolled: true,
			face_enrolled_at: '2026-10-18T10:12:00+00:00',
			face_embedding_version: 2,
		},
		performed_by: 4,
		performed_at: mockAuditAt(2, '10:12:00'),
	}),
	mockAuditRow({
		id: 9,
		action: 'create',
		entity_type: 'backup',
		entity_id: 31,
		old_value: null,
		new_value: {
			kind: 'full',
			filename: 'attendance_2026-10-17.dump.gz',
			status: 'completed',
			size_bytes: 43008000,
			storage_backend: 'local',
			sha256: '9f2c1ab4de7056f8e3c1b0a9d4e7f2c8b5a6d1e0f3c2b9a8d7e6f5c4b3a2d1e0f9',
		},
		performed_by: null,
		performed_at: mockAuditAt(3, '03:00:00'),
	}),
	mockAuditRow({
		id: 10,
		action: 'close',
		entity_type: 'session',
		entity_id: 38,
		old_value: {
			offering_id: 2,
			professor_id: 3,
			session_type: 'lecture',
			session_code: '775104',
			scheduled_start_time: '2026-10-17T08:00:00+00:00',
			scheduled_end_time: '2026-10-17T09:00:00+00:00',
			expires_at: '2026-10-17T09:15:00+00:00',
		},
		new_value: {
			offering_id: 2,
			professor_id: 3,
			session_type: 'lecture',
			session_code: '775104',
			scheduled_start_time: '2026-10-17T08:00:00+00:00',
			scheduled_end_time: '2026-10-17T09:00:00+00:00',
			expires_at: '2026-10-17T09:15:00+00:00',
		},
		performed_by: 3,
		performed_at: mockAuditAt(3, '09:44:00'),
	}),
	mockAuditRow({
		id: 11,
		action: 'lock',
		entity_type: 'user',
		entity_id: 4,
		old_value: {
			failed_login_attempts: 4,
			is_locked: false,
			is_permanently_locked: false,
			locked_at: null,
			must_change_password: true,
		},
		new_value: {
			failed_login_attempts: 5,
			is_locked: true,
			locked_at: '2026-10-16T13:29:00+00:00',
			must_change_password: true,
		},
		performed_by: null,
		performed_at: mockAuditAt(4, '13:29:00'),
	}),
	mockAuditRow({
		id: 12,
		action: 'login_failed',
		entity_type: 'user',
		entity_id: 4,
		old_value: {
			failed_login_attempts: 4,
			is_locked: false,
			locked_at: null,
			must_change_password: true,
		},
		new_value: {
			failed_login_attempts: 5,
			is_locked: false,
			locked_at: null,
			must_change_password: true,
		},
		performed_by: null,
		performed_at: mockAuditAt(4, '13:24:00'),
	}),
	mockAuditRow({
		id: 13,
		action: 'update',
		entity_type: 'offering_component',
		entity_id: 7,
		old_value: {
			offering_id: 2,
			session_type: 'lecture',
			schedule_days: 'MW',
			schedule_start_time: '08:00:00',
			schedule_end_time: '09:00:00',
			classroom_name: 'Room 201',
			classroom_lat: 14.5995,
			classroom_lng: 120.9842,
			is_active: true,
		},
		new_value: {
			offering_id: 2,
			session_type: 'lecture',
			schedule_days: 'MW',
			schedule_start_time: '09:00:00',
			schedule_end_time: '10:00:00',
			classroom_name: 'Room 201',
			classroom_lat: 14.5995,
			classroom_lng: 120.9842,
			is_active: true,
		},
		performed_by: 2,
		performed_at: mockAuditAt(5, '10:02:00'),
	}),
	mockAuditRow({
		id: 14,
		action: 'archive',
		entity_type: 'course',
		entity_id: 4,
		old_value: {
			course_code: 'CS102',
			course_name: 'Data Structures',
			units: 3,
			session_duration_hours: 1.5,
			is_active: true,
		},
		new_value: {
			course_code: 'CS102',
			course_name: 'Data Structures',
			units: 3,
			session_duration_hours: 1.5,
			is_active: false,
		},
		performed_by: 1,
		performed_at: mockAuditAt(5, '09:15:00'),
	}),
	mockAuditRow({
		id: 15,
		action: 'create',
		entity_type: 'excuse',
		entity_id: 6,
		old_value: null,
		new_value: {
			student_id: 4,
			session_id: 38,
			initiated_by: 'professor',
			initiated_via: 'quick_excuse',
			reason: 'Family emergency',
			attachment_count: 0,
			status: 'pending',
			reviewed_by: null,
			review_notes: null,
		},
		performed_by: 3,
		performed_at: mockAuditAt(6, '14:51:00'),
	}),
	mockAuditRow({
		id: 16,
		action: 'create',
		entity_type: 'course',
		entity_id: 2,
		old_value: null,
		new_value: {
			course_code: 'CS102',
			course_name: 'Data Structures',
			units: 3,
			session_duration_hours: 1.5,
			is_active: true,
		},
		performed_by: 2,
		performed_at: mockAuditAt(7, '08:05:00'),
	}),
	mockAuditRow({
		id: 17,
		action: 'create',
		entity_type: 'course_offering',
		entity_id: 3,
		old_value: null,
		new_value: {
			course_id: 2,
			program_id: 2,
			year_level_id: 3,
			semester: '1st',
			academic_year: '2026-2027',
			sessions_per_week: 2,
			schedule_days: 'MW',
			schedule_start_time: '08:00:00',
			schedule_end_time: '09:30:00',
			classroom_name: 'Lab 1',
			classroom_lat: 14.5996,
			classroom_lng: 120.9843,
			default_present_window_minutes: 5,
			default_late_window_minutes: 10,
			default_classroom_radius_meters: null,
			is_active: true,
		},
		performed_by: 2,
		performed_at: mockAuditAt(7, '08:02:00'),
	}),
	mockAuditRow({
		id: 18,
		action: 'unassign',
		entity_type: 'course_professor',
		entity_id: null,
		old_value: {
			offering_id: 3,
			professor_id: 3,
			is_primary: true,
			effective_from: '2026-08-01',
			effective_to: null,
		},
		new_value: {
			offering_id: 3,
			professor_id: 3,
			is_primary: true,
			effective_from: '2026-08-01',
			effective_to: '2026-10-16',
		},
		performed_by: 2,
		performed_at: mockAuditAt(9, '12:18:00'),
	}),
	mockAuditRow({
		id: 19,
		action: 'update',
		entity_type: 'app_setting',
		entity_id: null,
		old_value: { present_window_default: '5' },
		new_value: { present_window_default: '10' },
		performed_by: 1,
		performed_at: mockAuditAt(10, '09:31:00'),
	}),
	mockAuditRow({
		id: 20,
		action: 'password_reset',
		entity_type: 'user',
		entity_id: 4,
		old_value: {
			failed_login_attempts: 5,
			is_locked: true,
			locked_at: '2026-10-16T13:29:00+00:00',
			must_change_password: true,
		},
		new_value: {
			failed_login_attempts: 0,
			is_locked: false,
			locked_at: null,
			must_change_password: true,
		},
		performed_by: 1,
		performed_at: mockAuditAt(12, '08:10:00'),
	}),
	mockAuditRow({
		id: 21,
		action: 'create',
		entity_type: 'program',
		entity_id: 2,
		old_value: null,
		new_value: {
			code: 'BSIT',
			name: 'Bachelor of Science in Information Technology',
			description: 'Information Technology program',
			total_years: 4,
			is_active: true,
		},
		performed_by: 1,
		performed_at: mockAuditAt(12, '07:40:00'),
	}),
	mockAuditRow({
		id: 22,
		action: 'update',
		entity_type: 'program',
		entity_id: 2,
		old_value: {
			code: 'BSIT',
			name: 'BS Information Technology',
			description: 'Information Technology program',
			total_years: 4,
			is_active: true,
		},
		new_value: {
			code: 'BSIT',
			name: 'Bachelor of Science in Information Technology',
			description: 'Information Technology program',
			total_years: 4,
			is_active: true,
		},
		performed_by: 1,
		performed_at: mockAuditAt(12, '07:45:00'),
	}),
	mockAuditRow({
		id: 23,
		action: 'unenroll',
		entity_type: 'enrollment',
		entity_id: 55,
		old_value: {
			offering_id: 3,
			student_id: '2024-0001',
			semester: '1st',
			academic_year: '2026-2027',
		},
		new_value: null,
		performed_by: 2,
		performed_at: mockAuditAt(13, '10:05:00'),
	}),
	mockAuditRow({
		id: 24,
		action: 'delete',
		entity_type: 'program',
		entity_id: 5,
		old_value: {
			code: 'BSED',
			name: 'Bachelor of Science in Education',
			description: null,
			total_years: 4,
			is_active: false,
		},
		new_value: null,
		performed_by: 1,
		performed_at: mockAuditAt(15, '16:20:00'),
	}),
	mockAuditRow({
		id: 25,
		action: 'create',
		entity_type: 'student',
		entity_id: 12,
		old_value: null,
		new_value: {
			student_id: '2024-0001',
			first_name: 'Juan',
			last_name: 'Dela Cruz',
			email: 'juan.delacruz@isu.edu.ph',
			year_level_id: 3,
			section: 'A',
			is_active: true,
			face_enrolled_at: null,
		},
		performed_by: 2,
		performed_at: mockAuditAt(2, '09:15:00'),
	}),
	mockAuditRow({
		id: 26,
		action: 'create',
		entity_type: 'professor',
		entity_id: 8,
		old_value: null,
		new_value: {
			email: 'maria.garcia@isu.edu.ph',
			first_name: 'Maria',
			last_name: 'Garcia',
			department: 'Computer Science',
			is_active: true,
		},
		performed_by: 1,
		performed_at: mockAuditAt(4, '10:15:00'),
	}),
];

// Academic-structure changes mirror api-contracts
// GET /admin/system/academic-structure exactly (D38).
//
// The same contract shape as the trail: dict snapshots, a numeric actor, and
// actions drawn from `AuditAction`. The structural rows are a subset of the
// trail — the server returns program/year/course/offering rows on BOTH
// endpoints — so the fixtures below reuse the trail's structural rows rather
// than inventing a parallel set.
const MOCK_STRUCTURE_ROWS: StructureChangeResponse[] = MOCK_AUDIT_ROWS.filter((r) =>
	(
		[
			'program',
			'year_level',
			'course',
			'course_offering',
			'offering_component',
		] as const
	).includes(r.entity_type as 'program')
);

// --- Admin users (super_admin only) -------------------------------------------
//
// Mirrors backend/src/features/admin/router.py (prefix /admin/users, mounted
// once in api/router.py): GET "" list (search/role/is_active/page/size),
// POST "" create (201 + temp_password once), PATCH /{id}/deactivate (204,
// self-deactivation rejected). Creatable roles are admin/professor/student —
// super_admin is seeded, never created via API. Real API by default; mocks
// only when PUBLIC_MOCK_MODE=true.

// Seeded super_admin account for mock mode (frontend-only; the real first
// super_admin is seeded at deployment and the backend is untouched here).
// Mock login accepts this email with any non-empty password (see
// features/auth/mock.ts MOCK_SUPER_ADMIN).
const MOCK_ADMIN_USER_ROWS: AdminUserResponse[] = [
	{
		id: 1,
		email: 'superadmin@isu.edu.ph',
		role: 'super_admin',
		first_name: 'Super',
		last_name: 'Admin',
		is_active: true,
		must_change_password: false,
		last_login: null,
		created_at: '2025-08-01T08:00:00.000Z',
	},
	{
		id: 2,
		email: 'admin@isu.edu.ph',
		role: 'admin',
		first_name: 'Admin',
		last_name: 'User',
		is_active: true,
		must_change_password: false,
		last_login: null,
		created_at: '2025-08-15T08:00:00.000Z',
	},
	{
		id: 3,
		email: 'maria.c.delacruz@isu.edu.ph',
		role: 'professor',
		first_name: 'Maria',
		last_name: 'Dela Cruz',
		is_active: true,
		must_change_password: false,
		last_login: null,
		created_at: '2025-09-01T08:00:00.000Z',
	},
	{
		id: 4,
		email: 'juan.delacruz@isu.edu.ph',
		role: 'student',
		first_name: 'Juan',
		last_name: 'Dela Cruz',
		is_active: false,
		must_change_password: true,
		last_login: null,
		created_at: '2025-09-15T08:00:00.000Z',
	},
];

const mockAdminUsersList = (
	params?: Record<string, string>
): Paginated<AdminUserResponse> => {
	let rows = [...MOCK_ADMIN_USER_ROWS];
	const search = params?.search?.trim().toLowerCase();
	if (search) {
		rows = rows.filter((r) =>
			`${r.email} ${r.first_name ?? ''} ${r.last_name ?? ''}`
				.toLowerCase()
				.includes(search)
		);
	}
	if (params?.role) {
		rows = rows.filter((r) => r.role === params.role);
	}
	if (params?.is_active !== undefined) {
		const active = params.is_active === 'true';
		rows = rows.filter((r) => r.is_active === active);
	}
	rows.sort((a, b) => a.id - b.id);
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

interface MockAdminUserPayload {
	email?: unknown;
	role?: unknown;
	first_name?: unknown;
	middle_name?: unknown;
	last_name?: unknown;
}

// --- Admin password reset (three rosters, one backend implementation) ----------
//
// POST /admin/users/{id}/reset-password names a `users.id` directly;
// POST /admin/students/{id}/reset-password and
// POST /admin/professors/{id}/reset-password name a roster row, which the
// backend resolves to a `users.id` before calling the same
// `AuthService.admin_reset_password`. So all three return one shape and there
// is no reason for the client to treat them differently.
//
// Three defs rather than one keyed by roster because the url is baked into
// EndpointDef and only the collection prefix is shared. Role gate differs
// too: the users route is super_admin, the roster two are admin (which
// super_admin also passes).
//
// The response's `temp_password` is returned exactly once — there is no
// endpoint to read it back — so the mock returns a plausible one and the UI
// must present it inline rather than storing it.
const mockTempPassword = (): AdminPasswordResetResponse => ({
	temp_password: `Temp-${Math.random().toString(36).slice(2, 10)}!`,
});

const MOCK_LIVENESS_ROWS: LivenessReviewItemResponse[] = [
	{ id: 501, student_number: '24-2132', student_name: 'Alice Santos', session_code: 'A7X-9K2M', course_code: 'CS101', face_match_score: 0.67, evidence: { review: true, blink_detected: true, head_turn_left: true, head_turn_right: true }, scanned_at: new Date().toISOString() },
	{ id: 502, student_number: '24-1045', student_name: 'Bob Cruz', session_code: 'B3M-7Q8N', course_code: 'MATH101', face_match_score: 0.68, evidence: { review: true, blink_detected: true, head_turn_left: true, head_turn_right: false }, scanned_at: new Date().toISOString() },
];

export const mockSessionQR: NonNullable<(typeof defs.SessionQREndpoint)['mock']> = () => ({
	session_id: 1,
	offering_id: 1,
	session_type: 'lecture' as const,
	course_code: 'CS101',
	course_name: 'Software Engineering 1',
	program_code: 'BSCS',
	year_level_label: 'Year 1',
	expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
	scheduled_start_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
	scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
	geofence: {
		radius: 50,
		lat: 13.7563,
		lng: 100.5018,
	},
	present_window_minutes: 15,
	late_window_minutes: 5,
});

export const mockAttendanceScan: NonNullable<(typeof defs.AttendanceScanEndpoint)['mock']> = () => ({
	id: 1,
	status: 'present',
	scanned_at: new Date().toISOString(),
	expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
});

export const mockAttendancePrecheck: NonNullable<(typeof defs.AttendancePrecheckEndpoint)['mock']> = (_params, _suffix, body) => {
	const p = (body ?? {}) as { student_number?: unknown };
	const studentNumber = String(p.student_number ?? '').trim().toUpperCase() || '24-0001';
	return {
		enrolled: true,
		already_scanned: false,
		student: { student_id: studentNumber, name: 'Jose Rizal', section: 'A' },
	};
};

export const mockSessionList: NonNullable<(typeof defs.SessionListEndpoint)['mock']> = () => ({
	items: [
		{
			id: 1,
			offering_id: 1,
			session_type: 'lecture' as const,
			session_code: '7X-9K2M',
			created_at: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
			expires_at: new Date(Date.now() + 40 * 60 * 1000).toISOString(),
			scheduled_end_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
			duration_minutes: 60,
			present_count: 15,
			late_count: 3,
			absent_count: 2,
			pending_count: 0,
			status: 'active',
		},
	],
	total: 1,
	page: 1,
	size: 20,
});

export const mockSessionCreate: NonNullable<(typeof defs.SessionCreateEndpoint)['mock']> = (_params, _suffix, body) => {
	mockSessionSeq += 1;
	const id = mockSessionSeq;
	const sessionCode = mockSessionCode(id);
	mockSessions.set(id, sessionCode);
	return {
		id,
		session_code: sessionCode,
		offering_id: 1,
		session_type:
			(body as { session_type?: unknown } | undefined)?.session_type === 'lab'
				? ('lab' as const)
				: ('lecture' as const),
		is_remote: (body as { is_remote?: unknown } | undefined)?.is_remote === true,
		qr_payload: {
			v: 1,
			code: sessionCode,
			offering: 1,
			radius: 50,
			pw: 15,
			lw: 5,
		},
		expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
		scheduled_start_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString(),
		// D93/D94: either schedule field marks the session as overridden.
		schedule_overridden:
			(body as { session_date?: unknown; start_time?: unknown } | undefined)
				?.session_date !== undefined ||
			(body as { start_time?: unknown } | undefined)?.start_time !== undefined,
		plan_source: 'component',
		actual_start_time: new Date().toISOString(),
		original_scheduled_start_time: null,
		override_reason:
			((body as { override_reason?: unknown } | undefined)?.override_reason as
				| string
				| null) ?? null,
		created_at: new Date().toISOString(),
	};
};

export const mockSessionHistory: NonNullable<(typeof defs.SessionHistoryEndpoint)['mock']> = () => ({
	items: [],
	total: 0,
	page: 1,
	size: 20,
});

export const mockSessionActive: NonNullable<(typeof defs.SessionActiveEndpoint)['mock']> = (_params, suffix) => {
	const match = suffix?.match(/\/(\d+)/);
	const id = match ? parseInt(match[1], 10) : 1;
	return {
		id,
		offering: 1,
		session_type: 'lecture' as const,
		session_code: mockSessions.get(id) ?? '7X-9K2M',
		scan_window_remaining: 2400,
		scheduled_start_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
		scheduled_end_time: new Date(Date.now() + 40 * 60 * 1000).toISOString(),
		expires_at: null,
		program_code: 'BSCS',
		year_level_label: '1st Year',
		status: 'active',
		enrolled_count: 30,
		remaining: 12,
		pending_sync_count: 0,
		students: [],
		counts: { present: 15, late: 3, pending: 10, absent: 2, excused: 0 },
	};
};

export const mockSessionClose: NonNullable<(typeof defs.SessionCloseEndpoint)['mock']> = (_params, suffix) => {
	const match = suffix?.match(/\/(\d+)\/close/);
	const ids = [...mockSessions.keys()];
	const id = match ? parseInt(match[1], 10) : (ids.pop() ?? 0);
	return {
		id,
		status: 'closed' as const,
		final_counts: { present: 0, late: 0, pending: 0, absent: 0, excused: 0 },
	};
};

export const mockAttendanceList: NonNullable<(typeof defs.AttendanceListEndpoint)['mock']> = () => ({
	items: [],
	total: 0,
	page: 1,
	size: 20,
});

export const mockAuthOtpRequest: NonNullable<(typeof defs.AuthOtpRequestEndpoint)['mock']> = () => undefined;

export const mockAuthOtpVerify: NonNullable<(typeof defs.AuthOtpVerifyEndpoint)['mock']> = () => undefined;

export const mockAuthRegister: NonNullable<(typeof defs.AuthRegisterEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthLogin: NonNullable<(typeof defs.AuthLoginEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthLoginOtpVerify: NonNullable<(typeof defs.AuthLoginOtpVerifyEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthLoginOtpResend: NonNullable<(typeof defs.AuthLoginOtpResendEndpoint)['mock']> = () => undefined;

export const mockAuthRefresh: NonNullable<(typeof defs.AuthRefreshEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthMe: NonNullable<(typeof defs.AuthMeEndpoint)['mock']> = () => ({
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
});

export const mockAuthMfaVerify: NonNullable<(typeof defs.AuthMfaVerifyEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthMfaSetup: NonNullable<(typeof defs.AuthMfaSetupEndpoint)['mock']> = () => ({
	// Valid base32 so an authenticator-app-shaped secret is still usable in
	// mock mode. Matches the backend's 16-char pyotp.random_base32().
	secret: 'JBSWY3DPEB2XS2LP',
	qr_url:
		'otpauth://totp/Attendly:student@example.com?secret=JBSWY3DPEB2XS2LP&issuer=Attendly',
	manual_entry_key: 'JBSWY3DPEB2XS2LP',
});

export const mockAuthMfaDisable: NonNullable<(typeof defs.AuthMfaDisableEndpoint)['mock']> = () => undefined;

export const mockAuthMfaBackupCodesGenerate: NonNullable<(typeof defs.AuthMfaBackupCodesGenerateEndpoint)['mock']> = () => ({
	codes: Array.from({ length: 10 }, (_, i) => `MOCKC-${String(i).padStart(4, '0')}-CODE`),
	remaining: 10,
});

export const mockAuthMfaBackupCodesSummary: NonNullable<(typeof defs.AuthMfaBackupCodesSummaryEndpoint)['mock']> = () => ({ total: 0, remaining: 0, last_generated_at: null });

export const mockAuthChangePassword: NonNullable<(typeof defs.AuthChangePasswordEndpoint)['mock']> = () => undefined;

export const mockAuthLogout: NonNullable<(typeof defs.AuthLogoutEndpoint)['mock']> = () => undefined;

export const mockAuthSessionPolicy: NonNullable<(typeof defs.AuthSessionPolicyEndpoint)['mock']> = () => ({ idle_timeout_minutes: 45, idle_warning_minutes: 5 });

export const mockForgotPassword: NonNullable<(typeof defs.ForgotPasswordEndpoint)['mock']> = () => ({
	question: 'What was the name of your first pet?',
	set: true,
});

export const mockForgotPasswordVerify: NonNullable<(typeof defs.ForgotPasswordVerifyEndpoint)['mock']> = () => ({ recovery_token: 'mock-recovery-token' });

export const mockResetPassword: NonNullable<(typeof defs.ResetPasswordEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockAuthPasswordRecoveryStart: NonNullable<(typeof defs.AuthPasswordRecoveryStartEndpoint)['mock']> = () => ({ recovery_token: 'mock-recovery-token', masked_email: 'j***@example.com' });

export const mockAuthPasswordRecoveryReset: NonNullable<(typeof defs.AuthPasswordRecoveryResetEndpoint)['mock']> = () => MOCK_TOKENS;

export const mockSecurityQuestion: NonNullable<(typeof defs.SecurityQuestionEndpoint)['mock']> = () => undefined;

export const mockRecoveryCode: NonNullable<(typeof defs.RecoveryCodeEndpoint)['mock']> = () => undefined;

export const mockStudentProfile: NonNullable<(typeof defs.StudentProfileEndpoint)['mock']> = () => ({
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
});

export const mockStudentDashboard: NonNullable<(typeof defs.StudentDashboardEndpoint)['mock']> = () => ({
	compliance_rate: 0,
	scans_today: 0,
	total_scans: 0,
	today_schedule: [],
	recent_activity: [],
});

export const mockAdminDashboard: NonNullable<(typeof defs.AdminDashboardEndpoint)['mock']> = () => ({
	student_count: 0,
	professor_count: 0,
	program_count: 0,
	avg_rate: 0,
	scans_today: 0,
	pending_sync: 0,
	recent_scans: [],
});

export const mockProfessorDashboard: NonNullable<(typeof defs.ProfessorDashboardEndpoint)['mock']> = () => ({
	sessions_today: 0,
	sessions_completed: 0,
	total_students: 0,
	avg_rate: 0,
	today_sessions: [],
});

export const mockStudentHistory: NonNullable<(typeof defs.StudentHistoryEndpoint)['mock']> = () => ({
	items: [],
	total: 0,
	page: 1,
	size: 20,
	summary: {
		compliance_rate: 0,
		participation_rate: 0,
		counts: { present: 0, late: 0, absent: 0, excused: 0, rejected: 0 },
	},
});

export const mockStudentExcuseSubmit: NonNullable<(typeof defs.StudentExcuseSubmitEndpoint)['mock']> = (_params, _suffix, body) => {
	const input = (body ?? {}) as StudentExcuseSubmitBody;
	const urls = [...(input.attachment_urls ?? [])];
	const id = Math.floor(Math.random() * 10000) + 1;
	MOCK_STUDENT_EXCUSE_ROWS.unshift({
		id,
		student_id: 1,
		session_id: input.session_id ?? 0,
		initiated_by: 'student',
		initiated_via: 'request',
		reason: input.reason ?? '',
		attachment_urls: urls,
		status: 'pending',
		requested_at: new Date().toISOString(),
		reviewed_by: null,
		reviewed_at: null,
		review_notes: null,
	});
	return {
		id,
		status: 'pending',
		requested_at: new Date().toISOString(),
	};
};

export const mockStudentExcuseList: NonNullable<(typeof defs.StudentExcuseListEndpoint)['mock']> = (params) => {
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
	return {
		items: MOCK_STUDENT_EXCUSE_ROWS.slice((page - 1) * size, page * size),
		total: MOCK_STUDENT_EXCUSE_ROWS.length,
		page,
		size,
	};
};

export const mockStudentExcuseDetail: NonNullable<(typeof defs.StudentExcuseDetailEndpoint)['mock']> = (_params, suffix) => ({
	id: parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '0', 10) || 0,
	student_id: 0,
	session_id: 0,
	initiated_by: 'student',
	initiated_via: 'request',
	reason: '',
	attachment_urls: null,
	status: 'pending',
	requested_at: new Date().toISOString(),
	reviewed_by: null,
	reviewed_at: null,
	review_notes: null,
});

export const mockUploadPresigned: NonNullable<(typeof defs.UploadPresignedEndpoint)['mock']> = (_params, _suffix, body) => {
	const input = (body ?? {}) as PresignedUrlRequest;
	const safe = String(input.filename ?? 'evidence').replace(/[^a-zA-Z0-9._-]+/g, '-');
	return {
		upload_url: `mock://upload/${safe}`,
		object_url: `mock://attachments/${safe}`,
		object_key: `attachments/${safe}`,
		expires_in: 3600,
	};
};

export const mockStudentFaceEmbedding: NonNullable<(typeof defs.StudentFaceEmbeddingEndpoint)['mock']> = () => undefined;

export const mockStudentSchedule: NonNullable<(typeof defs.StudentScheduleEndpoint)['mock']> = () => ({
	offerings: [
		{
			offering_id: 1,
			course_id: 1,
			course_code: 'CS101',
			course_name: 'Software Engineering 1',
			program_code: 'BSCS',
			year_level_label: '1st Year',
			semester: '1st Sem 2025-2026',
			schedule_days: 'MWF',
			schedule_start_time: '09:00:00',
			schedule_end_time: '10:30:00',
			classroom_name: 'Room 301',
			professor_name: 'John Smith',
		},
		{
			offering_id: 2,
			course_id: 2,
			course_name: 'Data Structures',
			course_code: 'CS102',
			program_code: 'BSCS',
			year_level_label: '1st Year',
			semester: '1st Sem 2025-2026',
			schedule_days: 'TH',
			schedule_start_time: '13:00:00',
			schedule_end_time: '14:30:00',
			classroom_name: null,
			professor_name: null,
		},
	],
});

export const mockProfessorProfile: NonNullable<(typeof defs.ProfessorProfileEndpoint)['mock']> = () => ({
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
});

export const mockSessionPlan: NonNullable<(typeof defs.SessionPlanEndpoint)['mock']> = () => ({
	offering_id: 1,
	session_type: 'lecture',
	source: 'component',
	session_date: null,
	start_time: '09:00:00',
	end_time: '10:30:00',
	scheduled_start: null,
	scheduled_end: null,
	timezone: 'UTC',
	duration_minutes: 90,
	present_window_minutes: 5,
	late_window_minutes: 10,
	classroom_name: 'Room 101',
	classroom_lat: 13.7563,
	classroom_lng: 100.5018,
	radius_meters: 50,
	override_capable: true,
	start_window: {
		permitted: true,
		reason: null,
		scheduled_date: null,
		start_time: '09:00:00',
		end_time: '10:30:00',
		scheduled_start: null,
		scheduled_end: null,
		opens_at: null,
		closes_at: null,
		current_time: new Date().toISOString(),
		timezone: 'UTC',
		early_open_minutes: 30,
		late_open_minutes: 0,
	},
});

export const mockProfessorOfferingStudents: NonNullable<(typeof defs.ProfessorOfferingStudentsEndpoint)['mock']> = (params) => {
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const rows: AdminRosterItemResponse[] = [
		{
			id: 1,
			student_id: 'S001',
			name: 'Ada Lovelace',
			email: 'ada@example.com',
			section: 'A',
			enrolled_at: new Date().toISOString(),
		},
	];
	const total = rows.length;
	const page = 1;
	return { items: rows, total, page, size };
};

export const mockProfessorCourses: NonNullable<(typeof defs.ProfessorCoursesEndpoint)['mock']> = () => ({
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
			schedule_days: 'MWF',
			schedule_start_time: '09:00:00',
			schedule_end_time: '10:30:00',
			classroom_name: 'Room 101',
			classroom_lat: 13.7563,
			classroom_lng: 100.5018,
			default_present_window_minutes: 5,
			default_late_window_minutes: 10,
			default_classroom_radius_meters: null,
			session_types: ['lecture'],
			components: [
				{
					id: 1,
					session_type: 'lecture',
					schedule_days: 'MWF',
					schedule_start_time: '09:00:00',
					schedule_end_time: '10:30:00',
					classroom_name: 'Room 101',
					classroom_lat: 13.7563,
					classroom_lng: 100.5018,
				},
			],
			next_session_date: null,
			next_session_start: '09:00:00',
			next_session_end: '10:30:00',
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
});

export const mockAdminStudents: NonNullable<(typeof defs.AdminStudentsEndpoint)['mock']> = (params) => mockAdminStudentsList(params);

export const mockAdminStudentCreate: NonNullable<(typeof defs.AdminStudentCreateEndpoint)['mock']> = (_params, _suffix, body) => {
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
		program_id: Number(p.program_id),
		year_level_label: mockYearLabelFor(Number(p.year_level_id)),
		year_level_id: Number(p.year_level_id),
		section: p.section ? String(p.section) : null,
		is_active: true,
		claim_status: 'Unclaimed',
		face_enrolled: false,
		created_at: new Date().toISOString(),
		scan_count: 0,
	};
	MOCK_ADMIN_STUDENT_ROWS.push(row);
	return row;
};

export const mockAdminStudentDetail: NonNullable<(typeof defs.AdminStudentDetailEndpoint)['mock']> = (_params, suffix, body, method) => {
	if (method === 'DELETE') {
		const row = findMockStudentRow(suffix);
		if (row.is_active) throw new Error('Only inactive students can be deleted.');
		MOCK_ADMIN_STUDENT_ROWS.splice(MOCK_ADMIN_STUDENT_ROWS.indexOf(row), 1);
		return mockNoContent();
	}
	if (method === 'PATCH') {
		const row = findMockStudentRow(suffix);
		const p = (body ?? {}) as MockStudentPayload;
		if (p.first_name !== undefined) row.first_name = String(p.first_name);
		if (p.last_name !== undefined) row.last_name = String(p.last_name);
		if (p.email !== undefined) row.email = String(p.email).trim().toLowerCase();
		if (p.section !== undefined) row.section = p.section ? String(p.section) : null;
		if (typeof p.is_active === 'boolean') row.is_active = p.is_active;
		if (p.program_id !== undefined) {
			row.program_code = mockProgramCodeFor(Number(p.program_id));
			row.program_id = Number(p.program_id);
		}
		if (p.year_level_id !== undefined) {
			row.year_level_label = mockYearLabelFor(Number(p.year_level_id));
			row.year_level_id = Number(p.year_level_id);
		}
		return toMockDetail(row);
	}
	return toMockDetail(findMockStudentRow(suffix));
};

export const mockAdminStudentImport: NonNullable<(typeof defs.AdminStudentImportEndpoint)['mock']> = (_params, _suffix, body) => mockCsvImport(body, 25);

export const mockAdminFaceEnrollmentUpload: NonNullable<(typeof defs.AdminFaceEnrollmentUploadEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_STUDENT_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Student not found.');
	row.face_enrolled = true;
	const prior = MOCK_FACE_VERSIONS.get(id) ?? 1;
	const version = prior + 1;
	const at = new Date().toISOString();
	MOCK_FACE_VERSIONS.set(id, version);
	MOCK_FACE_ENROLLED_AT.set(id, at);
	return { student_id: id, face_enrolled_at: at, face_embedding_version: version };
};

export const mockAdminFaceEnrollmentStatus: NonNullable<(typeof defs.AdminFaceEnrollmentStatusEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_STUDENT_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Student not found.');
	if (!row.face_enrolled) return { enrolled: false };
	const at = MOCK_FACE_ENROLLED_AT.get(id);
	if (!at) return { enrolled: false };
	return {
		enrolled: true,
		face_enrolled_at: at,
		face_embedding_version: MOCK_FACE_VERSIONS.get(id) ?? 1,
	};
};

export const mockAdminFaceEnrollmentRevoke: NonNullable<(typeof defs.AdminFaceEnrollmentRevokeEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_STUDENT_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('Student not found.');
	row.face_enrolled = false;
	const prior = MOCK_FACE_VERSIONS.get(id) ?? 1;
	MOCK_FACE_VERSIONS.set(id, prior + 1);
	MOCK_FACE_ENROLLED_AT.delete(id);
	return undefined as void;
};

export const mockAdminProfessors: NonNullable<(typeof defs.AdminProfessorsEndpoint)['mock']> = (params) => mockAdminProfessorsList(params);

export const mockAdminProfessorCreate: NonNullable<(typeof defs.AdminProfessorCreateEndpoint)['mock']> = (_params, _suffix, body) => {
	const p = (body ?? {}) as MockProfessorPayload;
	const email = String(p.email ?? '').trim().toLowerCase();
	if (MOCK_ADMIN_PROFESSOR_ROWS.some((r) => r.email.toLowerCase() === email)) {
		throw new Error('Professor email already exists.');
	}
	const offeringIds = Array.isArray(p.courses)
		? [...new Set((p.courses as unknown[]).map((v) => Number(v)).filter((v) => Number.isInteger(v) && v > 0))]
		: [];
	const row: AdminProfessorResponse = {
		id: Math.max(...MOCK_ADMIN_PROFESSOR_ROWS.map((r) => r.id), 0) + 1,
		first_name: String(p.first_name ?? ''),
		middle_name: null,
		last_name: String(p.last_name ?? ''),
		email,
		department: p.department ? String(p.department) : null,
		is_active: true,
		claim_status: 'Unclaimed',
		assigned_courses: offeringIds.map((offering_id) => ({
			offering_id,
			course_code: mockCourseCodeFor(offering_id),
		})),
		created_at: new Date().toISOString(),
	};
	MOCK_ADMIN_PROFESSOR_ROWS.push(row);
	return row;
};

export const mockAdminProfessorDetail: NonNullable<(typeof defs.AdminProfessorDetailEndpoint)['mock']> = (_params, suffix, body, method) => {
	if (method === 'DELETE') {
		const row = findMockProfessorRow(suffix);
		if (row.is_active) throw new Error('Only inactive professors can be deleted.');
		MOCK_ADMIN_PROFESSOR_ROWS.splice(MOCK_ADMIN_PROFESSOR_ROWS.indexOf(row), 1);
		return mockNoContent();
	}
	if (method === 'PATCH') {
		const row = findMockProfessorRow(suffix);
		const p = (body ?? {}) as MockProfessorPayload;
		if (p.first_name !== undefined) row.first_name = String(p.first_name);
		if (p.last_name !== undefined) row.last_name = String(p.last_name);
		if (p.email !== undefined) row.email = String(p.email).trim().toLowerCase();
		if (p.department !== undefined)
			row.department = p.department ? String(p.department) : null;
		if (typeof p.is_active === 'boolean') row.is_active = p.is_active;
		if (p.courses !== undefined && Array.isArray(p.courses)) {
			const offeringIds = [
				...new Set(
					(p.courses as unknown[]).map((v) => Number(v)).filter((v) => Number.isInteger(v) && v > 0)
				),
			];
			row.assigned_courses = offeringIds.map((offering_id) => ({
				offering_id,
				course_code: mockCourseCodeFor(offering_id),
			}));
		}
		return row;
	}
	return findMockProfessorRow(suffix);
};

export const mockAdminProfessorImport: NonNullable<(typeof defs.AdminProfessorImportEndpoint)['mock']> = (_params, _suffix, body) => mockCsvImport(body, 5);

export const mockAdminOfferings: NonNullable<(typeof defs.AdminOfferingsEndpoint)['mock']> = (params) => {
	let rows = [...MOCK_ADMIN_OFFERINGS];
	// Full cascade mirrors the backend list query (program/year/semester/
	// course/status). Id params resolve against the numeric mock ids.
	if (params?.program_id) {
		rows = rows.filter((r) => String(r.program_id) === params.program_id);
	}
	if (params?.year_level_id) {
		rows = rows.filter((r) => String(r.year_level_id) === params.year_level_id);
	}
	if (params?.semester) {
		rows = rows.filter(
			(r) => r.semester.toLowerCase() === params.semester!.trim().toLowerCase()
		);
	}
	if (params?.course_id) {
		rows = rows.filter((r) => String(r.course_id) === params.course_id);
	}
	if (params?.is_active !== undefined) {
		const wantActive = params.is_active === 'true';
		rows = rows.filter((r) => r.is_active === wantActive);
	}
	const size = Math.min(Math.max(parseInt(params?.size ?? '50', 10) || 50, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

export const mockAdminCourses: NonNullable<(typeof defs.AdminCoursesEndpoint)['mock']> = (params) => {
	let rows = [...MOCK_ADMIN_COURSE_ROWS];
	if (params?.is_active !== undefined) {
		const wantActive = params.is_active === 'true';
		rows = rows.filter((r) => r.is_active === wantActive);
	}
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

export const mockAdminCourseCreate: NonNullable<(typeof defs.AdminCourseCreateEndpoint)['mock']> = (_params, _suffix, body) => {
	const p = (body ?? {}) as MockCoursePayload;
	const code = String(p.course_code ?? '').trim().toUpperCase();
	if (MOCK_ADMIN_COURSE_ROWS.some((r) => r.course_code === code)) {
		throw new Error('Course code already exists.');
	}
	const row: AdminCourseResponse = {
		id: Math.max(...MOCK_ADMIN_COURSE_ROWS.map((r) => r.id), 0) + 1,
		course_code: code,
		course_name: String(p.course_name ?? ''),
		units: Number(p.units ?? 3),
		session_duration_hours: Number(p.session_duration_hours ?? 1.5),
		course_type: p.course_type === 'lab' ? 'lab' : 'lecture',
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	};
	MOCK_ADMIN_COURSE_ROWS.push(row);
	return row;
};

export const mockAdminCourseDetail: NonNullable<(typeof defs.AdminCourseDetailEndpoint)['mock']> = (_params, suffix, body, method) => {
	if (method === 'DELETE') {
		const row = findMockCourseRow(suffix);
		if (row.is_active) throw new Error('Only inactive courses can be deleted.');
		MOCK_ADMIN_COURSE_ROWS.splice(MOCK_ADMIN_COURSE_ROWS.indexOf(row), 1);
		return mockNoContent();
	}
	if (method === 'PATCH') {
		const row = findMockCourseRow(suffix);
		const p = (body ?? {}) as MockCoursePayload;
		if (p.course_code !== undefined) {
			const code = String(p.course_code).trim().toUpperCase();
			if (
				code !== row.course_code &&
				MOCK_ADMIN_COURSE_ROWS.some((r) => r.course_code === code)
			) {
				throw new Error('Course code already exists.');
			}
			row.course_code = code;
		}
		if (p.course_name !== undefined) row.course_name = String(p.course_name);
		if (p.units !== undefined) row.units = Number(p.units);
		if (p.session_duration_hours !== undefined)
			row.session_duration_hours = Number(p.session_duration_hours);
		if (p.course_type === 'lecture' || p.course_type === 'lab')
			row.course_type = p.course_type;
		if (typeof p.is_active === 'boolean') row.is_active = p.is_active;
		row.updated_at = new Date().toISOString();
		return row;
	}
	return findMockCourseRow(suffix);
};

export const mockAdminCourseImport: NonNullable<(typeof defs.AdminCourseImportEndpoint)['mock']> = (_params, _suffix, body) => mockCsvImport(body, 5);

export const mockAdminOfferingCreate: NonNullable<(typeof defs.AdminOfferingCreateEndpoint)['mock']> = (_params, _suffix, body) => {
	const p = (body ?? {}) as MockOfferingPayload;
	const courseId = Number(p.course_id);
	const programId = Number(p.program_id);
	const semester = String(p.semester ?? '').trim();
	const academicYear = String(p.academic_year ?? '').trim();
	if (
		MOCK_ADMIN_OFFERINGS.some(
			(r) =>
				r.course_id === courseId &&
				r.program_id === programId &&
				r.semester.toLowerCase() === semester.toLowerCase() &&
				r.academic_year.toLowerCase() === academicYear.toLowerCase()
		)
	) {
		throw new Error('Offering already exists for this course, program, semester and academic year.');
	}
	const row: AdminOfferingResponse = {
		id: Math.max(...MOCK_ADMIN_OFFERINGS.map((r) => r.id), 0) + 1,
		course_id: courseId,
		program_id: programId,
		year_level_id: Number(p.year_level_id),
		semester,
		academic_year: academicYear,
		sessions_per_week: Number(p.sessions_per_week ?? 2),
		// Derived from the term (D86), mirroring the live read: the mock
		// never accepts weeks on the create payload.
		semester_weeks: mockTermWeeks(Number(p.year_level_id), semester),
		schedule_days: String(p.schedule_days ?? 'MWF').trim().toUpperCase(),
		schedule_start_time: String(p.schedule_start_time ?? '09:00:00'),
		schedule_end_time: String(p.schedule_end_time ?? '10:30:00'),
		course_type: p.course_type === 'lab' ? 'lab' : 'lecture',
		session_types: ['lecture'],
		components: [],
		classroom_name: (p.classroom_name as string | null) ?? null,
		classroom_lat: (p.classroom_lat as number | null) ?? null,
		classroom_lng: (p.classroom_lng as number | null) ?? null,
		default_present_window_minutes: Number(p.default_present_window_minutes ?? 5),
		default_late_window_minutes: Number(p.default_late_window_minutes ?? 10),
		default_classroom_radius_meters:
			typeof p.default_classroom_radius_meters === 'number'
				? p.default_classroom_radius_meters
				: null,
		enrolled_count: 0,
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	};
	// D77: explicit per-type schedules, else one lecture component
	// mirroring the offering schedule/classroom (same default as live).
	row.components = mockComponentsForCreate(row, p.components);
	row.session_types = [...new Set(row.components.map((c) => c.session_type))];
	MOCK_ADMIN_OFFERINGS.push(row);
	return row;
};

export const mockAdminOfferingDetail: NonNullable<(typeof defs.AdminOfferingDetailEndpoint)['mock']> = (_params, suffix, body, method) => {
	if (method === 'DELETE') {
		const row = findMockOfferingRow(suffix);
		if (row.is_active) throw new Error('Only inactive offerings can be deleted.');
		MOCK_ADMIN_OFFERINGS.splice(MOCK_ADMIN_OFFERINGS.indexOf(row), 1);
		return mockNoContent();
	}
	if (method === 'PATCH') {
		const row = findMockOfferingRow(suffix);
		const p = (body ?? {}) as MockOfferingPayload;
		if (p.sessions_per_week !== undefined)
			row.sessions_per_week = Number(p.sessions_per_week);
		if (p.schedule_days !== undefined)
			row.schedule_days = String(p.schedule_days).trim().toUpperCase();
		if (p.schedule_start_time !== undefined)
			row.schedule_start_time = String(p.schedule_start_time);
		if (p.schedule_end_time !== undefined)
			row.schedule_end_time = String(p.schedule_end_time);
		if (p.course_type === 'lecture' || p.course_type === 'lab')
			row.course_type = p.course_type;
		if (p.classroom_name !== undefined)
			row.classroom_name = p.classroom_name ? String(p.classroom_name) : null;
		if (p.classroom_lat !== undefined)
			row.classroom_lat = p.classroom_lat === null ? null : Number(p.classroom_lat);
		if (p.classroom_lng !== undefined)
			row.classroom_lng = p.classroom_lng === null ? null : Number(p.classroom_lng);
		if (p.default_present_window_minutes !== undefined)
			row.default_present_window_minutes = Number(p.default_present_window_minutes);
		if (p.default_late_window_minutes !== undefined)
			row.default_late_window_minutes = Number(p.default_late_window_minutes);
		if (typeof p.is_active === 'boolean') row.is_active = p.is_active;
		row.updated_at = new Date().toISOString();
		return row;
	}
	return findMockOfferingRow(suffix);
};

export const mockAdminOfferingComponents: NonNullable<(typeof defs.AdminOfferingComponentsEndpoint)['mock']> = (_params, suffix) =>
	findMockOfferingRow(suffix).components.filter((c) => c.is_active);

export const mockAdminOfferingComponentCreate: NonNullable<(typeof defs.AdminOfferingComponentCreateEndpoint)['mock']> = (_params, suffix, body) => {
	const row = findMockOfferingRow(suffix);
	const p = (body ?? {}) as MockComponentPayload;
	const created = mockComponentFromPayload(
		row.id,
		p,
		{
			days: row.schedule_days,
			start: row.schedule_start_time,
			end: row.schedule_end_time,
			name: row.classroom_name,
			lat: row.classroom_lat,
			lng: row.classroom_lng,
		}
	);
	if (
		row.components.some(
			(c) =>
				c.session_type === created.session_type &&
				c.schedule_days === created.schedule_days &&
				c.schedule_start_time === created.schedule_start_time
		)
	) {
		throw new Error('Offering already has a component on that schedule.');
	}
	row.components.push(created);
	refreshMockSessionTypes(row);
	return created;
};

export const mockAdminOfferingComponentDetail: NonNullable<(typeof defs.AdminOfferingComponentDetailEndpoint)['mock']> = (_params, suffix, body, method) => {
	const { offering, component } = findMockComponentRow(suffix);
	if (method === 'DELETE') {
		component.is_active = false;
		component.updated_at = new Date().toISOString();
		refreshMockSessionTypes(offering);
		return mockNoContent();
	}
	if (method === 'PATCH') {
		const p = (body ?? {}) as MockComponentPayload;
		if (p.schedule_days !== undefined)
			component.schedule_days = String(p.schedule_days).trim().toUpperCase();
		const start =
			p.schedule_start_time !== undefined
				? String(p.schedule_start_time)
				: component.schedule_start_time;
		const end =
			p.schedule_end_time !== undefined
				? String(p.schedule_end_time)
				: component.schedule_end_time;
		if (end <= start) throw new Error('schedule_end_time must be after schedule_start_time');
		component.schedule_start_time = start;
		component.schedule_end_time = end;
		if (p.classroom_name !== undefined)
			component.classroom_name = p.classroom_name ? String(p.classroom_name) : null;
		if (p.classroom_lat !== undefined)
			component.classroom_lat = p.classroom_lat === null ? null : Number(p.classroom_lat);
		if (p.classroom_lng !== undefined)
			component.classroom_lng = p.classroom_lng === null ? null : Number(p.classroom_lng);
		if (typeof p.is_active === 'boolean') component.is_active = p.is_active;
		component.updated_at = new Date().toISOString();
		refreshMockSessionTypes(offering);
		return component;
	}
	return component;
};

export const mockAdminOfferingProfessors: NonNullable<(typeof defs.AdminOfferingProfessorsEndpoint)['mock']> = (params, suffix, body, method) => {
	const offeringId = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!Number.isFinite(offeringId) || offeringId <= 0) throw new Error('Offering not found.');
	if (method === 'DELETE') {
		const permanentMatch = suffix?.match(/\/professors\/(\d+)\/permanent/);
		if (permanentMatch) {
			const professorId = parseInt(permanentMatch[1], 10);
			const effectiveFrom = params?.effective_from;
			if (!effectiveFrom) throw new Error('Assignment start date is required.');
			const row = MOCK_ADMIN_ASSIGNMENTS.find(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === professorId &&
					a.effective_from === effectiveFrom
			);
			if (!row) throw new Error('Assignment not found.');
			const today = new Date().toISOString().slice(0, 10);
			if (row.effective_to === null || row.effective_to > today) {
				throw new Error(
					'This assignment is still active. End it first, then remove it permanently.'
				);
			}
			if (row.has_sessions) {
				throw new Error(
					'This assignment has sessions and cannot be permanently removed. End it instead.'
				);
			}
			MOCK_ADMIN_ASSIGNMENTS.splice(MOCK_ADMIN_ASSIGNMENTS.indexOf(row), 1);
			return mockNoContent();
		}

		const professorId = parseInt(suffix?.match(/\/professors\/(\d+)/)?.[1] ?? '', 10);
		const effectiveFrom = params?.effective_from;
		const row =
			MOCK_ADMIN_ASSIGNMENTS.find(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === professorId &&
					(!effectiveFrom || a.effective_from === effectiveFrom) &&
					a.effective_to === null
			) ??
			MOCK_ADMIN_ASSIGNMENTS.find(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === professorId &&
					(!effectiveFrom || a.effective_from === effectiveFrom)
			);
		if (!row) throw new Error('Assignment not found.');
		const today = new Date().toISOString().slice(0, 10);
		if (row.effective_from > today) {
			// A future assignment never took effect; cancel it.
			MOCK_ADMIN_ASSIGNMENTS.splice(MOCK_ADMIN_ASSIGNMENTS.indexOf(row), 1);
		} else {
			row.effective_to = today;
		}
		return { effective_to: today };
	}
	if (method === 'POST') {
		const p = (body ?? {}) as MockAssignmentPayload;
		const offering = MOCK_ADMIN_OFFERINGS.find((o) => o.id === offeringId);
		const semester = offering?.semester ?? '';
		const reopenMatch = suffix?.match(/\/professors\/(\d+)\/reopen/);
		if (reopenMatch) {
			const professorId = parseInt(reopenMatch[1], 10);
			const targetStart = String(p.effective_from ?? '').slice(0, 10);
			const row = MOCK_ADMIN_ASSIGNMENTS.find(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === professorId &&
					a.effective_from === targetStart
			);
			if (!row) throw new Error('Assignment not found.');
			if (row.effective_to === null) throw new Error('This assignment is already open-ended.');
			const later = MOCK_ADMIN_ASSIGNMENTS.find(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === professorId &&
					a.effective_from > row.effective_from
			);
			if (later) throw new Error('A later assignment exists for this professor. End or change it first.');
			const newPrimary =
				p.is_primary === undefined ? row.is_primary : Boolean(p.is_primary);
			if (newPrimary) {
				const conflict = mockPrimaryConflict(
					offeringId,
					row.effective_from,
					null,
					row
				);
				if (conflict) throw mockPrimaryConflictError(conflict);
			}
			row.effective_to = null;
			row.is_primary = newPrimary;
			return row;
		}
		const reassignMatch = suffix?.match(/\/professors\/(\d+)\/reassign/);
		if (reassignMatch) {
			const oldProfessorId = parseInt(reassignMatch[1], 10);
			const newProfessorId = Number(p.new_professor_id);
			const effectiveTo = p.effective_to ? String(p.effective_to).slice(0, 10) : null;
			const oldEffectiveFrom = p.old_effective_from
				? String(p.old_effective_from).slice(0, 10)
				: null;
			const oldRow =
				MOCK_ADMIN_ASSIGNMENTS.find(
					(a) =>
						a.offering_id === offeringId &&
						a.professor_id === oldProfessorId &&
						(!oldEffectiveFrom || a.effective_from === oldEffectiveFrom) &&
						a.effective_to === null
				) ??
				MOCK_ADMIN_ASSIGNMENTS.find(
					(a) =>
						a.offering_id === offeringId &&
						a.professor_id === oldProfessorId &&
						(!oldEffectiveFrom || a.effective_from === oldEffectiveFrom)
				);
			if (!oldRow) throw new Error('Assignment not found.');
			const effectiveFrom = String(p.effective_from ?? oldRow.effective_from).slice(0, 10);
			if (newProfessorId === oldProfessorId) throw new Error('Replacement professor must differ.');
			const overlap = MOCK_ADMIN_ASSIGNMENTS.some(
				(a) =>
					a.offering_id === offeringId &&
					a.professor_id === newProfessorId &&
					mockDateOrOngoing(a.effective_to) >= effectiveFrom &&
					mockDateOrOngoing(effectiveTo) >= a.effective_from
			);
			if (overlap) throw new Error('Overlapping assignment for this professor and offering.');
			const newPrimary = Boolean(p.is_primary ?? oldRow.is_primary);
			if (newPrimary) {
				const conflict = mockPrimaryConflict(
					offeringId,
					effectiveFrom,
					effectiveTo,
					oldRow
				);
				if (conflict) throw mockPrimaryConflictError(conflict);
			}
			const today = new Date().toISOString().slice(0, 10);
			if (oldRow.effective_from > today && effectiveFrom === oldRow.effective_from) {
				MOCK_ADMIN_ASSIGNMENTS.splice(MOCK_ADMIN_ASSIGNMENTS.indexOf(oldRow), 1);
			} else {
				oldRow.effective_to = mockDayBefore(effectiveFrom);
			}
			const row: AdminAssignmentResponse = {
				offering_id: offeringId,
				professor_id: newProfessorId,
				is_primary: newPrimary,
				effective_from: effectiveFrom,
				effective_to: effectiveTo,
				semester,
				has_sessions: false,
				assigned_by: 1,
				assigned_at: new Date().toISOString(),
			};
			MOCK_ADMIN_ASSIGNMENTS.push(row);
			return row;
		}
		const professorId = Number(p.professor_id);
		const effectiveFrom = String(p.effective_from ?? '').slice(0, 10);
		const effectiveTo = p.effective_to ? String(p.effective_to).slice(0, 10) : null;
		const overlap = MOCK_ADMIN_ASSIGNMENTS.some(
			(a) =>
				a.offering_id === offeringId &&
				a.professor_id === professorId &&
				mockDateOrOngoing(a.effective_to) >= effectiveFrom &&
				mockDateOrOngoing(effectiveTo) >= a.effective_from
		);
		if (overlap) throw new Error('Overlapping assignment for this professor and offering.');
		const isPrimary = Boolean(p.is_primary);
		if (isPrimary) {
			const conflict = mockPrimaryConflict(
				offeringId,
				effectiveFrom,
				effectiveTo
			);
			if (conflict) throw mockPrimaryConflictError(conflict);
		}
		const row: AdminAssignmentResponse = {
			offering_id: offeringId,
			professor_id: professorId,
			is_primary: isPrimary,
			effective_from: effectiveFrom,
			effective_to: effectiveTo,
			semester,
			has_sessions: false,
			assigned_by: 1,
			assigned_at: new Date().toISOString(),
		};
		MOCK_ADMIN_ASSIGNMENTS.push(row);
		return row;
	}
	return MOCK_ADMIN_ASSIGNMENTS.filter((a) => a.offering_id === offeringId);
};

export const mockAdminOfferingRoster: NonNullable<(typeof defs.AdminOfferingRosterEndpoint)['mock']> = (params) => {
	let rows: AdminRosterItemResponse[] = MOCK_ADMIN_STUDENT_ROWS.map((s) => ({
		id: s.id,
		student_id: s.student_id,
		name: [s.first_name, s.middle_name, s.last_name].filter(Boolean).join(' '),
		section: s.section,
		enrolled_at: s.created_at,
	}));
	const section = params?.section?.trim().toLowerCase();
	if (section) {
		rows = rows.filter((r) => (r.section ?? '').toLowerCase() === section);
	}
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

export const mockAdminOfferingBulkEnroll: NonNullable<(typeof defs.AdminOfferingBulkEnrollEndpoint)['mock']> = () => ({ enrolled: 3, skipped: 1, errors: [] });

export const mockAdminPrograms: NonNullable<(typeof defs.AdminProgramsEndpoint)['mock']> = () => MOCK_PROGRAMS;

export const mockAdminProgramCreate: NonNullable<(typeof defs.AdminProgramCreateEndpoint)['mock']> = () => MOCK_PROGRAMS.items[0];

export const mockAdminProgramDetail: NonNullable<(typeof defs.AdminProgramDetailEndpoint)['mock']> = (_params, suffix, _body, method) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (method === 'DELETE') {
		const idx = MOCK_PROGRAMS.items.findIndex((p) => p.id === id);
		if (idx === -1) throw new Error('Program not found.');
		if (MOCK_PROGRAMS.items[idx].is_active)
			throw new Error('Only inactive programs can be deleted.');
		const [removed] = MOCK_PROGRAMS.items.splice(idx, 1);
		MOCK_PROGRAMS.total = MOCK_PROGRAMS.items.length;
		for (let i = MOCK_YEARS.length - 1; i >= 0; i--) {
			if (MOCK_YEARS[i].program_id === removed.id) MOCK_YEARS.splice(i, 1);
		}
		return mockNoContent();
	}
	const program = MOCK_PROGRAMS.items.find((p) => p.id === id) ?? MOCK_PROGRAMS.items[0];
	return {
		...program,
		year_levels: MOCK_YEARS.filter((y) => y.program_id === program.id),
	};
};

export const mockAdminProgramImport: NonNullable<(typeof defs.AdminProgramImportEndpoint)['mock']> = (_params, _suffix, body) => mockCsvImport(body, 5);

export const mockAdminYearLevels: NonNullable<(typeof defs.AdminYearLevelsEndpoint)['mock']> = (_params, suffix) => {
	// Suffix looks like `/3/years` — only that program's years come back.
	const programId = parseInt(suffix?.match(/\/(\d+)\/years/)?.[1] ?? '', 10);
	const items =
		Number.isFinite(programId) && programId > 0
			? MOCK_YEARS.filter((y) => y.program_id === programId)
			: [...MOCK_YEARS];
	return { items, total: items.length, page: 1, size: 50 };
};

export const mockAdminYearLevelDetail: NonNullable<(typeof defs.AdminYearLevelDetailEndpoint)['mock']> = () => MOCK_YEARS[0];

export const mockAdminAnalyticsOverview: NonNullable<(typeof defs.AdminAnalyticsOverviewEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params, parseCourseIds(params));
	const rates = summarizeMockSessions(sessions);
	const students = new Set(sessions.map((s) => `${s.programId}:${s.enrolled}`));
	return {
		total_students: sessions.length === 0 ? 0 : [...students].reduce((sum, key) => sum + Number(key.split(':')[1]), 0),
		total_courses: new Set(sessions.map((s) => `${s.courseId}:${s.programId}`)).size,
		avg_compliance_rate: rates.compliance,
		avg_participation_rate: rates.participation,
		total_sessions: sessions.length,
	};
};

export const mockAdminAnalyticsCourseOptions: NonNullable<(typeof defs.AdminAnalyticsCourseOptionsEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params);
	const byId = new Map<number, { course_id: number; course_code: string; course_name: string }>();
	for (const s of sessions) {
		if (!byId.has(s.courseId)) {
			byId.set(s.courseId, {
				course_id: s.courseId,
				course_code: s.courseCode,
				course_name: s.courseName,
			});
		}
	}
	let items = [...byId.values()].sort((a, b) => a.course_code.localeCompare(b.course_code));
	const q = params?.q?.trim().toLowerCase();
	if (q) {
		items = items.filter(
			(c) => c.course_code.toLowerCase().includes(q) || c.course_name.toLowerCase().includes(q)
		);
	}
	return { items, total: items.length };
};

export const mockAdminAnalyticsComparison: NonNullable<(typeof defs.AdminAnalyticsComparisonEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params, parseCourseIds(params));
	const groups = new Map<string, MockAnalyticsSession[]>();
	for (const s of sessions) {
		const key = `${s.courseId}|${s.programId}|${s.yearLevelId}`;
		const group = groups.get(key) ?? [];
		group.push(s);
		groups.set(key, group);
	}
	const items: AnalyticsComparisonItemResponse[] = [...groups].map(([key, group]) => {
		const [courseId, programId, yearLevelId] = key.split('|').map(Number);
		const rates = summarizeMockSessions(group);
		return {
			course_id: courseId,
			course_code: group[0].courseCode,
			program_id: programId,
			year_level_id: yearLevelId,
			compliance_rate: rates.compliance,
			participation_rate: rates.participation,
			total_sessions: group.length,
		};
	});
	items.sort((a, b) =>
		a.course_code === b.course_code
			? `${a.program_id}${a.year_level_id}`.localeCompare(`${b.program_id}${b.year_level_id}`)
			: a.course_code.localeCompare(b.course_code)
	);
	return { items };
};

export const mockAdminAnalyticsTrends: NonNullable<(typeof defs.AdminAnalyticsTrendsEndpoint)['mock']> = (params) => {
	const granularity = params?.granularity ?? 'daily';
	const sessions = filterMockSessions(params, parseCourseIds(params));
	const buckets = new Map<string, MockAnalyticsSession[]>();
	for (const s of sessions) {
		const { key } = mockBucketKey(s.date, granularity);
		const bucket = buckets.get(key) ?? [];
		bucket.push(s);
		buckets.set(key, bucket);
	}
	const items: AnalyticsTrendItemResponse[] = [...buckets].map(([, group]) => {
		const rates = summarizeMockSessions(group);
		return {
			date: mockBucketKey(group[0].date, granularity).date,
			compliance_rate: rates.compliance,
			participation_rate: rates.participation,
			total_sessions: group.length,
		};
	});
	items.sort((a, b) => (a.date === b.date ? 0 : a.date < b.date ? -1 : 1));
	return { items };
};

export const mockAdminAnalyticsAtRisk: NonNullable<(typeof defs.AdminAnalyticsAtRiskEndpoint)['mock']> = (params) => {
	let rows = [...MOCK_AT_RISK_ROWS];
	if (params?.risk_level) {
		rows = rows.filter((r) => r.risk_level === params.risk_level);
	}
	if (params?.program_id) {
		const program = MOCK_PROGRAMS.items.find((p) => String(p.id) === params.program_id);
		rows = program ? rows.filter((r) => r.program === program.code) : [];
	}
	// Mock rows carry no semester (risk is keyed by offering per D35), so in
	// mock mode the filter is accepted and has no effect. Live mode passes
	// semester through to the backend.
	return { items: rows };
};

export const mockAdminAnalyticsRefreshRisk: NonNullable<(typeof defs.AdminAnalyticsRefreshRiskEndpoint)['mock']> = () => {
	const now = new Date().toISOString();
	for (const row of MOCK_AT_RISK_ROWS) row.computed_at = now;
	const high = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'high').length;
	const medium = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'medium').length;
	const low = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'low').length;
	return { processed: MOCK_AT_RISK_ROWS.length, high, medium, low, duration_ms: 42 };
};

export const mockAdminRiskStaging: NonNullable<(typeof defs.AdminRiskStagingEndpoint)['mock']> = () => ({ items: [], total: 0, page: 1, size: 20 });

export const mockAdminRiskStagingPromote: NonNullable<(typeof defs.AdminRiskStagingPromoteEndpoint)['mock']> = () => ({ promoted: 0, skipped: 0, duration_ms: 0 });

export const mockAdminAttendanceOverview: NonNullable<(typeof defs.AdminAttendanceOverviewEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params);
	const groups = new Map<number, MockAnalyticsSession[]>();
	for (const s of sessions) {
		const group = groups.get(s.courseId) ?? [];
		group.push(s);
		groups.set(s.courseId, group);
	}
	let items: AttendanceOverviewItemResponse[] = [...groups].map(([courseId, group]) => {
		const firstHalf = group.slice(0, Math.ceil(group.length / 2));
		const secondHalf = group.slice(Math.ceil(group.length / 2));
		const avgOf = (rows: MockAnalyticsSession[]) => summarizeMockSessions(rows).compliance;
		const early = avgOf(firstHalf.length > 0 ? firstHalf : group);
		const lateAvg = avgOf(secondHalf.length > 0 ? secondHalf : group);
		const delta = lateAvg - early;
		return {
			course_id: courseId,
			course_code: group[0].courseCode,
			course_name: group[0].courseName,
			sessions_count: group.length,
			avg_rate: summarizeMockSessions(group).compliance,
			trend: (delta > 0.02 ? 'up' : delta < -0.02 ? 'down' : 'flat') as 'up' | 'down' | 'flat',
		};
	});
	if (params?.course_id) {
		items = items.filter((r) => String(r.course_id) === params.course_id);
	}
	items.sort((a, b) => a.course_code.localeCompare(b.course_code));
	return { items };
};

export const mockAdminAttendanceSummary: NonNullable<(typeof defs.AdminAttendanceSummaryEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params);
	let present = 0;
	let late = 0;
	let excused = 0;
	let rejected = 0;
	let seats = 0;
	const students = new Set<number>();
	for (const s of sessions) {
		present += s.present;
		late += s.late;
		excused += s.excused;
		rejected += (s as { rejected?: number }).rejected ?? 0;
		seats += s.enrolled;
		students.add(s.courseId);
	}
	const total = present + late + excused + rejected;
	return {
		total_records: total,
		present,
		late,
		excused,
		rejected,
		absent: 0,
		compliance_rate: seats === 0 ? 0 : present / seats,
		participation_rate: seats === 0 ? 0 : (present + late + excused) / seats,
		total_sessions: sessions.length,
		total_students: students.size,
		previous_compliance_rate: 0,
		previous_participation_rate: 0,
	};
};

export const mockAdminAttendanceRecords: NonNullable<(typeof defs.AdminAttendanceRecordsEndpoint)['mock']> = (params) => {
	const sessions = filterMockSessions(params);
	const items: AttendanceRecordItemResponse[] = [];
	let id = 1;
	for (const s of sessions) {
		for (let i = 0; i < s.present; i++) {
			items.push({
				id: id++,
				student_id: i + 1,
				student_name: `Student ${i + 1}`,
				student_number: `STU-${i + 1}`,
				course_id: s.courseId,
				course_code: s.courseCode,
				course_name: s.courseName,
				program_code: s.programCode ?? null,
				year_level_label: s.yearLevelLabel ?? null,
				session_code: `S-${s.courseId}`,
				status: 'present',
				scanned_at: `${s.date}T08:00:00Z`,
				professor_name: null,
			});
		}
	}
	const page = Number(params?.page ?? 1);
	const size = Number(params?.size ?? 20);
	const start = (page - 1) * size;
	return { items: items.slice(start, start + size), total: items.length, page, size };
};

export const mockSystemSettingsGet: NonNullable<(typeof defs.SystemSettingsGetEndpoint)['mock']> = () => ({ ...MOCK_SYSTEM_SETTINGS });

export const mockSystemSettingsPatch: NonNullable<(typeof defs.SystemSettingsPatchEndpoint)['mock']> = (_params, _suffix, body) => {
	const patch = (body ?? {}) as Partial<SystemSettingsResponse>;
	const numericKeys = [
		'geofence_default_radius',
		'present_window_default',
		'late_window_default',
		'session_early_open_minutes',
		'session_late_open_minutes',
		'backup_retention_daily',
		'backup_retention_monthly'
	] as const;
	for (const key of numericKeys) {
		const value = patch[key];
		if (typeof value === 'number' && Number.isFinite(value)) {
			MOCK_SYSTEM_SETTINGS[key] = value;
		}
	}
	return { ...MOCK_SYSTEM_SETTINGS };
};

export const mockSystemBackups: NonNullable<(typeof defs.SystemBackupsEndpoint)['mock']> = () => ({ items: [...MOCK_BACKUP_ROWS] });

export const mockSystemBackupTrigger: NonNullable<(typeof defs.SystemBackupTriggerEndpoint)['mock']> = () => {
	const nextId = Math.max(0, ...MOCK_BACKUP_ROWS.map((r) => r.id)) + 1;
	const now = new Date().toISOString();
	MOCK_BACKUP_ROWS.unshift({
		id: nextId,
		filename: `attendance_full_${now.replace(/[-:]/g, '').slice(0, 15)}Z.dump.gpg`,
		kind: 'full',
		size_bytes: 0,
		storage_backend: 'local',
		started_at: now,
		finished_at: null,
		status: 'started'
	});
	return { backup_id: nextId, status: 'started' };
};

export const mockSystemSyncFlush: NonNullable<(typeof defs.SystemSyncFlushEndpoint)['mock']> = () => {
	const processed = MOCK_SYSTEM_SETTINGS.pending_sync_count;
	MOCK_SYSTEM_SETTINGS.pending_sync_count = 0;
	return { processed, succeeded: processed, failed: 0 };
};

export const mockSystemCleanup: NonNullable<(typeof defs.SystemCleanupEndpoint)['mock']> = () => ({ removed: 14 });

export const mockAdminAuditLogs: NonNullable<(typeof defs.AdminAuditLogsEndpoint)['mock']> = (params) => {
	let rows = [...MOCK_AUDIT_ROWS];
	// Contract filters AND-combine; a blank value means "no filter".
	if (params?.entity_type) {
		rows = rows.filter((r) => r.entity_type === params.entity_type);
	}
	if (params?.action) {
		rows = rows.filter((r) => r.action === params.action);
	}
	// `performed_by` is a `users.id` in the contract, so the mock compares
	// ids rather than names.
	if (params?.performed_by) {
		const wanted = Number(params.performed_by);
		rows = rows.filter((r) => r.performed_by === wanted);
	}
	// `actor` matches the id, the email or the name — the same fragment
	// match the server does.
	if (params?.actor) {
		const needle = params.actor.trim().toLowerCase();
		if (needle) {
			rows = rows.filter((r) => {
				if (r.actor.email?.toLowerCase().includes(needle)) return true;
				if (r.actor.name.toLowerCase().includes(needle)) return true;
				return String(r.actor.id ?? '') === needle;
			});
		}
	}
	if (params?.date_from) {
		rows = rows.filter((r) => r.performed_at.slice(0, 10) >= params.date_from!);
	}
	if (params?.date_to) {
		rows = rows.filter((r) => r.performed_at.slice(0, 10) <= params.date_to!);
	}
	// The sort is the server's: `time`, `actor` or `action`, over the
	// WHOLE trail rather than the loaded page.
	const sortBy = params?.sort_by ?? 'time';
	const descending = (params?.sort_dir ?? 'desc') !== 'asc';
	const key =
		sortBy === 'actor'
			? (r: AuditLogItemResponse) => r.actor.name
			: sortBy === 'action'
				? (r: AuditLogItemResponse) => r.action_label
				: (r: AuditLogItemResponse) => r.performed_at;
	rows.sort((a, b) => {
		const compared = key(a).localeCompare(key(b));
		return descending ? -compared : compared;
	});
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

export const mockAdminStructureChanges: NonNullable<(typeof defs.AdminStructureChangesEndpoint)['mock']> = (params) => {
	const rows = [...MOCK_STRUCTURE_ROWS].sort((a, b) =>
		a.performed_at < b.performed_at ? 1 : -1
	);
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 200);
	const total = rows.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
	return { items: rows.slice((page - 1) * size, page * size), total, page, size };
};

export const mockAdminUsers: NonNullable<(typeof defs.AdminUsersEndpoint)['mock']> = (params) => mockAdminUsersList(params);

export const mockAdminUserCreate: NonNullable<(typeof defs.AdminUserCreateEndpoint)['mock']> = (_params, _suffix, body) => {
	const p = (body ?? {}) as MockAdminUserPayload;
	const email = String(p.email ?? '').trim().toLowerCase();
	const role = String(p.role ?? '').trim();
	if (!email) throw new Error('Email is required.');
	if (role === 'super_admin') {
		throw new Error('super_admin accounts cannot be created; the first one is seeded at deployment');
	}
	if (!['admin', 'professor', 'student'].includes(role)) {
		throw new Error('Role must be admin, professor, or student.');
	}
	if (MOCK_ADMIN_USER_ROWS.some((r) => (r.email ?? '').toLowerCase() === email)) {
		throw new Error('Email already exists.');
	}
	const row: AdminUserResponse = {
		id: Math.max(...MOCK_ADMIN_USER_ROWS.map((r) => r.id), 0) + 1,
		email,
		role: role as AdminUserResponse['role'],
		first_name: String(p.first_name ?? '').trim() || null,
		last_name: String(p.last_name ?? '').trim() || null,
		is_active: true,
		must_change_password: true,
		last_login: null,
		created_at: new Date().toISOString(),
	};
	MOCK_ADMIN_USER_ROWS.push(row);
	return { ...row, temp_password: `Temp-${Math.random().toString(36).slice(2, 10)}!` };
};

export const mockAdminUserDeactivate: NonNullable<(typeof defs.AdminUserDeactivateEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('User not found.');
	row.is_active = false;
	return undefined;
};

export const mockAdminUserReactivate: NonNullable<(typeof defs.AdminUserReactivateEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('User not found.');
	row.is_active = true;
	return undefined;
};

export const mockAdminUserResetPassword: NonNullable<(typeof defs.AdminUserResetPasswordEndpoint)['mock']> = (_params, suffix, _body, method) => {
	if (method !== 'POST') throw new Error('Password reset is a POST.');
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
	if (!row) throw new Error('User not found.');
	row.must_change_password = true;
	return mockTempPassword();
};

export const mockAdminStudentResetPassword: NonNullable<(typeof defs.AdminStudentResetPasswordEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_STUDENT_ROWS.some((r) => r.id === id)) throw new Error('Student not found.');
	return mockTempPassword();
};

export const mockAdminProfessorResetPassword: NonNullable<(typeof defs.AdminProfessorResetPasswordEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_PROFESSOR_ROWS.some((r) => r.id === id)) {
		throw new Error('Professor not found.');
	}
	return mockTempPassword();
};

export const mockAdminUserLockoutStatus: NonNullable<(typeof defs.AdminUserLockoutStatusEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_USER_ROWS.some((r) => r.id === id)) throw new Error('User not found.');
	return {
		user_id: id,
		email: MOCK_ADMIN_USER_ROWS.find((r) => r.id === id)?.email ?? '',
		role: 'admin',
		is_locked: false,
		is_permanently_locked: false,
		locked_at: null,
		lockout_level: 0,
		lockout_duration_minutes: 0,
		locked_until: null,
		remaining_minutes: null,
		last_lockout_at: null,
		override_until: null,
		override_remaining_minutes: null,
	};
};

export const mockAdminUserLockoutRelease: NonNullable<(typeof defs.AdminUserLockoutReleaseEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_USER_ROWS.some((r) => r.id === id)) throw new Error('User not found.');
	return mockNoContent();
};

export const mockAdminUserLockoutResetCounter: NonNullable<(typeof defs.AdminUserLockoutResetCounterEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_USER_ROWS.some((r) => r.id === id)) throw new Error('User not found.');
	return mockNoContent();
};

export const mockAdminUserLockoutOverride: NonNullable<(typeof defs.AdminUserLockoutOverrideEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_USER_ROWS.some((r) => r.id === id)) throw new Error('User not found.');
	return mockNoContent();
};

export const mockAdminUserLockoutOverrideRevoke: NonNullable<(typeof defs.AdminUserLockoutOverrideRevokeEndpoint)['mock']> = (_params, suffix) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	if (!MOCK_ADMIN_USER_ROWS.some((r) => r.id === id)) throw new Error('User not found.');
	return mockNoContent();
};

export const mockProfessorReportsAllCourses: NonNullable<(typeof defs.ProfessorReportsAllCoursesEndpoint)['mock']> = (params) => {
	const granularity = params?.granularity ?? 'daily';
	const suffix = granularity === 'monthly' ? '-01' : '';
	const base = (params?.date_from ?? new Date().toISOString().slice(0, 10)).slice(0, granularity === 'monthly' ? 7 : 10);
	const items: ProfessorReportsAllCoursesItemResponse[] = [0, 1, 2].map((i) => ({
		date: `${base}${suffix}`,
		total_sessions: 3 - i,
		total_students: 90 - i * 5,
		compliance_rate: 0.82 - i * 0.03,
		participation_rate: 0.9 - i * 0.02,
	}));
	return { items, avg_compliance: 0.79, avg_participation: 0.88 };
};

export const mockProfessorReportsComparison: NonNullable<(typeof defs.ProfessorReportsComparisonEndpoint)['mock']> = () => ({
	items: [
		{ course_id: 1, course_code: 'CS101', program_id: 1, year_level_id: 1, program_code: 'BSCS', year_level_label: 'Year 1', compliance_rate: 0.84, participation_rate: 0.92, total_sessions: 12 },
		{ course_id: 2, course_code: 'MATH101', program_id: 1, year_level_id: 1, program_code: 'BSCS', year_level_label: 'Year 1', compliance_rate: 0.71, participation_rate: 0.83, total_sessions: 9 },
	],
});

export const mockProfessorReportsTrends: NonNullable<(typeof defs.ProfessorReportsTrendsEndpoint)['mock']> = (params) => {
	const base = (params?.date_from ?? new Date().toISOString().slice(0, 10)).slice(0, 10);
	return {
		items: [0, 1, 2].map((i) => ({
			date: base,
			course_id: 1,
			course_code: 'CS101',
			rate: 0.8 - i * 0.02,
		})),
	};
};

export const mockAdminExcuses: NonNullable<(typeof defs.AdminExcusesEndpoint)['mock']> = (params) => {
	const now = new Date().toISOString();
	// The mock mirrors the CONTRACT shape: the display fields are
	// resolved server-side, so the mock carries them too. A mock that
	// invents a friendlier shape is what hid the last round of defects
	// (ADR-088).
	const rows: ExcuseRequestReadResponse[] = [
		{
			id: 901,
			student_id: 1,
			session_id: 41,
			initiated_by: 'student',
			initiated_via: 'request',
			reason: 'Medical appointment with supporting documents attached for review.',
			attachment_urls: [],
			status: 'pending',
			requested_at: now,
			reviewed_by: null,
			reviewed_at: null,
			review_notes: null,
			student_name: 'Juan Dela Cruz',
			student_number: '2024-0001',
			student_section: 'A1',
			session_code: '482913',
			session_date: now,
			course_code: 'CS101',
			course_name: 'Data Structures',
			reviewed_by_name: null,
		},
		{
			id: 902,
			student_id: 2,
			session_id: 38,
			initiated_by: 'student',
			initiated_via: 'request',
			reason: 'Family emergency, barangay certificate available on request.',
			attachment_urls: [],
			status: 'approved',
			requested_at: now,
			reviewed_by: 3,
			reviewed_at: now,
			review_notes: 'Certificate seen.',
			student_name: 'Maria Santos',
			student_number: '2024-0002',
			student_section: 'B2',
			session_code: '775104',
			session_date: now,
			course_code: 'CS101',
			course_name: 'Data Structures',
			reviewed_by_name: 'Maria Dela Cruz',
		},
	];
	const status = params?.status;
	const filtered = status ? rows.filter((r) => r.status === status) : rows;
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
	return { items: filtered.slice((page - 1) * size, page * size), total: filtered.length, page, size };
};

export const mockLivenessReviewList: NonNullable<(typeof defs.LivenessReviewListEndpoint)['mock']> = (params) => {
	const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
	const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
	return { items: [...MOCK_LIVENESS_ROWS], total: MOCK_LIVENESS_ROWS.length, page, size };
};

export const mockLivenessReviewResolve: NonNullable<(typeof defs.LivenessReviewResolveEndpoint)['mock']> = (_params, suffix, body) => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '0', 10) || MOCK_LIVENESS_ROWS[0].id;
	const decision = (body as LivenessReviewResolveBody | undefined)?.decision ?? 'approve';
	return { id, status: decision === 'approve' ? 'present' : 'rejected', reviewed_by: 1, reviewed_at: new Date().toISOString() };
};
