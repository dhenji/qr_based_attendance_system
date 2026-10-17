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
	BackupCodesResponse,
	BackupCodesSummaryResponse,
	MfaDisableRequest,
	MfaSetupResponse,
} from '$lib/shared/types';
import type {
	StudentDashboardResponse,
	StudentProfileResponse,
	ScheduleResponse,
} from '$lib/shared/types';
import type {
	ProfessorDashboardResponse,
} from '$lib/shared/types';
import type {
	AdminDashboardResponse,
	AdminAssignmentResponse,
	AdminBulkEnrollResult,
	AdminCourseResponse,
	AdminOfferingResponse,
	AdminPasswordResetResponse,
	AdminProfessorResponse,
	AdminRosterItemResponse,
	AdminStudentDetailResponse,
	AdminStudentResponse,
	AdminUserCreateResponse,
	AdminUserResponse,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewItemResponse,
	AuditLogItemResponse,
	CourseImportResult,
	OfferingComponentResponse,
	ProfessorImportResult,
	ProgramImportResult,
	PromoteStagingResponse,
	RecentScanResponse,
	RiskRefreshResponse,
	RiskStagingResponse,
	StructureChangeResponse,
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
	session_type: 'lecture' | 'lab';
	course_code: string;
	course_name: string;
	program_code: string;
	year_level_label: string;
	expires_at: string;
	scheduled_end_time: string;
	// Center is null when the session has no classroom coordinates — the
	// backend skips its geofence check in that case (and so does the scan
	// page pre-check).
	geofence: { radius: number; lat: number | null; lng: number | null };
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
	method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
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

// Mock 204 No Content: the live client returns `undefined as T` for empty
// responses, and callers issue these deletes as `del<void>`, so a mock
// DELETE produces no value either. `never` is assignable to every T, which
// keeps the single cast here instead of an `as unknown as X` at each site.
const mockNoContent = (): never => undefined as unknown as never;

// Session QR payload (D18)
export const SessionQREndpoint: EndpointDef<SessionVerificationResponse> = {
	url: '/student/sessions/verify-code',
	method: 'POST',
	mock: () => ({
		session_id: 1,
		offering_id: 1,
		session_type: 'lecture' as const,
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

// Scan precheck (D27 step-2 gate) — live on features/attendance/router.py
// (POST /student/attendance/precheck). Read-only: resolves the student from
// the authenticated user, comparing payload.student_number case-insensitively
// (403 student_number_mismatch on spoof). 200 flags enrolled/already_scanned
// (which scan would raise as 403 not_enrolled / 409 duplicate_scan);
// 404 session_not_found, 410 session_expired still raise.
export interface AttendancePrecheckResponse {
	enrolled: boolean;
	already_scanned: boolean;
	student: {
		student_id: string;
		name: string;
		section: string | null;
	};
}

export const AttendancePrecheckEndpoint: EndpointDef<AttendancePrecheckResponse> = {
	url: '/student/attendance/precheck',
	method: 'POST',
	mock: (_params, _suffix, body) => {
		const p = (body ?? {}) as { student_number?: unknown };
		const studentNumber = String(p.student_number ?? '').trim().toUpperCase() || '24-0001';
		return {
			enrolled: true,
			already_scanned: false,
			student: { student_id: studentNumber, name: 'Jose Rizal', section: 'A' },
		};
	},
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
				session_type: 'lecture' as const,
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

export const SessionCreateEndpoint: EndpointDef<SessionReadResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
			qr_payload: {
				v: 1,
				code: sessionCode,
				offering: 1,
				radius: 50,
				pw: 15,
				lw: 5,
			},
			expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
			scheduled_end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
			created_at: new Date().toISOString(),
		};
	},
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
	mock: (_params, suffix) => {
		const match = suffix?.match(/\/(\d+)/);
		const id = match ? parseInt(match[1], 10) : 1;
		return {
			id,
			offering: 1,
			session_type: 'lecture' as const,
			session_code: mockSessions.get(id) ?? '7X-9K2M',
			scan_window_remaining: 2400,
			scheduled_end_time: new Date(Date.now() + 40 * 60 * 1000).toISOString(),
			status: 'active',
			enrolled_count: 30,
			remaining: 12,
			pending_sync_count: 0,
			students: [],
			counts: { present: 15, late: 3, pending: 10, absent: 2, excused: 0 },
		};
	},
};

// Close session (professor).
// The session id rides the path: POST /professor/sessions/{id}/close —
// callers pass it via the client's `suffix` option.
export const SessionCloseEndpoint: EndpointDef<SessionCloseResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: (_params, suffix) => {
		const match = suffix?.match(/\/(\d+)\/close/);
		const ids = [...mockSessions.keys()];
		const id = match ? parseInt(match[1], 10) : (ids.pop() ?? 0);
		return {
			id,
			status: 'closed' as const,
			final_counts: { present: 0, late: 0, pending: 0, absent: 0, excused: 0 },
		};
	},
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
	otp_pending: false,
	otp_token: null,
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

// Login OTP (mandatory second factor). The password step returns an otp_token
// grant instead of tokens; verify exchanges grant + emailed code for tokens
// (or an MFA challenge), resend burns the previous code and mints a fresh one.
export const AuthLoginOtpVerifyEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/login/verify',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

export const AuthLoginOtpResendEndpoint: EndpointDef<void> = {
	url: '/auth/login/resend',
	method: 'POST',
	mock: () => undefined,
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

// --- MFA enrolment and recovery ------------------------------------------------
//
// Five routes, one account field. `mfa_enabled` is a TWO-WRITER field and the
// UI has to respect that split:
//   * `verify_mfa` is the ONLY writer of true.
//   * `disable_mfa` (POST /auth/mfa/disable) is the ONLY path back to false.
// `setup` deliberately does not enable anything — it only stores the secret —
// so the confirm step must go through `authMfaVerify`, which is why enabling
// takes two calls and looks like it "does nothing" on the first.
//
// None of these are rate limited server-side (unlike login / otp /
// forgot-password), so do not assume the login page's throttle covers the
// confirm step.
export const AuthMfaSetupEndpoint: EndpointDef<MfaSetupResponse> = {
	url: '/auth/mfa/setup',
	method: 'POST',
	mock: () => ({
		// Valid base32 so an authenticator-app-shaped secret is still usable in
		// mock mode. Matches the backend's 16-char pyotp.random_base32().
		secret: 'JBSWY3DPEB2XS2LP',
		qr_url:
			'otpauth://totp/Attendly:student@example.com?secret=JBSWY3DPEB2XS2LP&issuer=Attendly',
		manual_entry_key: 'JBSWY3DPEB2XS2LP',
	}),
};

export const AuthMfaDisableEndpoint: EndpointDef<void> = {
	url: '/auth/mfa/disable',
	method: 'POST',
	mock: () => undefined,
};

export const AuthMfaBackupCodesGenerateEndpoint: EndpointDef<BackupCodesResponse> = {
	url: '/auth/mfa/backup-codes',
	method: 'POST',
	mock: () => ({
		codes: Array.from({ length: 10 }, (_, i) => `MOCKC-${String(i).padStart(4, '0')}-CODE`),
		remaining: 10,
	}),
};

export const AuthMfaBackupCodesSummaryEndpoint: EndpointDef<BackupCodesSummaryResponse> = {
	url: '/auth/mfa/backup-codes',
	method: 'GET',
	mock: () => ({ total: 0, remaining: 0, last_generated_at: null }),
};

export const AuthChangePasswordEndpoint: EndpointDef<void> = {
	url: '/auth/change-password',
	method: 'POST',
	mock: () => undefined,
};

// Forgot-password recovery (ADR-056). Four steps against the live backend
// (features/auth/router.py + service.py):
//  1. POST /auth/forgot-password {email, turnstile_token?} -> {question, set}
//     (decoy question for unknown emails — always render it, never hint at
//     existence; turnstile_token omitted when unconfigured, enforced once
//     TURNSTILE_SECRET is set).
//  2. POST /auth/forgot-password/verify {email, answer} -> {recovery_token}
//     (5-min type=recovery JWT; 400 security_answer_invalid,
//     423 recovery_locked after repeated failures).
//  3. POST /auth/otp/request {email, purpose=forget_password, recovery_token}
//     -> 204, then POST /auth/otp/verify {email, purpose, code} -> 204
//     (existing AuthOtpRequest/Verify defs; pass purpose + recovery_token).
//  4. POST /auth/reset-password {email, otp_code, new_password}
//     -> TokenResponse (the session itself, or an MFA challenge for
//     MFA-enabled accounts — NOT a 204).
export interface ForgotPasswordResponse {
	question: string;
	set: boolean;
}

export const ForgotPasswordEndpoint: EndpointDef<ForgotPasswordResponse> = {
	url: '/auth/forgot-password',
	method: 'POST',
	mock: () => ({
		question: 'What was the name of your first pet?',
		set: true,
	}),
};

export interface ForgotPasswordVerifyResponse {
	recovery_token: string;
}

export const ForgotPasswordVerifyEndpoint: EndpointDef<ForgotPasswordVerifyResponse> = {
	url: '/auth/forgot-password/verify',
	method: 'POST',
	mock: () => ({ recovery_token: 'mock-recovery-token' }),
};

export const ResetPasswordEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/reset-password',
	method: 'POST',
	mock: () => MOCK_TOKENS,
};

// Set/update security question (authenticated) —
// POST /auth/security-question {question, answer} -> 204. The question is
// stored server-side (plaintext under a legacy column name); only the answer
// is hashed. Registration sets the first pair; this updates it.
export const SecurityQuestionEndpoint: EndpointDef<void> = {
	url: '/auth/security-question',
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

// The other two dashboard summaries. All three live in the backend
// `features/dashboard` slice but mount under three different role prefixes, so
// they are three defs rather than one with a path parameter.
//
// Each aggregates features it does not own, and composes its figures from
// existing service methods rather than recomputing them — which is why the
// dashboard can never disagree with the page above it. On the client that
// means: take the numbers from here and do not re-derive them from the roster
// or analytics endpoints.

export const AdminDashboardEndpoint: EndpointDef<AdminDashboardResponse> = {
	url: '/admin/dashboard',
	method: 'GET',
	mock: () => ({
		student_count: 0,
		professor_count: 0,
		program_count: 0,
		avg_rate: 0,
		scans_today: 0,
		pending_sync: 0,
		recent_scans: [],
	}),
};

export const ProfessorDashboardEndpoint: EndpointDef<ProfessorDashboardResponse> = {
	url: '/professor/dashboard',
	method: 'GET',
	mock: () => ({
		sessions_today: 0,
		sessions_completed: 0,
		total_students: 0,
		avg_rate: 0,
		today_sessions: [],
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

// Student excuse requests — live on features/excuse/student_router.py.
// Submit creates a pending request (201); the professor reviews it in the
// queue. Reason floor is STUDENT_EXCUSE_REASON_MIN_LENGTH (student/service),
// not the professor 10. Attachments ride presigned-upload URLs (D24): the
// client mints a URL per file, PUTs the bytes itself, then submits the
// returned object_urls (up to ATTACHMENTS_MAX_FILES). Reason-only submits
// stay valid (pending without files).
// List/detail read the student's own rows (a 404 doubles as not-yours).
export interface StudentExcuseSubmitBody {
	session_id: number;
	reason: string;
	attachment_urls?: string[];
}

export interface StudentExcuseSubmitResponse {
	id: number;
	status: string;
	requested_at: string;
}

export interface StudentExcuseItemResponse {
	id: number;
	student_id: number;
	session_id: number;
	initiated_by: string;
	initiated_via: string;
	reason: string;
	attachment_urls: string[] | null;
	status: string;
	requested_at: string;
	reviewed_by: number | null;
	reviewed_at: string | null;
	review_notes: string | null;
}

// In-memory student excuse rows so mock-mode submits visibly stick.
const MOCK_STUDENT_EXCUSE_ROWS: StudentExcuseItemResponse[] = [];

export const StudentExcuseSubmitEndpoint: EndpointDef<StudentExcuseSubmitResponse> = {
	url: '/student/excuse-requests',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
	},
};

export const StudentExcuseListEndpoint: EndpointDef<Paginated<StudentExcuseItemResponse>> = {
	url: '/student/excuse-requests',
	method: 'GET',
	mock: (params) => {
		const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
		const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
		return {
			items: MOCK_STUDENT_EXCUSE_ROWS.slice((page - 1) * size, page * size),
			total: MOCK_STUDENT_EXCUSE_ROWS.length,
			page,
			size,
		};
	},
};

export const StudentExcuseDetailEndpoint: EndpointDef<StudentExcuseItemResponse> = {
	url: '/student/excuse-requests',
	method: 'GET',
	mock: (_params, suffix) => ({
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
	}),
};

// --- Attachment uploads (D24) --------------------------------------------------
//
// Excuse evidence is uploaded straight to storage, so the file bytes never
// pass through the API. The client mints a URL here, PUTs the bytes itself,
// then submits the excuse carrying the returned object_url — the database
// stores URL references only, never file bytes.
//
// POST /upload/presigned-url { filename, size_bytes, content_type? } →
// { upload_url, object_url, object_key, expires_in }. Max 5 MiB
// (ATTACHMENTS_MAX_BYTES), PDF/JPG/PNG/HEIC by extension (case-insensitive),
// max 5 attachments per request (enforced by the excuse schemas).
// Real API by default; mocks only when PUBLIC_MOCK_MODE=true.
export interface PresignedUrlRequest {
	filename: string;
	size_bytes: number;
	content_type?: string;
}

export interface PresignedUrlResponse {
	upload_url: string;
	object_url: string;
	object_key: string;
	expires_in: number;
}

export const UploadPresignedEndpoint: EndpointDef<PresignedUrlResponse> = {
	url: '/upload/presigned-url',
	method: 'POST',
	mock: (_params, _suffix, body) => {
		const input = (body ?? {}) as PresignedUrlRequest;
		const safe = String(input.filename ?? 'evidence').replace(/[^a-zA-Z0-9._-]+/g, '-');
		return {
			upload_url: `mock://upload/${safe}`,
			object_url: `mock://attachments/${safe}`,
			object_key: `attachments/${safe}`,
			expires_in: 3600,
		};
	},
};
// Student face-embedding pull (D29) — live on features/student/router.py
// (GET /student/me/face-embedding?current_version=N). 200 carries the
// base64 blob for a newer version; 204 (client resolves to undefined) means
// the cached version is current; 404 means no enrollment on file.
export interface StudentFaceEmbeddingResponse {
	version: number;
	embedding: string;
}

export const StudentFaceEmbeddingEndpoint: EndpointDef<StudentFaceEmbeddingResponse | undefined> = {
	url: '/student/me/face-embedding',
	method: 'GET',
	mock: () => undefined,
};

// Student schedule — live on features/student/router.py
// (GET /student/schedule, no params; identity from the Bearer token).
// One row per active enrollment ordered by offering_id; empty enrollments
// return { offerings: [] }.
export const StudentScheduleEndpoint: EndpointDef<ScheduleResponse> = {
	url: '/student/schedule',
	method: 'GET',
	mock: () => ({
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
	}),
};

// --- Professor --------------------------------------------------------------
//
// GET /professor/profile is fully implemented on the backend
// (professor/router.py -> ProfessorService.get_self_profile). Password change
// goes through the shared forgot-password recovery wizard (email + OTP code),
// the same process as the student settings page, so no separate endpoint def
// is needed here.

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
		year_level_label: '2nd Year',
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
		year_level_label: '3rd Year',
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
		year_level_label: '1st Year',
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
		year_level_label: '2nd Year',
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
		year_level_label: '4th Year',
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
		year_level_label: '1st Year',
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
		year_level_label: '3rd Year',
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
		year_level_label: '2nd Year',
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
		year_level_label: '2nd Year',
		section: 'A',
		is_active: false,
		face_enrolled: true,
		claim_status: 'Unclaimed',
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
			claim_status: 'Unclaimed',
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
			if (p.program_id !== undefined)
				row.program_code = mockProgramCodeFor(Number(p.program_id));
			if (p.year_level_id !== undefined)
				row.year_level_label = mockYearLabelFor(Number(p.year_level_id));
			return toMockDetail(row);
		}
		return toMockDetail(findMockStudentRow(suffix));
	},
};

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

export const AdminStudentImportEndpoint: EndpointDef<StudentImportResult> = {
	url: '/admin/students/import',
	method: 'POST',
	mock: (_params, _suffix, body) => mockCsvImport(body, 25),
};

// --- Admin face enrollment (3-photo upload, D43) --------------------------------
//
// POST /admin/face-enrollment/{student_id} takes multipart front/left/right
// images and returns the enrollment stamp; GET reads the status. The student
// id rides the suffix like adminStudentDetail. Real API by default; mocks
// only when PUBLIC_MOCK_MODE=true (the mock flips the roster row's
// face_enrolled flag so the list visibly sticks).
export interface AdminFaceEnrollmentUploadResponse {
	student_id: number;
	face_enrolled_at: string;
	face_embedding_version: number;
}

export interface AdminFaceEnrollmentStatusResponse {
	enrolled: boolean;
	face_enrolled_at?: string;
	face_embedding_version?: number;
}

export const AdminFaceEnrollmentUploadEndpoint: EndpointDef<AdminFaceEnrollmentUploadResponse> = {
	url: '/admin/face-enrollment',
	method: 'POST',
	mock: (_params, suffix) => {
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
	},
};

export const AdminFaceEnrollmentStatusEndpoint: EndpointDef<AdminFaceEnrollmentStatusResponse> = {
	url: '/admin/face-enrollment',
	method: 'GET',
	mock: (_params, suffix) => {
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
	},
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

export const AdminProfessorsEndpoint: EndpointDef<Paginated<AdminProfessorResponse>> = {
	url: '/admin/professors',
	method: 'GET',
	mock: (params) => mockAdminProfessorsList(params),
};

export const AdminProfessorCreateEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
	},
};

export const AdminProfessorDetailEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
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
	},
};

