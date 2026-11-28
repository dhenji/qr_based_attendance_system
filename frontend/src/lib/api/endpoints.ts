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
	LockoutStatusResponse,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsCourseOptionsResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewItemResponse,
	AttendanceRecordItemResponse,
	AttendanceSummaryResponse,
	AuditLogItemResponse,
	CourseImportResult,
	OfferingComponentResponse,
	ProfessorImportResult,
	ProgramImportResult,
	PromoteStagingResponse,
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
	SessionPlanResponse,
	SessionReadResponse,
} from '$lib/shared/types';
// Mock fixtures, mutable state, and handlers live in ./endpoints.mock; the
// definitions below point at their named handler. That module imports these
// types back with `import type`, so the runtime graph stays acyclic.
import {
	mockSessionQR,
	mockAttendanceScan,
	mockAttendancePrecheck,
	mockSessionList,
	mockSessionCreate,
	mockSessionHistory,
	mockSessionActive,
	mockSessionClose,
	mockAttendanceList,
	mockAuthOtpRequest,
	mockAuthOtpVerify,
	mockAuthRegister,
	mockAuthLogin,
	mockAuthLoginOtpVerify,
	mockAuthLoginOtpResend,
	mockAuthRefresh,
	mockAuthMe,
	mockAuthMfaVerify,
	mockAuthMfaSetup,
	mockAuthMfaDisable,
	mockAuthMfaBackupCodesGenerate,
	mockAuthMfaBackupCodesSummary,
	mockAuthChangePassword,
	mockAuthLogout,
	mockAuthSessionPolicy,
	mockForgotPassword,
	mockForgotPasswordVerify,
	mockResetPassword,
	mockAuthPasswordRecoveryStart,
	mockAuthPasswordRecoveryReset,
	mockSecurityQuestion,
	mockRecoveryCode,
	mockStudentProfile,
	mockStudentDashboard,
	mockAdminDashboard,
	mockProfessorDashboard,
	mockStudentHistory,
	mockStudentExcuseSubmit,
	mockStudentExcuseList,
	mockStudentExcuseDetail,
	mockUploadPresigned,
	mockStudentFaceEmbedding,
	mockStudentSchedule,
	mockProfessorProfile,
	mockSessionPlan,
	mockProfessorOfferingStudents,
	mockProfessorCourses,
	mockAdminStudents,
	mockAdminStudentCreate,
	mockAdminStudentDetail,
	mockAdminStudentImport,
	mockAdminFaceEnrollmentUpload,
	mockAdminFaceEnrollmentStatus,
	mockAdminFaceEnrollmentRevoke,
	mockAdminProfessors,
	mockAdminProfessorCreate,
	mockAdminProfessorDetail,
	mockAdminProfessorImport,
	mockAdminOfferings,
	mockAdminCourses,
	mockAdminCourseCreate,
	mockAdminCourseDetail,
	mockAdminCourseImport,
	mockAdminOfferingCreate,
	mockAdminOfferingDetail,
	mockAdminOfferingComponents,
	mockAdminOfferingComponentCreate,
	mockAdminOfferingComponentDetail,
	mockAdminOfferingProfessors,
	mockAdminOfferingRoster,
	mockAdminOfferingBulkEnroll,
	mockAdminPrograms,
	mockAdminProgramCreate,
	mockAdminProgramDetail,
	mockAdminProgramImport,
	mockAdminYearLevels,
	mockAdminYearLevelDetail,
	mockAdminAnalyticsOverview,
	mockAdminAnalyticsCourseOptions,
	mockAdminAnalyticsComparison,
	mockAdminAnalyticsTrends,
	mockAdminAnalyticsAtRisk,
	mockAdminAnalyticsRefreshRisk,
	mockAdminRiskStaging,
	mockAdminRiskStagingPromote,
	mockAdminAttendanceOverview,
	mockAdminAttendanceSummary,
	mockAdminAttendanceRecords,
	mockSystemSettingsGet,
	mockSystemSettingsPatch,
	mockSystemBackups,
	mockSystemBackupTrigger,
	mockSystemSyncFlush,
	mockSystemCleanup,
	mockAdminAuditLogs,
	mockAdminStructureChanges,
	mockAdminUsers,
	mockAdminUserCreate,
	mockAdminUserDeactivate,
	mockAdminUserReactivate,
	mockAdminUserResetPassword,
	mockAdminStudentResetPassword,
	mockAdminProfessorResetPassword,
	mockAdminUserLockoutStatus,
	mockAdminUserLockoutRelease,
	mockAdminUserLockoutResetCounter,
	mockAdminUserLockoutOverride,
	mockAdminUserLockoutOverrideRevoke,
	mockProfessorReportsAllCourses,
	mockProfessorReportsComparison,
	mockProfessorReportsTrends,
	mockAdminExcuses,
	mockLivenessReviewList,
	mockLivenessReviewResolve,
} from './endpoints.mock';

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
	scheduled_start_time: string;
	scheduled_end_time: string;
	// Center is null when the session has no classroom coordinates — the
	// backend skips its geofence check in that case (and so does the scan
	// page pre-check).
	geofence: { radius: number; lat: number | null; lng: number | null; uncertainty_cap_meters?: number; gps_hard_floor_meters?: number; gps_review_accuracy_threshold?: number };
	present_window_minutes: number;
	late_window_minutes: number;
	classroom_name?: string | null;
	is_remote?: boolean;
	geofence_enabled?: boolean;
	attendance_attempt_limit?: number;
	// Caller attempt state (Option A contract): populated only when the
	// caller resolves to a student row and the session caps attempts;
	// attempts_remaining is null for unlimited sessions. Absent on legacy
	// servers — treat absence as "keep last-known".
	attempts_used?: number | null;
	attempts_remaining?: number | null;
	limit_reached?: boolean;
}