export const AdminProfessorImportEndpoint: EndpointDef<ProfessorImportResult> = {
	url: '/admin/professors/import',
	method: 'POST',
	mock: (_params, _suffix, body) => mockCsvImport(body, 5),
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
		enrolled_count: 25,
		is_active: true,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	},
];

export const AdminOfferingsEndpoint: EndpointDef<Paginated<AdminOfferingResponse>> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (params) => {
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
	},
};

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

export const AdminCoursesEndpoint: EndpointDef<Paginated<AdminCourseResponse>> = {
	url: '/admin/courses',
	method: 'GET',
	mock: (params) => {
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
	},
};

export const AdminCourseCreateEndpoint: EndpointDef<AdminCourseResponse> = {
	url: '/admin/courses',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
	},
};

export const AdminCourseDetailEndpoint: EndpointDef<AdminCourseResponse> = {
	url: '/admin/courses',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
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
	},
};

export const AdminCourseImportEndpoint: EndpointDef<CourseImportResult> = {
	url: '/admin/courses/import',
	method: 'POST',
	mock: (_params, _suffix, body) => mockCsvImport(body, 5),
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
	semester_weeks?: unknown;
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
	is_active?: unknown;
}

const findMockOfferingRow = (suffix?: string): AdminOfferingResponse => {
	const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
	const row = MOCK_ADMIN_OFFERINGS.find((r) => r.id === id);
	if (!row) throw new Error('Offering not found.');
	return row;
};

// D77 mock components: the offering rows above are the single source of
// truth (each carries its components array); these helpers build and
// maintain them the way the live service does.
const mockComponentId = (): number =>
	Math.max(0, ...MOCK_ADMIN_OFFERINGS.flatMap((r) => r.components.map((c) => c.id))) + 1;

const refreshMockSessionTypes = (row: AdminOfferingResponse): void => {
	row.session_types = [
		...new Set(
			row.components.filter((c) => c.is_active).map((c) => c.session_type)
		),
	];
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

export const AdminOfferingCreateEndpoint: EndpointDef<AdminOfferingResponse> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
			semester_weeks: Number(p.semester_weeks ?? 18),
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
	},
};

export const AdminOfferingDetailEndpoint: EndpointDef<AdminOfferingResponse> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
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
			if (p.semester_weeks !== undefined) row.semester_weeks = Number(p.semester_weeks);
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
	},
};

// Offering components (D77: per-type schedules) ---------------------------------
//
// Live routes on course/offering_router.py. Same suffix convention:
// `/{oid}/components`, `/{oid}/components/{cid}`.

export const AdminOfferingComponentsEndpoint: EndpointDef<OfferingComponentResponse[]> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (_params, suffix) =>
		findMockOfferingRow(suffix).components.filter((c) => c.is_active),
};

export const AdminOfferingComponentCreateEndpoint: EndpointDef<OfferingComponentResponse> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: (_params, suffix, body) => {
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
	},
};

export const AdminOfferingComponentDetailEndpoint: EndpointDef<OfferingComponentResponse> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
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
	},
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
		assigned_by: 1,
		assigned_at: new Date().toISOString(),
	},
];

interface MockAssignmentPayload {
	professor_id?: unknown;
	is_primary?: unknown;
	effective_from?: unknown;
	effective_to?: unknown;
	semester?: unknown;
}

// Open-ended dates compare as a far-future sentinel, mirroring the backend
// overlap check (NULL effective_to = ongoing).
const mockDateOrOngoing = (value: string | null | undefined): string =>
	value ?? '9999-12-31';

export const AdminOfferingProfessorsEndpoint: EndpointDef<
	AdminAssignmentResponse[] | AdminAssignmentResponse
> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (_params, suffix, body, method) => {
		const offeringId = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		if (!Number.isFinite(offeringId) || offeringId <= 0) throw new Error('Offering not found.');
		if (method === 'DELETE') {
			const professorId = parseInt(suffix?.match(/\/professors\/(\d+)/)?.[1] ?? '', 10);
			const row = MOCK_ADMIN_ASSIGNMENTS.find(
				(a) => a.offering_id === offeringId && a.professor_id === professorId
			);
			if (!row) throw new Error('Assignment not found.');
			row.effective_to = new Date().toISOString().slice(0, 10);
			return mockNoContent();
		}
		if (method === 'POST') {
			const p = (body ?? {}) as MockAssignmentPayload;
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
			const row: AdminAssignmentResponse = {
				offering_id: offeringId,
				professor_id: professorId,
				is_primary: Boolean(p.is_primary),
				effective_from: effectiveFrom,
				effective_to: effectiveTo,
				semester: String(p.semester ?? '').trim(),
				assigned_by: 1,
				assigned_at: new Date().toISOString(),
			};
			MOCK_ADMIN_ASSIGNMENTS.push(row);
			return row;
		}
		return MOCK_ADMIN_ASSIGNMENTS.filter((a) => a.offering_id === offeringId);
	},
};