export interface AttendanceScanResponse {
	id: number;
	status: ScanStatus;
	scanned_at: string;
	expires_at: string;
	// Post-operation attempt state for this request (authoritative;
	// attempts_used can exceed attendance_attempt_limit when blocked
	// retries keep incrementing the durable counter). Null remaining =
	// unlimited session. Optional: absent on legacy servers.
	attendance_attempt_limit?: number;
	attempts_used?: number;
	attempts_remaining?: number | null;
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

// Scan precheck (D27 step-2 gate) — live on features/attendance/router.py
// (POST /student/attendance/precheck). Read-only: resolves the student from
// the authenticated user, comparing payload.student_number case-insensitively
// (403 student_number_mismatch on spoof). 200 flags enrolled/already_scanned
// (which scan would raise as 403 not_enrolled / 409 duplicate_scan);
// 404 session_not_found, 410 session_expired still raise.
export interface AttendancePrecheckResponse {
	enrolled: boolean;
	already_scanned: boolean;
	retake_available?: boolean;
	attendance_attempt_limit?: number;
	attempts_used?: number;
	attempts_remaining?: number | null;
	limit_reached?: boolean;
	student: {
		student_id: string;
		name: string;
		section: string | null;
	};
}

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

export interface ForgotPasswordVerifyResponse {
	recovery_token: string;
}

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
	session_code?: string | null;
	course_code: string;
	course_name: string;
	status: StudentHistoryStatus;
	original_status?: StudentHistoryStatus | null;
	excuse_reason?: string | null;
	review_note?: string | null;
	reviewed_at?: string | null;
	retake_available?: boolean;
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

// Student face-embedding pull (D29) — live on features/student/router.py
// (GET /student/me/face-embedding?current_version=N). 200 carries the
// base64 blob for a newer version; 204 (client resolves to undefined) means
// the cached version is current; 404 means no enrollment on file.
export interface StudentFaceEmbeddingResponse {
	version: number;
	embedding: string;
}

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
	// D94: the open-window grace — how early and how late a session may be
	// opened around its scheduled class.
	session_early_open_minutes: number;
	session_late_open_minutes: number;
	backup_retention_daily: number;
	backup_retention_monthly: number;
	attendance_attempt_limit_default: number;
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
	// The display identity, resolved server-side (ADR-088). The ids above
	// stay: the per-record paths key on them.
	student_name: string;
	student_number: string;
	student_section: string;
	session_code: string;
	session_date: string;
	course_code: string;
	course_name: string;
	reviewed_by_name: string | null;
}

export interface ExcuseReviewBody {
	status: 'approved' | 'rejected';
	review_notes?: string;
}

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

// Edit a professor-issued excuse —
// PATCH /professor/sessions/{sid}/attendance/{stid}/excuse
// { reason?: 10..2000 chars, review_notes?: ≤2000 } (at least one required).
export interface ExcuseEditBody {
	reason?: string;
	review_notes?: string;
}

// Revoke a professor-issued excuse —
// DELETE /professor/sessions/{sid}/attendance/{stid}/excuse (no body).
// Sets the excuse rejected and restores attendance to original_status.
export interface ExcuseRevokeResponse {
	reverted_to: string | null;
}

// Excuse all absent records in a session (idempotent) —
// POST /professor/sessions/{sid}/excuse-all-absent { reason: 10..2000 }.
export interface ExcuseBulkResponse {
	excused_count: number;
	reason: string;
}

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

export interface ProfessorReportsComparisonItemResponse {
	course_id: number;
	course_code: string;
	program_id: number;
	year_level_id: number;
	program_code: string;
	year_level_label: string;
	compliance_rate: number;
	participation_rate: number;
	total_sessions: number;
}