// Roster mock: derived from the student mock rows so the section filter has
// real values to narrow. `enrolled_at` reuses the student created_at.
export const AdminOfferingRosterEndpoint: EndpointDef<Paginated<AdminRosterItemResponse>> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: (params) => {
		let rows: AdminRosterItemResponse[] = MOCK_ADMIN_STUDENT_ROWS.map((s) => ({
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
	},
};

export const AdminOfferingBulkEnrollEndpoint: EndpointDef<AdminBulkEnrollResult> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: () => ({ enrolled: 3, skipped: 1, errors: [] }),
};

// Unenroll one student —
// DELETE /admin/offerings/{id}/students/{student_number} (204, no body).
// Removes the enrollment link row only; past attendance rows keep their
// student+session identity. No mock: the roster mock fixture is static, so a
// mock success would leave the removed row on screen; mock mode instead
// throws the explicit mock_mode error like other unwired mutations.
export const AdminOfferingUnenrollEndpoint: EndpointDef<void> = {
	url: '/admin/offerings',
	method: 'DELETE',
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
	mock: (_params, suffix, _body, method) => {
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
	},
};

export const AdminProgramImportEndpoint: EndpointDef<ProgramImportResult> = {
	url: '/admin/programs/import',
	method: 'POST',
	mock: (_params, _suffix, body) => mockCsvImport(body, 5),
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

export const AdminAnalyticsOverviewEndpoint: EndpointDef<AnalyticsOverviewResponse> = {
	url: '/admin/analytics/overview',
	method: 'GET',
	mock: (params) => {
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
	},
};

export const AdminAnalyticsComparisonEndpoint: EndpointDef<{ items: AnalyticsComparisonItemResponse[] }> = {
	url: '/admin/analytics/course-comparison',
	method: 'GET',
	mock: (params) => {
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
	},
};

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

export const AdminAnalyticsTrendsEndpoint: EndpointDef<{ items: AnalyticsTrendItemResponse[] }> = {
	url: '/admin/analytics/trends',
	method: 'GET',
	mock: (params) => {
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
	},
};

export const AdminAnalyticsAtRiskEndpoint: EndpointDef<{ items: AnalyticsAtRiskItemResponse[] }> = {
	url: '/admin/analytics/at-risk',
	method: 'GET',
	mock: (params) => {
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
	},
};

export const AdminAnalyticsRefreshRiskEndpoint: EndpointDef<RiskRefreshResponse> = {
	url: '/admin/analytics/refresh-risk',
	method: 'POST',
	mock: () => {
		const now = new Date().toISOString();
		for (const row of MOCK_AT_RISK_ROWS) row.computed_at = now;
		const high = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'high').length;
		const medium = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'medium').length;
		const low = MOCK_AT_RISK_ROWS.filter((r) => r.risk_level === 'low').length;
		return { processed: MOCK_AT_RISK_ROWS.length, high, medium, low, duration_ms: 42 };
	},
};

// Dry-run staging review (backend #137): GET lists staged rows without
// touching live scores; POST copies unpromoted rows into the live scores.
// Mocks are empty by design — fabricated staged scores would imply a batch
// that never ran, so mock mode renders the "no dry-run yet" hint instead.
export const AdminRiskStagingEndpoint: EndpointDef<RiskStagingResponse> = {
	url: '/admin/analytics/risk-staging',
	method: 'GET',
	mock: () => ({ items: [], total: 0, page: 1, size: 20 }),
};

export const AdminRiskStagingPromoteEndpoint: EndpointDef<PromoteStagingResponse> = {
	url: '/admin/analytics/risk-staging/promote',
	method: 'POST',
	mock: () => ({ promoted: 0, skipped: 0, duration_ms: 0 }),
};

export const AdminAttendanceOverviewEndpoint: EndpointDef<{ items: AttendanceOverviewItemResponse[] }> = {
	url: '/admin/attendance/overview',
	method: 'GET',
	mock: (params) => {
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
	},
};

const MOCK_SCAN_STATUSES = ['present', 'late', 'present', 'present', 'excused', 'late'];

export const AdminRecentScansEndpoint: EndpointDef<{ items: RecentScanResponse[] }> = {
	url: '/admin/attendance/recent-scans',
	method: 'GET',
	mock: (params) => {
		const limit = Math.min(Math.max(parseInt(params?.limit ?? '10', 10) || 10, 1), 100);
		const sorted = [...MOCK_ANALYTICS_SESSIONS].sort((a, b) => (a.date < b.date ? 1 : -1));
		const items: RecentScanResponse[] = sorted.slice(0, limit).map((s, i) => ({
			id: i + 1,
			scanned_at: `${s.date}T${String(8 + (i % 9)).padStart(2, '0')}:${String((i * 7) % 60).padStart(2, '0')}:00.000Z`,
			student_name: MOCK_ADMIN_STUDENT_ROWS[i % MOCK_ADMIN_STUDENT_ROWS.length]
				? [MOCK_ADMIN_STUDENT_ROWS[i % MOCK_ADMIN_STUDENT_ROWS.length].first_name, MOCK_ADMIN_STUDENT_ROWS[i % MOCK_ADMIN_STUDENT_ROWS.length].last_name].join(' ')
				: 'Unknown',
			course_code: s.courseCode,
			status: MOCK_SCAN_STATUSES[i % MOCK_SCAN_STATUSES.length],
		}));
		return { items };
	},
};

// --- Admin system settings (live backend) -------------------------------------
// api-contracts.md §System Settings & Backups: GET/PATCH /admin/system/settings
// (app_settings KV seeded from env defaults), GET/POST /admin/backups,
// GET /admin/backups/{id}/download, POST /admin/system/sync/flush,
// POST /admin/system/cleanup — all served by the mounted features/system
// router. Real API by default; the mocks below are only consulted when
// PUBLIC_MOCK_MODE=true, where they mutate module state so saves visibly stick.

export interface SystemSettingsResponse {
	geofence_default_radius: number;
	present_window_default: number;
	late_window_default: number;
	backup_retention_daily: number;
	backup_retention_monthly: number;
	pending_sync_count: number;
}

export interface BackupLogItemResponse {
	id: number;
	filename: string;
	kind: 'full' | 'analytics';
	size_bytes: number;
	storage_backend: 'local' | 's3';
	started_at: string;
	finished_at: string | null;
	status: 'started' | 'completed' | 'failed';
}