export interface ProfessorReportsTrendItemResponse {
	date: string;
	course_id: number;
	course_code: string;
	rate: number;
}

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

// Session QR payload (D18)
export const SessionQREndpoint: EndpointDef<SessionVerificationResponse> = {
	url: '/student/sessions/verify-code',
	method: 'POST',
	mock: mockSessionQR,
};

// Attendance scan (D18)
export const AttendanceScanEndpoint: EndpointDef<AttendanceScanResponse> = {
	url: '/student/attendance/scan',
	method: 'POST',
	mock: mockAttendanceScan,
};

export const AttendancePrecheckEndpoint: EndpointDef<AttendancePrecheckResponse> = {
	url: '/student/attendance/precheck',
	method: 'POST',
	mock: mockAttendancePrecheck,
};

// Session CRUD (professor) — real routes on features/session/router.py.
//
// The live QR payload keys the offering as `offering` (backend QRPayload);
// course display names are joined client-side from GET /professor/courses.
export const SessionListEndpoint: EndpointDef<Paginated<SessionListItemResponse>> = {
	url: '/professor/sessions',
	method: 'GET',
	mock: mockSessionList,
};

export const SessionCreateEndpoint: EndpointDef<SessionReadResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: mockSessionCreate,
};

// Session history (professor) — wireframe 3.5, GET /professor/sessions/history.
// Rates ride the rows; averages are derived client-side (the envelope carries
// items/total/page/size only).
export const SessionHistoryEndpoint: EndpointDef<Paginated<SessionHistoryItemResponse>> = {
	url: '/professor/sessions/history',
	method: 'GET',
	mock: mockSessionHistory,
};

// Live session detail (professor projector view).
// The session id rides the path: GET /professor/sessions/active/{id} —
// callers pass it via the client's `suffix` option.
// Poll-friendly: unscanned students read as absent server-side.
export const SessionActiveEndpoint: EndpointDef<SessionActiveResponse> = {
	url: '/professor/sessions/active',
	method: 'GET',
	mock: mockSessionActive,
};

// Close session (professor).
// The session id rides the path: POST /professor/sessions/{id}/close —
// callers pass it via the client's `suffix` option.
export const SessionCloseEndpoint: EndpointDef<SessionCloseResponse> = {
	url: '/professor/sessions',
	method: 'POST',
	mock: mockSessionClose,
};

// Attendance records (professor) — GET /professor/attendance.
// Filtered by course_id/offering_id (not course code); course display names
// join client-side from GET /professor/courses.
export const AttendanceListEndpoint: EndpointDef<Paginated<ProfessorAttendanceItemResponse>> = {
	url: '/professor/attendance',
	method: 'GET',
	mock: mockAttendanceList,
};

export const AuthOtpRequestEndpoint: EndpointDef<void> = {
	url: '/auth/otp/request',
	method: 'POST',
	mock: mockAuthOtpRequest,
};

export const AuthOtpVerifyEndpoint: EndpointDef<void> = {
	url: '/auth/otp/verify',
	method: 'POST',
	mock: mockAuthOtpVerify,
};

export const AuthRegisterEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/register',
	method: 'POST',
	mock: mockAuthRegister,
};

export const AuthLoginEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/login',
	method: 'POST',
	mock: mockAuthLogin,
};

// Login OTP (mandatory second factor). The password step returns an otp_token
// grant instead of tokens; verify exchanges grant + emailed code for tokens
// (or an MFA challenge), resend burns the previous code and mints a fresh one.
export const AuthLoginOtpVerifyEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/login/verify',
	method: 'POST',
	mock: mockAuthLoginOtpVerify,
};

export const AuthLoginOtpResendEndpoint: EndpointDef<void> = {
	url: '/auth/login/resend',
	method: 'POST',
	mock: mockAuthLoginOtpResend,
};

export const AuthRefreshEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/refresh',
	method: 'POST',
	mock: mockAuthRefresh,
};

export const AuthMeEndpoint: EndpointDef<MeResponse> = {
	url: '/auth/me',
	method: 'GET',
	mock: mockAuthMe,
};

export const AuthMfaVerifyEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/mfa/verify',
	method: 'POST',
	mock: mockAuthMfaVerify,
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
	mock: mockAuthMfaSetup,
};

export const AuthMfaDisableEndpoint: EndpointDef<void> = {
	url: '/auth/mfa/disable',
	method: 'POST',
	mock: mockAuthMfaDisable,
};

export const AuthMfaBackupCodesGenerateEndpoint: EndpointDef<BackupCodesResponse> = {
	url: '/auth/mfa/backup-codes',
	method: 'POST',
	mock: mockAuthMfaBackupCodesGenerate,
};