const MOCK_SYSTEM_SETTINGS: SystemSettingsResponse = {
	geofence_default_radius: 50,
	present_window_default: 5,
	late_window_default: 10,
	backup_retention_daily: 30,
	backup_retention_monthly: 12,
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

export const SystemSettingsGetEndpoint: EndpointDef<SystemSettingsResponse> = {
	url: '/admin/system/settings',
	method: 'GET',
	mock: () => ({ ...MOCK_SYSTEM_SETTINGS })
};

export const SystemSettingsPatchEndpoint: EndpointDef<SystemSettingsResponse> = {
	url: '/admin/system/settings',
	method: 'PATCH',
	mock: (_params, _suffix, body) => {
		const patch = (body ?? {}) as Partial<SystemSettingsResponse>;
		const numericKeys = [
			'geofence_default_radius',
			'present_window_default',
			'late_window_default',
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
	}
};

export const SystemBackupsEndpoint: EndpointDef<{ items: BackupLogItemResponse[] }> = {
	url: '/admin/backups',
	method: 'GET',
	mock: () => ({ items: [...MOCK_BACKUP_ROWS] })
};

export const SystemBackupTriggerEndpoint: EndpointDef<{ backup_id: number; status: 'started' }> = {
	url: '/admin/backups',
	method: 'POST',
	mock: () => {
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
	}
};

export const SystemSyncFlushEndpoint: EndpointDef<{ processed: number; succeeded: number; failed: number }> = {
	url: '/admin/system/sync/flush',
	method: 'POST',
	mock: () => {
		const processed = MOCK_SYSTEM_SETTINGS.pending_sync_count;
		MOCK_SYSTEM_SETTINGS.pending_sync_count = 0;
		return { processed, succeeded: processed, failed: 0 };
	}
};

export const SystemCleanupEndpoint: EndpointDef<{ removed: number }> = {
	url: '/admin/system/cleanup',
	method: 'POST',
	mock: () => ({ removed: 14 })
};

// --- Admin audit logs (live backend, api-contracts §System Settings & Backups) --
//
// GET /admin/audit-logs?entity_type&action&performed_by&date_from&date_to&page&size
// returns { items: [{ id, action, entity_type, entity_id, old_value, new_value,
// performed_by, performed_at }] }. The mock rows below mirror that contract
// shape (mapped to the legacy feed view-model in features/admin/audit/service.ts
// until the page migrates to the native columns); mocks only when
// PUBLIC_MOCK_MODE=true.

const mockAuditAt = (daysAgo: number, time: string): string => {
	const date = new Date();
	date.setHours(0, 0, 0, 0);
	date.setDate(date.getDate() - daysAgo);
	return `${date.toISOString().slice(0, 10)}T${time}.000Z`;
};

const MOCK_AUDIT_ROWS: AuditLogItemResponse[] = [
	{ id: 1, action: 'open', entity_type: 'session', entity_id: 41, old_value: null, new_value: 'offering 1 · 60 min', performed_by: 'J. Smith', performed_at: mockAuditAt(0, '08:55:00') },
	{ id: 2, action: 'import', entity_type: 'student', entity_id: null, old_value: null, new_value: '25 imported · 0 duplicates', performed_by: 'Admin', performed_at: mockAuditAt(0, '08:30:00') },
	{ id: 3, action: 'update', entity_type: 'year_level', entity_id: 2, old_value: '1st Semester, 2nd Semester', new_value: '1st Semester, 2nd Semester, Midyear', performed_by: 'Admin', performed_at: mockAuditAt(0, '08:00:00') },
	{ id: 4, action: 'approve', entity_type: 'excuse', entity_id: 7, old_value: 'pending', new_value: 'approved · quick excuse · medical', performed_by: 'M. Garcia', performed_at: mockAuditAt(1, '15:20:00') },
	{ id: 5, action: 'assign', entity_type: 'course_professor', entity_id: null, old_value: null, new_value: 'J. Smith → offering 1 · primary', performed_by: 'Admin', performed_at: mockAuditAt(1, '14:05:00') },
	{ id: 6, action: 'update', entity_type: 'maintenance', entity_id: null, old_value: null, new_value: 'risk batch · processed 90 · high 4 · medium 11', performed_by: 'system', performed_at: mockAuditAt(1, '11:47:00') },
	{ id: 7, action: 'enroll', entity_type: 'enrollment', entity_id: null, old_value: null, new_value: '3 enrolled · 1 skipped · offering 1', performed_by: 'Admin', performed_at: mockAuditAt(2, '16:33:00') },
	{ id: 8, action: 'create', entity_type: 'face_enrollment', entity_id: 1, old_value: null, new_value: '3 photos · embedding v2', performed_by: 'Admin', performed_at: mockAuditAt(2, '10:12:00') },
	{ id: 9, action: 'create', entity_type: 'backup', entity_id: 31, old_value: null, new_value: 'pg_dump · AES-256-GCM · 41 MB', performed_by: 'system', performed_at: mockAuditAt(3, '03:00:00') },
	{ id: 10, action: 'close', entity_type: 'session', entity_id: 38, old_value: null, new_value: 'present 24 · late 3 · absent 3', performed_by: 'J. Smith', performed_at: mockAuditAt(3, '09:44:00') },
	{ id: 11, action: 'lock', entity_type: 'user', entity_id: 19, old_value: null, new_value: '5 failed attempts', performed_by: 'system', performed_at: mockAuditAt(4, '13:29:00') },
	{ id: 12, action: 'login_failed', entity_type: 'user', entity_id: 19, old_value: null, new_value: 'attempt 5 · wrong password', performed_by: null, performed_at: mockAuditAt(4, '13:24:00') },
	{ id: 13, action: 'update', entity_type: 'course_offering', entity_id: 2, old_value: 'present 5 min', new_value: 'present 10 min', performed_by: 'Admin', performed_at: mockAuditAt(5, '10:02:00') },
	{ id: 14, action: 'archive', entity_type: 'course', entity_id: 4, old_value: 'is_active=true', new_value: 'is_active=false', performed_by: 'Admin', performed_at: mockAuditAt(5, '09:15:00') },
	{ id: 15, action: 'create', entity_type: 'excuse', entity_id: 6, old_value: null, new_value: 'pending professor review', performed_by: 'B. Cruz', performed_at: mockAuditAt(6, '14:51:00') },
	{ id: 16, action: 'create', entity_type: 'course', entity_id: 2, old_value: null, new_value: 'CS102 Data Structures · 3 units', performed_by: 'Admin', performed_at: mockAuditAt(7, '08:05:00') },
	{ id: 17, action: 'create', entity_type: 'course_offering', entity_id: 3, old_value: null, new_value: 'CS101 BSIT 1st Year 1st Sem 2025-2026', performed_by: 'Admin', performed_at: mockAuditAt(7, '08:02:00') },
	{ id: 18, action: 'open', entity_type: 'session', entity_id: 35, old_value: null, new_value: 'offering 2 · 90 min', performed_by: 'M. Garcia', performed_at: mockAuditAt(8, '17:40:00') },
	{ id: 19, action: 'unassign', entity_type: 'course_professor', entity_id: null, old_value: 'J. Smith → offering 3', new_value: 'effective_to today (handover)', performed_by: 'Admin', performed_at: mockAuditAt(9, '12:18:00') },
	{ id: 20, action: 'update', entity_type: 'app_setting', entity_id: null, old_value: 'present_window 5 min', new_value: 'present_window 10 min', performed_by: 'Admin', performed_at: mockAuditAt(10, '09:31:00') },
	{ id: 21, action: 'unlock', entity_type: 'user', entity_id: 19, old_value: 'locked', new_value: 'unlocked after verification', performed_by: 'Admin', performed_at: mockAuditAt(12, '07:58:00') },
	{ id: 22, action: 'password_reset', entity_type: 'user', entity_id: 19, old_value: null, new_value: 'temp password issued · must_change_password', performed_by: 'Admin', performed_at: mockAuditAt(12, '08:10:00') },
];

export const AdminAuditLogsEndpoint: EndpointDef<Paginated<AuditLogItemResponse>> = {
	url: '/admin/audit-logs',
	method: 'GET',
	mock: (params) => {
		let rows = [...MOCK_AUDIT_ROWS];
		// Contract filters AND-combine; a blank value means "no filter".
		if (params?.entity_type) {
			rows = rows.filter((r) => r.entity_type === params.entity_type);
		}
		if (params?.action) {
			rows = rows.filter((r) => r.action === params.action);
		}
		if (params?.performed_by) {
			const needle = params.performed_by.trim().toLowerCase();
			if (needle) {
				rows = rows.filter((r) => String(r.performed_by ?? '').toLowerCase().includes(needle));
			}
		}
		if (params?.date_from) {
			rows = rows.filter((r) => r.performed_at.slice(0, 10) >= params.date_from!);
		}
		if (params?.date_to) {
			rows = rows.filter((r) => r.performed_at.slice(0, 10) <= params.date_to!);
		}
		rows.sort((a, b) => (a.performed_at < b.performed_at ? 1 : -1));
		const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
		const total = rows.length;
		const totalPages = Math.max(1, Math.ceil(total / size));
		const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), totalPages);
		return { items: rows.slice((page - 1) * size, page * size), total, page, size };
	},
};