export const AuthMfaBackupCodesSummaryEndpoint: EndpointDef<BackupCodesSummaryResponse> = {
	url: '/auth/mfa/backup-codes',
	method: 'GET',
	mock: mockAuthMfaBackupCodesSummary,
};

export const AuthChangePasswordEndpoint: EndpointDef<void> = {
	url: '/auth/change-password',
	method: 'POST',
	mock: mockAuthChangePassword,
};

export const AuthLogoutEndpoint: EndpointDef<void> = {
	url: '/auth/logout',
	method: 'POST',
	mock: mockAuthLogout,
};

export const AuthSessionPolicyEndpoint: EndpointDef<{ idle_timeout_minutes: number; idle_warning_minutes: number }> = {
	url: '/auth/session-policy',
	method: 'GET',
	mock: mockAuthSessionPolicy,
};

export const ForgotPasswordEndpoint: EndpointDef<ForgotPasswordResponse> = {
	url: '/auth/forgot-password',
	method: 'POST',
	mock: mockForgotPassword,
};

export const ForgotPasswordVerifyEndpoint: EndpointDef<ForgotPasswordVerifyResponse> = {
	url: '/auth/forgot-password/verify',
	method: 'POST',
	mock: mockForgotPasswordVerify,
};

export const ResetPasswordEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/reset-password',
	method: 'POST',
	mock: mockResetPassword,
};

export const AuthPasswordRecoveryStartEndpoint: EndpointDef<{ recovery_token: string; masked_email: string }> = {
	url: '/auth/password-recovery/start',
	method: 'POST',
	mock: mockAuthPasswordRecoveryStart,
};

export const AuthPasswordRecoveryResetEndpoint: EndpointDef<TokenResponse> = {
	url: '/auth/password-recovery/reset',
	method: 'POST',
	mock: mockAuthPasswordRecoveryReset,
};

// Set/update security question (authenticated) —
// POST /auth/security-question {question, answer} -> 204. The question is
// stored server-side (plaintext under a legacy column name); only the answer
// is hashed. Registration sets the first pair; this updates it.
export const SecurityQuestionEndpoint: EndpointDef<void> = {
	url: '/auth/security-question',
	method: 'POST',
	mock: mockSecurityQuestion,
};

// Set or rotate the break-glass recovery code (authenticated) —
// POST /auth/recovery-code {code, current_password} -> 204.
export const RecoveryCodeEndpoint: EndpointDef<void> = {
	url: '/auth/recovery-code',
	method: 'POST',
	mock: mockRecoveryCode,
};

// --- Student ----------------------------------------------------------------

export const StudentProfileEndpoint: EndpointDef<StudentProfileResponse> = {
	url: '/student/profile',
	method: 'GET',
	mock: mockStudentProfile,
};

export const StudentDashboardEndpoint: EndpointDef<StudentDashboardResponse> = {
	url: '/student/dashboard',
	method: 'GET',
	mock: mockStudentDashboard,
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
	mock: mockAdminDashboard,
};

export const ProfessorDashboardEndpoint: EndpointDef<ProfessorDashboardResponse> = {
	url: '/professor/dashboard',
	method: 'GET',
	mock: mockProfessorDashboard,
};

// Student attendance history — live on features/attendance/router.py
// (GET /student/attendance/history). Query: ?program_id&year_level_id&semester&
// course_id&status&date_from&date_to&sort_by=date|course|section|status|time&
// sort_dir&page&size. Summary covers the FULL filter set, not just the page.
export const StudentHistoryEndpoint: EndpointDef<StudentHistoryResponse> = {
	url: '/student/attendance/history',
	method: 'GET',
	mock: mockStudentHistory,
};

export const StudentExcuseSubmitEndpoint: EndpointDef<StudentExcuseSubmitResponse> = {
	url: '/student/excuse-requests',
	method: 'POST',
	mock: mockStudentExcuseSubmit,
};

export const StudentExcuseListEndpoint: EndpointDef<Paginated<StudentExcuseItemResponse>> = {
	url: '/student/excuse-requests',
	method: 'GET',
	mock: mockStudentExcuseList,
};

export const StudentExcuseDetailEndpoint: EndpointDef<StudentExcuseItemResponse> = {
	url: '/student/excuse-requests',
	method: 'GET',
	mock: mockStudentExcuseDetail,
};

export const UploadPresignedEndpoint: EndpointDef<PresignedUrlResponse> = {
	url: '/upload/presigned-url',
	method: 'POST',
	mock: mockUploadPresigned,
};

export const StudentFaceEmbeddingEndpoint: EndpointDef<StudentFaceEmbeddingResponse | undefined> = {
	url: '/student/me/face-embedding',
	method: 'GET',
	mock: mockStudentFaceEmbedding,
};