// Academic-structure changes mirror api-contracts
// GET /admin/system/academic-structure exactly (D38).
const MOCK_STRUCTURE_ROWS: StructureChangeResponse[] = [
	{ id: 1, action: 'term_added', entity_type: 'year_level', entity_id: 2, old_value: '1st Semester, 2nd Semester', new_value: '1st Semester, 2nd Semester, Midyear', performed_by: 'Admin', performed_at: mockAuditAt(0, '08:00:00') },
	{ id: 2, action: 'course_archived', entity_type: 'course', entity_id: 4, old_value: 'is_active=true', new_value: 'is_active=false', performed_by: 'Admin', performed_at: mockAuditAt(5, '09:15:00') },
	{ id: 3, action: 'course_created', entity_type: 'course', entity_id: 2, old_value: null, new_value: 'CS102 Data Structures · 3 units', performed_by: 'Admin', performed_at: mockAuditAt(7, '08:05:00') },
	{ id: 4, action: 'offering_created', entity_type: 'course_offering', entity_id: 3, old_value: null, new_value: 'CS101 BSIT 1st Year 1st Sem 2025-2026', performed_by: 'Admin', performed_at: mockAuditAt(7, '08:02:00') },
	{ id: 5, action: 'year_level_created', entity_type: 'year_level', entity_id: 6, old_value: null, new_value: '6th Year · BSCS', performed_by: 'Admin', performed_at: mockAuditAt(9, '10:00:00') },
	{ id: 6, action: 'program_renamed', entity_type: 'program', entity_id: 2, old_value: 'BS Information Technology', new_value: 'BS Information Technology (morning)', performed_by: 'Admin', performed_at: mockAuditAt(12, '11:30:00') },
];

export const AdminStructureChangesEndpoint: EndpointDef<{ items: StructureChangeResponse[] }> = {
	url: '/admin/system/academic-structure',
	method: 'GET',
	mock: () => ({ items: [...MOCK_STRUCTURE_ROWS] }),
};

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

export const AdminUsersEndpoint: EndpointDef<Paginated<AdminUserResponse>> = {
	url: '/admin/users',
	method: 'GET',
	mock: (params) => mockAdminUsersList(params),
};

export const AdminUserCreateEndpoint: EndpointDef<AdminUserCreateResponse> = {
	url: '/admin/users',
	method: 'POST',
	mock: (_params, _suffix, body) => {
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
		if (MOCK_ADMIN_USER_ROWS.some((r) => r.email.toLowerCase() === email)) {
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
	},
};

export const AdminUserDeactivateEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'PATCH',
	mock: (_params, suffix) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
		if (!row) throw new Error('User not found.');
		row.is_active = false;
		return undefined;
	},
};

export const AdminUserReactivateEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'PATCH',
	mock: (_params, suffix) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
		if (!row) throw new Error('User not found.');
		row.is_active = true;
		return undefined;
	},
};

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

export const AdminUserResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/users',
	method: 'POST',
	mock: (_params, suffix, _body, method) => {
		if (method !== 'POST') throw new Error('Password reset is a POST.');
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		const row = MOCK_ADMIN_USER_ROWS.find((r) => r.id === id);
		if (!row) throw new Error('User not found.');
		row.must_change_password = true;
		return mockTempPassword();
	},
};

export const AdminStudentResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/students',
	method: 'POST',
	mock: (_params, suffix) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		if (!MOCK_ADMIN_STUDENT_ROWS.some((r) => r.id === id)) throw new Error('Student not found.');
		return mockTempPassword();
	},
};

export const AdminProfessorResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/professors',
	method: 'POST',
	mock: (_params, suffix) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '', 10);
		if (!MOCK_ADMIN_PROFESSOR_ROWS.some((r) => r.id === id)) {
			throw new Error('Professor not found.');
		}
		return mockTempPassword();
	},
};

// --- Professor excuse queue --------------------------------------------------
//
// Live routes on features/excuse/professor_router.py under the shared
// /professor mount (never mounted twice). The list row is deliberately bare:
// no student identity, course labels, or original status — those join
// client-side in features/excuse/service.ts (same convention as the professor
// attendance ledger). Review is POST with the id riding the suffix
// (`/{rid}/review`). Per-record actions ride
// `/professor/sessions/{sid}/attendance/{stid}/excuse` (POST quick, PATCH
// edit, DELETE revoke); bulk rides `/{sid}/excuse-all-absent`. Like the
// queue defs these carry no `mock`: mock mode is served by the in-memory
// store in features/excuse/service.ts (see api/client.ts stub fallback).
export interface ExcuseRequestReadResponse {
	id: number;
	student_id: number;
	session_id: number;
	initiated_by: string;
	initiated_via: string;
	reason: string;
	attachment_urls: string[] | null;
	status: string;
	requested_at: string;
	reviewed_by: number | null;
	reviewed_at: string | null;
	review_notes: string | null;
}

export interface ExcuseReviewBody {
	status: 'approved' | 'rejected';
	review_notes?: string;
}

export const ExcuseListEndpoint: EndpointDef<Paginated<ExcuseRequestReadResponse>> = {
	url: '/professor/excuse-requests',
	method: 'GET',
};

export const ExcuseReviewEndpoint: EndpointDef<ExcuseRequestReadResponse> = {
	url: '/professor/excuse-requests',
	method: 'POST',
};

// Professor-initiated excuse (Path A quick / Path B with evidence) —
// POST /professor/sessions/{sid}/attendance/{stid}/excuse. Path is chosen
// server-side by presence of the `attachment_urls` key (absent → quick,
// present → evidence); the quick modal collects files via the D24 presigned
// flow and sends reason-only bodies when there are none.
export interface ExcuseActionBody {
	reason: string;
	attachment_urls?: string[];
}

export interface ExcuseActionResponse {
	excuse_request_id: number;
	status: string;
	original_status: string | null;
	new_status: string;
}

export const ExcuseQuickEndpoint: EndpointDef<ExcuseActionResponse> = {
	url: '/professor/sessions',
	method: 'POST',
};

// Edit a professor-issued excuse —
// PATCH /professor/sessions/{sid}/attendance/{stid}/excuse
// { reason?: 10..2000 chars, review_notes?: ≤2000 } (at least one required).
export interface ExcuseEditBody {
	reason?: string;
	review_notes?: string;
}

export const ExcuseEditEndpoint: EndpointDef<ExcuseRequestReadResponse> = {
	url: '/professor/sessions',
	method: 'PATCH',
};

// Revoke a professor-issued excuse —
// DELETE /professor/sessions/{sid}/attendance/{stid}/excuse (no body).
// Sets the excuse rejected and restores attendance to original_status.
export interface ExcuseRevokeResponse {
	reverted_to: string | null;
}

export const ExcuseRevokeEndpoint: EndpointDef<ExcuseRevokeResponse> = {
	url: '/professor/sessions',
	method: 'DELETE',
};

// Excuse all absent records in a session (idempotent) —
// POST /professor/sessions/{sid}/excuse-all-absent { reason: 10..2000 }.
export interface ExcuseBulkResponse {
	excused_count: number;
	reason: string;
}

export const ExcuseBulkEndpoint: EndpointDef<ExcuseBulkResponse> = {
	url: '/professor/sessions',
	method: 'POST',
};

// --- Professor reports (live aggregates, D37) ---------------------------------
//
// GET /professor/reports/all-courses, /comparison, /trends. The reports page
// used to recompute all three client-side from GET /professor/sessions/history;
// these defs call the dedicated aggregates instead, keeping the history
// derivation as the offline/mock fallback in features/report/service.ts.
// Real API by default; mocks only when PUBLIC_MOCK_MODE=true.
export interface ProfessorReportsAllCoursesItemResponse {
	date: string;
	total_sessions: number;
	total_students: number;
	compliance_rate: number;
	participation_rate: number;
}

export interface ProfessorReportsAllCoursesResponse {
	items: ProfessorReportsAllCoursesItemResponse[];
	avg_compliance: number;
	avg_participation: number;
}

export const ProfessorReportsAllCoursesEndpoint: EndpointDef<ProfessorReportsAllCoursesResponse> = {
	url: '/professor/reports/all-courses',
	method: 'GET',
	mock: (params) => {
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
	},
};

export interface ProfessorReportsComparisonItemResponse {
	course_id: number;
	course_code: string;
	program_id: number;
	year_level_id: number;
	compliance_rate: number;
	participation_rate: number;
	total_sessions: number;
}

export const ProfessorReportsComparisonEndpoint: EndpointDef<{
	items: ProfessorReportsComparisonItemResponse[];
}> = {
	url: '/professor/reports/comparison',
	method: 'GET',
	mock: () => ({
		items: [
			{ course_id: 1, course_code: 'CS101', program_id: 1, year_level_id: 1, compliance_rate: 0.84, participation_rate: 0.92, total_sessions: 12 },
			{ course_id: 2, course_code: 'MATH101', program_id: 1, year_level_id: 1, compliance_rate: 0.71, participation_rate: 0.83, total_sessions: 9 },
		],
	}),
};

export interface ProfessorReportsTrendItemResponse {
	date: string;
	course_id: number;
	course_code: string;
	rate: number;
}

export const ProfessorReportsTrendsEndpoint: EndpointDef<{
	items: ProfessorReportsTrendItemResponse[];
}> = {
	url: '/professor/reports/trends',
	method: 'GET',
	mock: (params) => {
		const base = (params?.date_from ?? new Date().toISOString().slice(0, 10)).slice(0, 10);
		return {
			items: [0, 1, 2].map((i) => ({
				date: base,
				course_id: 1,
				course_code: 'CS101',
				rate: 0.8 - i * 0.02,
			})),
		};
	},
};

// --- Admin excuses (read-only queue) ------------------------------------------
//
// GET /admin/excuses?status&page&size — same ExcuseRequest row as the professor
// queue. Admins review via the professor flow; this def is list-only so the
// admin side can surface workload without duplicating review actions.
// Real API by default; mocks only when PUBLIC_MOCK_MODE=true.
export const AdminExcusesEndpoint: EndpointDef<Paginated<ExcuseRequestReadResponse>> = {
	url: '/admin/excuses',
	method: 'GET',
	mock: (params) => {
		const now = new Date().toISOString();
		const rows: ExcuseRequestReadResponse[] = [
			{ id: 901, student_id: 1, session_id: 41, initiated_by: 'student', initiated_via: 'request', reason: 'Medical appointment with supporting documents attached for review.', attachment_urls: [], status: 'pending', requested_at: now, reviewed_by: null, reviewed_at: null, review_notes: null },
			{ id: 902, student_id: 2, session_id: 38, initiated_by: 'student', initiated_via: 'request', reason: 'Family emergency, barangay certificate available on request.', attachment_urls: [], status: 'pending', requested_at: now, reviewed_by: null, reviewed_at: null, review_notes: null },
		];
		const status = params?.status;
		const filtered = status ? rows.filter((r) => r.status === status) : rows;
		const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
		const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
		return { items: filtered.slice((page - 1) * size, page * size), total: filtered.length, page, size };
	},
};

// --- Admin liveness review (flagged-scan queue) --------------------------------
//
// GET /admin/attendance/liveness-review?status&page&size lists records whose
// face_match_score fell in [0.65, 0.70) with validation_status pending;
// PATCH /admin/attendance/liveness-review/{id}/resolve approves (restores
// present/late) or rejects them. Real API by default; mocks only when
// PUBLIC_MOCK_MODE=true.
export interface LivenessReviewItemResponse {
	id: number;
	student_number: string;
	student_name: string;
	session_code: string;
	course_code: string;
	face_match_score: number;
	evidence: Record<string, unknown>;
	scanned_at: string;
}

export interface LivenessReviewResolveBody {
	decision: 'approve' | 'reject';
	note?: string;
}

export interface LivenessReviewResolveResponse {
	id: number;
	status: string;
	reviewed_by: number;
	reviewed_at: string;
}

const MOCK_LIVENESS_ROWS: LivenessReviewItemResponse[] = [
	{ id: 501, student_number: '24-2132', student_name: 'Alice Santos', session_code: 'A7X-9K2M', course_code: 'CS101', face_match_score: 0.67, evidence: { review: true, blink_detected: true, head_turn_left: true, head_turn_right: true }, scanned_at: new Date().toISOString() },
	{ id: 502, student_number: '24-1045', student_name: 'Bob Cruz', session_code: 'B3M-7Q8N', course_code: 'MATH101', face_match_score: 0.68, evidence: { review: true, blink_detected: true, head_turn_left: true, head_turn_right: false }, scanned_at: new Date().toISOString() },
];

export const LivenessReviewListEndpoint: EndpointDef<Paginated<LivenessReviewItemResponse>> = {
	url: '/admin/attendance/liveness-review',
	method: 'GET',
	mock: (params) => {
		const size = Math.min(Math.max(parseInt(params?.size ?? '20', 10) || 20, 1), 100);
		const page = Math.min(Math.max(parseInt(params?.page ?? '1', 10) || 1, 1), 1);
		return { items: [...MOCK_LIVENESS_ROWS], total: MOCK_LIVENESS_ROWS.length, page, size };
	},
};

export const LivenessReviewResolveEndpoint: EndpointDef<LivenessReviewResolveResponse> = {
	url: '/admin/attendance/liveness-review',
	method: 'PATCH',
	mock: (_params, suffix, body) => {
		const id = parseInt(suffix?.match(/\/(\d+)/)?.[1] ?? '0', 10) || MOCK_LIVENESS_ROWS[0].id;
		const decision = (body as LivenessReviewResolveBody | undefined)?.decision ?? 'approve';
		return { id, status: decision === 'approve' ? 'present' : 'rejected', reviewed_by: 1, reviewed_at: new Date().toISOString() };
	},
};