// Student schedule — live on features/student/router.py
// (GET /student/schedule, no params; identity from the Bearer token).
// One row per active enrollment ordered by offering_id; empty enrollments
// return { offerings: [] }.
export const StudentScheduleEndpoint: EndpointDef<ScheduleResponse> = {
	url: '/student/schedule',
	method: 'GET',
	mock: mockStudentSchedule,
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
	mock: mockProfessorProfile,
};

// GET /professor/offerings/{id}/session-plan — what a session for this
// offering would inherit (D93): the meeting it belongs to, the next
// occurrence of that meeting, the attendance windows, the classroom and the
// geofence radius. The open form renders this instead of re-deriving the
// schedule.
//
// D94 adds the open window: whether the session may be opened at this very
// moment, and why not when it may not.
export const SessionPlanEndpoint: EndpointDef<SessionPlanResponse> = {
	url: '/professor/offerings',
	method: 'GET',
	mock: mockSessionPlan,
};

// GET /professor/offerings/{id}/students — enrolled roster for an offering
// the signed-in professor is assigned to (professor-scoped, paginated).
export const ProfessorOfferingStudentsEndpoint: EndpointDef<Paginated<AdminRosterItemResponse>> = {
	url: '/professor/offerings',
	method: 'GET',
	mock: mockProfessorOfferingStudents,
};

// GET /professor/courses — own active assignments, paginated. Since D93 the
// wire rows also carry the configuration a session inherits: the offering's
// schedule and classroom, its default windows and radius, its scheduled
// meetings, and the next occurrence of the first one.
export const ProfessorCoursesEndpoint: EndpointDef<Paginated<ProfessorAssignedOffering>> = {
	url: '/professor/courses',
	method: 'GET',
	mock: mockProfessorCourses,
};

export const AdminStudentsEndpoint: EndpointDef<Paginated<AdminStudentResponse>> = {
	url: '/admin/students',
	method: 'GET',
	mock: mockAdminStudents,
};

export const AdminStudentCreateEndpoint: EndpointDef<AdminStudentResponse> = {
	url: '/admin/students',
	method: 'POST',
	mock: mockAdminStudentCreate,
};

export const AdminStudentDetailEndpoint: EndpointDef<AdminStudentDetailResponse> = {
	url: '/admin/students',
	method: 'GET',
	mock: mockAdminStudentDetail,
};

export const AdminStudentImportEndpoint: EndpointDef<StudentImportResult> = {
	url: '/admin/students/import',
	method: 'POST',
	mock: mockAdminStudentImport,
};

export const AdminFaceEnrollmentUploadEndpoint: EndpointDef<AdminFaceEnrollmentUploadResponse> = {
	url: '/admin/face-enrollment',
	method: 'POST',
	mock: mockAdminFaceEnrollmentUpload,
};

export const AdminFaceEnrollmentStatusEndpoint: EndpointDef<AdminFaceEnrollmentStatusResponse> = {
	url: '/admin/face-enrollment',
	method: 'GET',
	mock: mockAdminFaceEnrollmentStatus,
};

export const AdminFaceEnrollmentRevokeEndpoint: EndpointDef<void> = {
	url: '/admin/face-enrollment',
	method: 'DELETE',
	mock: mockAdminFaceEnrollmentRevoke,
};

export const AdminProfessorsEndpoint: EndpointDef<Paginated<AdminProfessorResponse>> = {
	url: '/admin/professors',
	method: 'GET',
	mock: mockAdminProfessors,
};

export const AdminProfessorCreateEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'POST',
	mock: mockAdminProfessorCreate,
};

export const AdminProfessorDetailEndpoint: EndpointDef<AdminProfessorResponse> = {
	url: '/admin/professors',
	method: 'GET',
	mock: mockAdminProfessorDetail,
};

export const AdminProfessorImportEndpoint: EndpointDef<ProfessorImportResult> = {
	url: '/admin/professors/import',
	method: 'POST',
	mock: mockAdminProfessorImport,
};

export const AdminOfferingsEndpoint: EndpointDef<Paginated<AdminOfferingResponse>> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferings,
};

export const AdminCoursesEndpoint: EndpointDef<Paginated<AdminCourseResponse>> = {
	url: '/admin/courses',
	method: 'GET',
	mock: mockAdminCourses,
};

export const AdminCourseCreateEndpoint: EndpointDef<AdminCourseResponse> = {
	url: '/admin/courses',
	method: 'POST',
	mock: mockAdminCourseCreate,
};

export const AdminCourseDetailEndpoint: EndpointDef<AdminCourseResponse> = {
	url: '/admin/courses',
	method: 'GET',
	mock: mockAdminCourseDetail,
};

export const AdminCourseImportEndpoint: EndpointDef<CourseImportResult> = {
	url: '/admin/courses/import',
	method: 'POST',
	mock: mockAdminCourseImport,
};

export const AdminOfferingCreateEndpoint: EndpointDef<AdminOfferingResponse> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: mockAdminOfferingCreate,
};

export const AdminOfferingDetailEndpoint: EndpointDef<AdminOfferingResponse> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferingDetail,
};

// Offering components (D77: per-type schedules) ---------------------------------
//
// Live routes on course/offering_router.py. Same suffix convention:
// `/{oid}/components`, `/{oid}/components/{cid}`.

export const AdminOfferingComponentsEndpoint: EndpointDef<OfferingComponentResponse[]> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferingComponents,
};

export const AdminOfferingComponentCreateEndpoint: EndpointDef<OfferingComponentResponse> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: mockAdminOfferingComponentCreate,
};

export const AdminOfferingComponentDetailEndpoint: EndpointDef<OfferingComponentResponse> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferingComponentDetail,
};

export const AdminOfferingProfessorsEndpoint: EndpointDef<
	AdminAssignmentResponse[] | AdminAssignmentResponse | { effective_to: string }
> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferingProfessors,
};

// Roster mock: derived from the student mock rows so the section filter has
// real values to narrow. `enrolled_at` reuses the student created_at.
export const AdminOfferingRosterEndpoint: EndpointDef<Paginated<AdminRosterItemResponse>> = {
	url: '/admin/offerings',
	method: 'GET',
	mock: mockAdminOfferingRoster,
};