// Endpoint registry
// Named, strongly-typed endpoint definitions keyed for the apiCall() layer.
export const endpoints = {
	// Session QR
	sessionQR: SessionQREndpoint,
	// Attendance scan
	attendanceScan: AttendanceScanEndpoint,
	// Scan precheck (D27 step-2 gate, read-only)
	attendancePrecheck: AttendancePrecheckEndpoint,
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
	authLoginOtpVerify: AuthLoginOtpVerifyEndpoint,
	authLoginOtpResend: AuthLoginOtpResendEndpoint,
	authRefresh: AuthRefreshEndpoint,
	authMe: AuthMeEndpoint,
	authMfaVerify: AuthMfaVerifyEndpoint,
	authMfaSetup: AuthMfaSetupEndpoint,
	authMfaDisable: AuthMfaDisableEndpoint,
	authMfaBackupCodesGenerate: AuthMfaBackupCodesGenerateEndpoint,
	authMfaBackupCodesSummary: AuthMfaBackupCodesSummaryEndpoint,
	authChangePassword: AuthChangePasswordEndpoint,
	authForgotPassword: ForgotPasswordEndpoint,
	authForgotPasswordVerify: ForgotPasswordVerifyEndpoint,
	authResetPassword: ResetPasswordEndpoint,
	authSecurityQuestion: SecurityQuestionEndpoint,
	// Student
	studentProfile: StudentProfileEndpoint,
	studentDashboard: StudentDashboardEndpoint,
	studentHistory: StudentHistoryEndpoint,
	studentFaceEmbedding: StudentFaceEmbeddingEndpoint,
	studentSchedule: StudentScheduleEndpoint,
	studentExcuseSubmit: StudentExcuseSubmitEndpoint,
	studentExcuseList: StudentExcuseListEndpoint,
	studentExcuseDetail: StudentExcuseDetailEndpoint,
	// Attachment uploads (D24 presigned flow; bytes never pass the API)
	uploadPresigned: UploadPresignedEndpoint,
	// Professor
	professorProfile: ProfessorProfileEndpoint,
	professorCourses: ProfessorCoursesEndpoint,
	// Professor excuse queue (list + review live; quick/edit/revoke/bulk live
	// by integer id — only the typed-number quick flow stays in-memory; the
	// quick modal collects evidence via the D24 presigned flow)
	excuseList: ExcuseListEndpoint,
	excuseReview: ExcuseReviewEndpoint,
	// Professor per-record excuse actions + bulk (suffix carries the ids)
	excuseQuick: ExcuseQuickEndpoint,
	excuseEdit: ExcuseEditEndpoint,
	excuseRevoke: ExcuseRevokeEndpoint,
	excuseBulk: ExcuseBulkEndpoint,
	// Professor reports (live aggregates; history derivation stays the fallback)
	professorReportsAllCourses: ProfessorReportsAllCoursesEndpoint,
	professorReportsComparison: ProfessorReportsComparisonEndpoint,
	professorReportsTrends: ProfessorReportsTrendsEndpoint,
	// Admin excuses (read-only queue)
	adminExcuses: AdminExcusesEndpoint,
	// Admin liveness review (flagged-scan queue + resolve)
	livenessReviewList: LivenessReviewListEndpoint,
	livenessReviewResolve: LivenessReviewResolveEndpoint,
	// Admin system settings (live backend)
	systemSettings: SystemSettingsGetEndpoint,
	systemSettingsPatch: SystemSettingsPatchEndpoint,
	systemBackups: SystemBackupsEndpoint,
	systemBackupTrigger: SystemBackupTriggerEndpoint,
	systemSyncFlush: SystemSyncFlushEndpoint,
	systemCleanup: SystemCleanupEndpoint,
	// Admin (students + professors)
	adminStudents: AdminStudentsEndpoint,
	adminStudentCreate: AdminStudentCreateEndpoint,
	adminStudentDetail: AdminStudentDetailEndpoint,
	adminStudentImport: AdminStudentImportEndpoint,
	adminFaceEnrollmentUpload: AdminFaceEnrollmentUploadEndpoint,
	adminFaceEnrollmentStatus: AdminFaceEnrollmentStatusEndpoint,
	adminProfessors: AdminProfessorsEndpoint,
	adminProfessorCreate: AdminProfessorCreateEndpoint,
	adminProfessorDetail: AdminProfessorDetailEndpoint,
	adminProfessorImport: AdminProfessorImportEndpoint,
	adminOfferings: AdminOfferingsEndpoint,
	adminOfferingCreate: AdminOfferingCreateEndpoint,
	adminOfferingDetail: AdminOfferingDetailEndpoint,
	adminOfferingComponents: AdminOfferingComponentsEndpoint,
	adminOfferingComponentCreate: AdminOfferingComponentCreateEndpoint,
	adminOfferingComponentDetail: AdminOfferingComponentDetailEndpoint,
	adminOfferingProfessors: AdminOfferingProfessorsEndpoint,
	adminOfferingRoster: AdminOfferingRosterEndpoint,
	adminOfferingBulkEnroll: AdminOfferingBulkEnrollEndpoint,
	adminOfferingUnenroll: AdminOfferingUnenrollEndpoint,
	// Admin analytics + attendance overview (Phase 7; backend #136/#137/#138)
	adminAnalyticsOverview: AdminAnalyticsOverviewEndpoint,
	adminAnalyticsComparison: AdminAnalyticsComparisonEndpoint,
	adminAnalyticsTrends: AdminAnalyticsTrendsEndpoint,
	adminAnalyticsAtRisk: AdminAnalyticsAtRiskEndpoint,
	adminAnalyticsRefreshRisk: AdminAnalyticsRefreshRiskEndpoint,
	adminRiskStaging: AdminRiskStagingEndpoint,
	adminRiskStagingPromote: AdminRiskStagingPromoteEndpoint,
	adminAttendanceOverview: AdminAttendanceOverviewEndpoint,
	adminRecentScans: AdminRecentScansEndpoint,
	// Admin audit logs (Phase 8 backend; designed shape)
	adminAuditLogs: AdminAuditLogsEndpoint,
	adminStructureChanges: AdminStructureChangesEndpoint,
	// Admin users (super_admin only)
	adminUsers: AdminUsersEndpoint,
	adminUserCreate: AdminUserCreateEndpoint,
	adminUserDeactivate: AdminUserDeactivateEndpoint,
	adminUserReactivate: AdminUserReactivateEndpoint,
	// Admin password reset (three rosters, one backend implementation)
	adminUserResetPassword: AdminUserResetPasswordEndpoint,
	adminStudentResetPassword: AdminStudentResetPasswordEndpoint,
	adminProfessorResetPassword: AdminProfessorResetPasswordEndpoint,
	// Admin courses (templates, D44)
	adminCourses: AdminCoursesEndpoint,
	adminCourseCreate: AdminCourseCreateEndpoint,
	adminCourseDetail: AdminCourseDetailEndpoint,
	adminCourseImport: AdminCourseImportEndpoint,
	// Admin programs (Phase A)
	adminPrograms: AdminProgramsEndpoint,
	adminProgramCreate: AdminProgramCreateEndpoint,
	adminProgramDetail: AdminProgramDetailEndpoint,
	adminProgramImport: AdminProgramImportEndpoint,
	adminYearLevels: AdminYearLevelsEndpoint,
	adminYearLevelDetail: AdminYearLevelDetailEndpoint,
	// Dashboard summaries (three roles, three mount points)
	adminDashboard: AdminDashboardEndpoint,
	professorDashboard: ProfessorDashboardEndpoint,
};