export const AdminOfferingBulkEnrollEndpoint: EndpointDef<AdminBulkEnrollResult> = {
	url: '/admin/offerings',
	method: 'POST',
	mock: mockAdminOfferingBulkEnroll,
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

export const AdminProgramsEndpoint: EndpointDef<Paginated<ProgramResponse>> = {
	url: '/admin/programs',
	method: 'GET',
	mock: mockAdminPrograms,
};

export const AdminProgramCreateEndpoint: EndpointDef<ProgramResponse> = {
	url: '/admin/programs',
	method: 'POST',
	mock: mockAdminProgramCreate,
};

export const AdminProgramDetailEndpoint: EndpointDef<ProgramDetailResponse> = {
	url: '/admin/programs',
	method: 'GET',
	mock: mockAdminProgramDetail,
};

export const AdminProgramImportEndpoint: EndpointDef<ProgramImportResult> = {
	url: '/admin/programs/import',
	method: 'POST',
	mock: mockAdminProgramImport,
};

export const AdminYearLevelsEndpoint: EndpointDef<Paginated<YearLevelResponse>> = {
	url: '/admin/programs',
	method: 'GET',
	mock: mockAdminYearLevels,
};

export const AdminYearLevelDetailEndpoint: EndpointDef<YearLevelResponse> = {
	url: '/admin/programs',
	method: 'GET',
	mock: mockAdminYearLevelDetail,
};

export const AdminAnalyticsOverviewEndpoint: EndpointDef<AnalyticsOverviewResponse> = {
	url: '/admin/analytics/overview',
	method: 'GET',
	mock: mockAdminAnalyticsOverview,
};

// Courses with at least one offering in the picked scope (#279): the rail's
// course picker reads this so a course no report can show is not selectable.
// Mirrors the backend's distinct-courses-with-an-offering scope and the `q`
// code/name search.
export const AdminAnalyticsCourseOptionsEndpoint: EndpointDef<AnalyticsCourseOptionsResponse> = {
	url: '/admin/analytics/course-options',
	method: 'GET',
	mock: mockAdminAnalyticsCourseOptions,
};

export const AdminAnalyticsComparisonEndpoint: EndpointDef<{ items: AnalyticsComparisonItemResponse[] }> = {
	url: '/admin/analytics/course-comparison',
	method: 'GET',
	mock: mockAdminAnalyticsComparison,
};

export const AdminAnalyticsTrendsEndpoint: EndpointDef<{ items: AnalyticsTrendItemResponse[] }> = {
	url: '/admin/analytics/trends',
	method: 'GET',
	mock: mockAdminAnalyticsTrends,
};

export const AdminAnalyticsAtRiskEndpoint: EndpointDef<{ items: AnalyticsAtRiskItemResponse[] }> = {
	url: '/admin/analytics/at-risk',
	method: 'GET',
	mock: mockAdminAnalyticsAtRisk,
};

export const AdminAnalyticsRefreshRiskEndpoint: EndpointDef<RiskRefreshResponse> = {
	url: '/admin/analytics/refresh-risk',
	method: 'POST',
	mock: mockAdminAnalyticsRefreshRisk,
};

// Dry-run staging review (backend #137): GET lists staged rows without
// touching live scores; POST copies unpromoted rows into the live scores.
// Mocks are empty by design — fabricated staged scores would imply a batch
// that never ran, so mock mode renders the "no dry-run yet" hint instead.
export const AdminRiskStagingEndpoint: EndpointDef<RiskStagingResponse> = {
	url: '/admin/analytics/risk-staging',
	method: 'GET',
	mock: mockAdminRiskStaging,
};

export const AdminRiskStagingPromoteEndpoint: EndpointDef<PromoteStagingResponse> = {
	url: '/admin/analytics/risk-staging/promote',
	method: 'POST',
	mock: mockAdminRiskStagingPromote,
};

export const AdminAttendanceOverviewEndpoint: EndpointDef<{ items: AttendanceOverviewItemResponse[] }> = {
	url: '/admin/attendance/overview',
	method: 'GET',
	mock: mockAdminAttendanceOverview,
};

export const AdminAttendanceSummaryEndpoint: EndpointDef<AttendanceSummaryResponse> = {
	url: '/admin/attendance/summary',
	method: 'GET',
	mock: mockAdminAttendanceSummary,
};

export const AdminAttendanceRecordsEndpoint: EndpointDef<{ items: AttendanceRecordItemResponse[]; total: number; page: number; size: number }> = {
	url: '/admin/attendance/records',
	method: 'GET',
	mock: mockAdminAttendanceRecords,
};

export const SystemSettingsGetEndpoint: EndpointDef<SystemSettingsResponse> = {
	url: '/admin/system/settings',
	method: 'GET',
	mock: mockSystemSettingsGet
};

export const SystemSettingsPatchEndpoint: EndpointDef<SystemSettingsResponse> = {
	url: '/admin/system/settings',
	method: 'PATCH',
	mock: mockSystemSettingsPatch
};

export const SystemBackupsEndpoint: EndpointDef<{ items: BackupLogItemResponse[] }> = {
	url: '/admin/backups',
	method: 'GET',
	mock: mockSystemBackups
};

export const SystemBackupTriggerEndpoint: EndpointDef<{ backup_id: number; status: 'started' }> = {
	url: '/admin/backups',
	method: 'POST',
	mock: mockSystemBackupTrigger
};

export const SystemSyncFlushEndpoint: EndpointDef<{ processed: number; succeeded: number; failed: number }> = {
	url: '/admin/system/sync/flush',
	method: 'POST',
	mock: mockSystemSyncFlush
};

export const SystemCleanupEndpoint: EndpointDef<{ removed: number }> = {
	url: '/admin/system/cleanup',
	method: 'POST',
	mock: mockSystemCleanup
};

export const AdminAuditLogsEndpoint: EndpointDef<Paginated<AuditLogItemResponse>> = {
	url: '/admin/audit-logs',
	method: 'GET',
	mock: mockAdminAuditLogs,
};

export const AdminStructureChangesEndpoint: EndpointDef<Paginated<StructureChangeResponse>> = {
	url: '/admin/system/academic-structure',
	method: 'GET',
	mock: mockAdminStructureChanges,
};

export const AdminUsersEndpoint: EndpointDef<Paginated<AdminUserResponse>> = {
	url: '/admin/users',
	method: 'GET',
	mock: mockAdminUsers,
};

export const AdminUserCreateEndpoint: EndpointDef<AdminUserCreateResponse> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserCreate,
};

export const AdminUserDeactivateEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'PATCH',
	mock: mockAdminUserDeactivate,
};

export const AdminUserReactivateEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'PATCH',
	mock: mockAdminUserReactivate,
};

export const AdminUserResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserResetPassword,
};

export const AdminStudentResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/students',
	method: 'POST',
	mock: mockAdminStudentResetPassword,
};

export const AdminProfessorResetPasswordEndpoint: EndpointDef<AdminPasswordResetResponse> = {
	url: '/admin/professors',
	method: 'POST',
	mock: mockAdminProfessorResetPassword,
};

// --- Admin account lockout (status + release + counter + override) -------------
//
// Five routes on backend features/admin/router.py under /admin/users/{id}/lockout.
// Real API by default; mocks return an unlocked status and successful no-op
// mutations (static fixtures, no backend state simulated).
export const AdminUserLockoutStatusEndpoint: EndpointDef<LockoutStatusResponse> = {
	url: '/admin/users',
	method: 'GET',
	mock: mockAdminUserLockoutStatus,
};

export const AdminUserLockoutReleaseEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserLockoutRelease,
};

export const AdminUserLockoutResetCounterEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserLockoutResetCounter,
};

export const AdminUserLockoutOverrideEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserLockoutOverride,
};

export const AdminUserLockoutOverrideRevokeEndpoint: EndpointDef<void> = {
	url: '/admin/users',
	method: 'POST',
	mock: mockAdminUserLockoutOverrideRevoke,
};

export const ExcuseListEndpoint: EndpointDef<Paginated<ExcuseRequestReadResponse>> = {
	url: '/professor/excuse-requests',
	method: 'GET',
};

export const ExcuseReviewEndpoint: EndpointDef<ExcuseRequestReadResponse> = {
	url: '/professor/excuse-requests',
	method: 'POST',
};

export const ExcuseQuickEndpoint: EndpointDef<ExcuseActionResponse> = {
	url: '/professor/sessions',
	method: 'POST',
};

export const ExcuseEditEndpoint: EndpointDef<ExcuseRequestReadResponse> = {
	url: '/professor/sessions',
	method: 'PATCH',
};

export const ExcuseRevokeEndpoint: EndpointDef<ExcuseRevokeResponse> = {
	url: '/professor/sessions',
	method: 'DELETE',
};

export const ExcuseBulkEndpoint: EndpointDef<ExcuseBulkResponse> = {
	url: '/professor/sessions',
	method: 'POST',
};

export const ProfessorReportsAllCoursesEndpoint: EndpointDef<ProfessorReportsAllCoursesResponse> = {
	url: '/professor/reports/all-courses',
	method: 'GET',
	mock: mockProfessorReportsAllCourses,
};

export const ProfessorReportsComparisonEndpoint: EndpointDef<{
	items: ProfessorReportsComparisonItemResponse[];
	total?: number;
}> = {
	url: '/professor/reports/comparison',
	method: 'GET',
	mock: mockProfessorReportsComparison,
};

export const ProfessorReportsTrendsEndpoint: EndpointDef<{
	items: ProfessorReportsTrendItemResponse[];
}> = {
	url: '/professor/reports/trends',
	method: 'GET',
	mock: mockProfessorReportsTrends,
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
	mock: mockAdminExcuses,
};

export const LivenessReviewListEndpoint: EndpointDef<Paginated<LivenessReviewItemResponse>> = {
	url: '/admin/attendance/liveness-review',
	method: 'GET',
	mock: mockLivenessReviewList,
};

export const LivenessReviewResolveEndpoint: EndpointDef<LivenessReviewResolveResponse> = {
	url: '/admin/attendance/liveness-review',
	method: 'PATCH',
	mock: mockLivenessReviewResolve,
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
	sessionPlan: SessionPlanEndpoint,
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
	authLogout: AuthLogoutEndpoint,
	authSessionPolicy: AuthSessionPolicyEndpoint,
	authForgotPassword: ForgotPasswordEndpoint,
	authForgotPasswordVerify: ForgotPasswordVerifyEndpoint,
	authResetPassword: ResetPasswordEndpoint,
	authPasswordRecoveryStart: AuthPasswordRecoveryStartEndpoint,
	authPasswordRecoveryReset: AuthPasswordRecoveryResetEndpoint,
	authSecurityQuestion: SecurityQuestionEndpoint,
	authRecoveryCode: RecoveryCodeEndpoint,
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
	professorOfferingStudents: ProfessorOfferingStudentsEndpoint,
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
	adminFaceEnrollmentRevoke: AdminFaceEnrollmentRevokeEndpoint,
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
	adminAnalyticsCourseOptions: AdminAnalyticsCourseOptionsEndpoint,
	adminAnalyticsComparison: AdminAnalyticsComparisonEndpoint,
	adminAnalyticsTrends: AdminAnalyticsTrendsEndpoint,
	adminAnalyticsAtRisk: AdminAnalyticsAtRiskEndpoint,
	adminAnalyticsRefreshRisk: AdminAnalyticsRefreshRiskEndpoint,
	adminRiskStaging: AdminRiskStagingEndpoint,
	adminRiskStagingPromote: AdminRiskStagingPromoteEndpoint,
	adminAttendanceOverview: AdminAttendanceOverviewEndpoint,
	adminAttendanceSummary: AdminAttendanceSummaryEndpoint,
	adminAttendanceRecords: AdminAttendanceRecordsEndpoint,
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
	// Admin account lockout
	adminUserLockoutStatus: AdminUserLockoutStatusEndpoint,
	adminUserLockoutRelease: AdminUserLockoutReleaseEndpoint,
	adminUserLockoutResetCounter: AdminUserLockoutResetCounterEndpoint,
	adminUserLockoutOverride: AdminUserLockoutOverrideEndpoint,
	adminUserLockoutOverrideRevoke: AdminUserLockoutOverrideRevokeEndpoint,
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
