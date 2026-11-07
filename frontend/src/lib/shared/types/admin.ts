// admin.ts
// Admin-portal domain types (Phase 3 MVP: students + professors).
//
// Wire shapes mirror backend/src/features/student/schema.py and
// backend/src/features/professor/schema.py exactly (snake_case); the
// camelCase view-models are what pages render. Services map wire → view.

export interface AdminStudentResponse {
	id: number;
	student_id: string;
	first_name: string;
	middle_name: string | null;
	last_name: string;
	email: string;
	program_code: string;
	year_level_label: string;
	section: string | null;
	is_active: boolean;
	claim_status: 'Claimed' | 'Unclaimed';
	face_enrolled: boolean;
	created_at: string;
	scan_count: number;
}

export interface AdminStudentDetailResponse extends AdminStudentResponse {
	face_enrolled_at: string | null;
	face_embedding_version: number;
}

export interface AdminStudent {
	id: number;
	studentId: string;
	firstName: string;
	middleName?: string;
	lastName: string;
	email: string;
	programCode: string;
	yearLevelLabel: string;
	section?: string;
	isActive: boolean;
	claimStatus: 'Claimed' | 'Unclaimed';
	faceEnrolled: boolean;
	createdAt: string;
	scanCount: number;
	faceEnrolledAt?: string;
	faceEmbeddingVersion?: number;
}

export interface AdminStudentCreatePayload {
	student_id: string;
	first_name: string;
	middle_name?: string;
	last_name: string;
	email: string;
	program_id: number;
	year_level_id: number;
	section?: string;
}

export interface AdminStudentUpdatePayload {
	first_name?: string;
	middle_name?: string | null;
	last_name?: string;
	email?: string;
	program_id?: number;
	year_level_id?: number;
	section?: string;
	is_active?: boolean;
}

export interface AdminStudentFilters {
	search?: string;
	program_id?: number;
	year_level_id?: number;
	section?: string;
	is_active?: boolean;
	sort_by?: 'last_name' | 'student_id' | 'created_at';
	sort_dir?: 'asc' | 'desc';
	page?: number;
	size?: number;
}

export interface AdminProfessorResponse {
	id: number;
	first_name: string;
	middle_name: string | null;
	last_name: string;
	email: string;
	department: string | null;
	is_active: boolean;
	claim_status: 'Claimed' | 'Unclaimed';
	assigned_courses: { offering_id: number; course_code: string }[];
	created_at: string;
}

export interface AdminProfessor extends AdminProfessorResponse {
	firstName: string;
	middleName?: string;
	lastName: string;
	claimStatus: 'Claimed' | 'Unclaimed';
	isActive: boolean;
	createdAt: string;
}

export interface AdminProfessorCreatePayload {
	first_name: string;
	middle_name?: string;
	last_name: string;
	email: string;
	department?: string;
	courses?: number[];
}

export interface AdminProfessorUpdatePayload {
	first_name?: string;
	middle_name?: string | null;
	last_name?: string;
	email?: string;
	department?: string | null;
	is_active?: boolean;
	courses?: number[];
}

export interface AdminProfessorFilters {
	search?: string;
	department?: string;
	is_active?: boolean;
	sort_by?: 'last_name' | 'email' | 'created_at';
	sort_dir?: 'asc' | 'desc';
	page?: number;
	size?: number;
}

export interface AdminOfferingResponse {
	id: number;
	course_id: number;
	program_id: number;
	year_level_id: number;
	semester: string;
	academic_year: string;
	sessions_per_week: number;
	semester_weeks: number;
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
	// Optional: the backend has no course_type column (frontend-only label).
	// Absent on live GETs — services fall back to 'lecture' so badges never
	// render undefined. Do not treat as persisted until a backend migration
	// lands.
	course_type?: CourseType;
	// Persisted per-type schedules (D77). Present on live GETs; the read also
	// carries the distinct `session_types` driving Lecture/Lab/Mixed badges.
	session_types: CourseType[];
	components: OfferingComponentResponse[];
	classroom_name: string | null;
	classroom_lat: number | null;
	classroom_lng: number | null;
	// D93: null means "follow the system default" (Admin -> System Settings).
	default_present_window_minutes: number | null;
	default_late_window_minutes: number | null;
	// D93: null means "inherit the app setting" (Admin -> System Settings ->
	// Geofence radius).
	default_classroom_radius_meters: number | null;
	enrolled_count: number;
	is_active: boolean;
	created_at: string;
	updated_at: string;
}

// --- Admin courses (templates, D44) -----------------------------------------
//
// Wire shapes mirror backend/src/features/course/schema.py exactly
// (snake_case); the camelCase view-models are what pages render. A course is
// a standalone reusable template — no program/year/schedule/classroom
// fields. Those live on the offering below. The list endpoint takes only
// ?is_active&page&size (no search/sort params), so search + Code/Name header
// sorts run client-side over the loaded page, like programs.

export type CourseType = 'lecture' | 'lab';

// --- Offering components (D77: per-type schedules) ---------------------------
//
// A component is one scheduled slice of an offering: its session type plus
// the days/times/room that type meets on. A single-component offering behaves
// like the pre-D77 offering; a mixed course carries e.g. a lab component on
// Monday plus a lecture component on Wednesday.

export interface OfferingComponentResponse {
	id: number;
	offering_id: number;
	session_type: CourseType;
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
	classroom_name: string | null;
	classroom_lat: number | null;
	classroom_lng: number | null;
	is_active: boolean;
	created_at: string;
	updated_at: string;
}

export interface OfferingComponent {
	id: number;
	offeringId: number;
	sessionType: CourseType;
	scheduleDays: string;
	scheduleStartTime: string;
	scheduleEndTime: string;
	classroomName?: string;
	classroomLat?: number;
	classroomLng?: number;
	isActive: boolean;
	createdAt: string;
	updatedAt: string;
}

export interface OfferingComponentCreatePayload {
	session_type: CourseType;
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
	classroom_name?: string;
	classroom_lat?: number;
	classroom_lng?: number;
}

export interface OfferingComponentUpdatePayload {
	schedule_days?: string;
	schedule_start_time?: string;
	schedule_end_time?: string;
	classroom_name?: string | null;
	classroom_lat?: number | null;
	classroom_lng?: number | null;
	is_active?: boolean;
}

/** Display label for an offering's type mix: Lecture / Laboratory / Mixed. */
export const sessionMixLabel = (types: CourseType[]): string => {
	if (types.includes('lecture') && types.includes('lab')) return 'Mixed';
	if (types.includes('lab')) return 'Laboratory';
	return 'Lecture';
};

export interface AdminCourseResponse {
	id: number;
	course_code: string;
	course_name: string;
	units: number;
	session_duration_hours: number;
	// Optional for the same reason as AdminOfferingResponse.course_type:
	// live GETs carry no value, so toCourse() falls back to 'lecture'.
	course_type?: CourseType;
	is_active: boolean;
	created_at: string;
	updated_at: string;
}

export interface AdminCourse {
	id: number;
	courseCode: string;
	courseName: string;
	units: number;
	sessionDurationHours: number;
	courseType: CourseType;
	isActive: boolean;
	createdAt: string;
	updatedAt: string;
}

export interface AdminCourseCreatePayload {
	course_code: string;
	course_name: string;
	units: number;
	session_duration_hours: number;
	// Sent when set; the backend ignores unknown keys (Pydantic v2 default),
	// so this is a local-only label until a migration lands.
	course_type?: CourseType;
}

export interface AdminCourseUpdatePayload {
	course_code?: string;
	course_name?: string;
	units?: number;
	session_duration_hours?: number;
	course_type?: CourseType;
	is_active?: boolean;
}

export interface AdminCourseFilters {
	search?: string;
	is_active?: boolean;
	page?: number;
	size?: number;
}

// --- Admin offerings (D44 instances) ------------------------------------------

export interface AdminOffering {
	id: number;
	courseId: number;
	programId: number;
	yearLevelId: number;
	semester: string;
	academicYear: string;
	sessionsPerWeek: number;
	semesterWeeks: number;
	scheduleDays: string;
	scheduleStartTime: string;
	scheduleEndTime: string;
	courseType: CourseType;
	// Distinct types across the active components (D77). Drives the
	// Lecture / Laboratory / Mixed badge via `sessionMixLabel`.
	sessionTypes: CourseType[];
	components: OfferingComponent[];
	classroomName?: string;
	classroomLat?: number;
	classroomLng?: number;
	// D93: null means "follow the system default" (Admin -> System Settings).
	presentWindowMinutes: number | null;
	lateWindowMinutes: number | null;
	// D93: the geofence radius the offering's sessions default to. Null
	// means "inherit" — the app setting in Admin -> System Settings wins.
	defaultClassroomRadiusMeters: number | null;
	isActive: boolean;
	enrolledCount: number;
	createdAt: string;
	updatedAt: string;
	// Joined client-side (the OfferingRead contract carries ids only).
	courseCode?: string;
	courseName?: string;
	programCode?: string;
	yearLevelLabel?: string;
}

export interface AdminOfferingCreatePayload {
	course_id: number;
	program_id: number;
	year_level_id: number;
	semester: string;
	academic_year: string;
	sessions_per_week: number;
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
	// Local-only label (see AdminOfferingResponse.course_type).
	course_type?: CourseType;
	// Optional per-type schedules (D77). Omitted means a single lecture
	// component mirroring the offering schedule/classroom.
	components?: OfferingComponentCreatePayload[];
	classroom_name?: string;
	classroom_lat?: number;
	classroom_lng?: number;
	// D93: null clears the override and puts the offering back on the
	// system default.
	default_present_window_minutes?: number | null;
	default_late_window_minutes?: number | null;
	// D93: the geofence radius override. Null clears it back to the app
	// setting.
	default_classroom_radius_meters?: number | null;
}

// Mutable subset only: course_id/program_id/year_level_id/semester/
// academic_year are identity and rejected server-side when patched.
export interface AdminOfferingUpdatePayload {
	sessions_per_week?: number;
	schedule_days?: string;
	schedule_start_time?: string;
	schedule_end_time?: string;
	course_type?: CourseType;
	classroom_name?: string | null;
	classroom_lat?: number | null;
	classroom_lng?: number | null;
	// D93: null clears the override and puts the offering back on the
	// system default.
	default_present_window_minutes?: number | null;
	default_late_window_minutes?: number | null;
	default_classroom_radius_meters?: number | null;
	is_active?: boolean;
}

export interface AdminOfferingFilters {
	program_id?: number;
	year_level_id?: number;
	semester?: string;
	course_id?: number;
	is_active?: boolean;
	page?: number;
	size?: number;
}

export interface AdminAssignmentResponse {
	offering_id: number;
	professor_id: number;
	is_primary: boolean;
	effective_from: string;
	effective_to: string | null;
	semester: string;
	/** True when a session was opened under this exact effective window. */
	has_sessions: boolean;
	assigned_by: number;
	assigned_at: string;
}

export interface AdminAssignment {
	offeringId: number;
	professorId: number;
	isPrimary: boolean;
	effectiveFrom: string;
	effectiveTo?: string;
	semester: string;
	/** Protected by session history; permanent removal is not available. */
	hasSessions: boolean;
	assignedBy: number;
	assignedAt: string;
	// Joined client-side for display.
	professorName?: string;
	professorEmail?: string;
}

export interface AdminAssignmentCreatePayload {
	professor_id: number;
	is_primary: boolean;
	effective_from: string;
	effective_to?: string;
}

export interface AdminAssignmentReassignPayload {
	new_professor_id: number;
	is_primary?: boolean;
	/** Composite-PK discriminator for the assignment being replaced. */
	old_effective_from?: string;
	effective_from?: string;
	effective_to?: string;
}

export interface AdminAssignmentReopenPayload {
	effective_from: string;
	/** Omit to restore the previous role; false reopens as an assistant. */
	is_primary?: boolean;
}

export interface AdminRosterItemResponse {
	// The student's database primary key (backend RosterItem.id). The printed
	// student number lives in `student_id` (a string); this is the integer id
	// that per-record routes such as the professor quick-excuse need.
	id: number;
	student_id: string;
	name: string;
	email?: string | null;
	section: string | null;
	enrolled_at: string;
}

export interface AdminRosterItem {
	// Database primary key of the student (backend RosterItem.id). Optional for
	// backward compat with any caller that builds the item without it.
	id?: number;
	studentId: string;
	name: string;
	email?: string;
	section?: string;
	enrolledAt: string;
}

export interface AdminRosterFilters {
	section?: string;
	search?: string;
	page?: number;
	size?: number;
}

export interface AdminBulkEnrollResult {
	enrolled: number;
	skipped: number;
	errors: CsvImportError[];
}

// --- Admin analytics & attendance overview (Phase 7, D33-D37) -----------------
//
// Wire shapes mirror docs/architecture/api-contracts.md exactly (snake_case).
// The analytics + attendance-overview routers landed in backend #136/#138,
// so the service layer hits the real API by default; mocks only when
// PUBLIC_MOCK_MODE=true. Rate semantics (D36): compliance = present /
// total (default display), participation = (present + late + excused) / total.
// At-risk thresholds (D35): absence_rate > 0.30 → high, > 0.15 → medium,
// streak ≥ 3 → high, trend slope < −0.05/week → medium.

export type AnalyticsGranularity = 'daily' | 'weekly' | 'monthly';
export type AnalyticsRiskLevel = 'low' | 'medium' | 'high';
export type AttendanceTrend = 'up' | 'down' | 'flat';

export interface AnalyticsOverviewResponse {
	total_students: number;
	total_courses: number;
	avg_compliance_rate: number;
	avg_participation_rate: number;
	total_sessions: number;
	lecture_sessions?: number;
	lab_sessions?: number;
}

export interface AnalyticsComparisonItemResponse {
	course_id: number;
	course_code: string;
	program_id: number;
	year_level_id: number;
	compliance_rate: number;
	participation_rate: number;
	total_sessions: number;
}

export interface AnalyticsCourseOptionResponse {
	course_id: number;
	course_code: string;
	course_name: string;
}

export interface AnalyticsCourseOptionsResponse {
	items: AnalyticsCourseOptionResponse[];
	total: number;
}

export interface AnalyticsTrendItemResponse {
	date: string;
	compliance_rate: number;
	participation_rate: number;
	total_sessions: number;
}

export interface AnalyticsAtRiskItemResponse {
	student_id: string;
	student_name: string;
	program: string;
	year_level: string;
	offering_id: number;
	course_code: string;
	course_name: string;
	absence_rate: number;
	max_streak: number;
	trend_slope: number;
	risk_level: AnalyticsRiskLevel;
	computed_at: string;
}

export interface RiskRefreshResponse {
	processed: number;
	high: number;
	medium: number;
	low: number;
	duration_ms: number;
}

// Dry-run staging review (backend #137): staged rows mirror AtRiskItem plus
// the offering join and the promote stamp. promoted_at null = not yet copied
// into the live scores.
export interface RiskStagingItemResponse {
	student_id: number;
	student_name: string;
	program: string;
	year_level: string;
	offering_id: number;
	course_code: string;
	course_name: string;
	absence_rate: number;
	max_streak: number;
	trend_slope: number;
	risk_level: AnalyticsRiskLevel;
	computed_at: string;
	promoted_at: string | null;
}

export interface RiskStagingResponse {
	items: RiskStagingItemResponse[];
	total: number;
	page: number;
	size: number;
}

export interface PromoteStagingResponse {
	promoted: number;
	skipped: number;
	duration_ms: number;
}

export interface RiskStagingFilters {
	program_id?: number;
	year_level_id?: number;
	semester?: string;
	course_ids?: number[];
	risk_level?: AnalyticsRiskLevel;
	unpromoted_only?: boolean;
	page?: number;
	size?: number;
	// Promote-scope keys: the POST honors these plus the rail's
	// program/year/course scope (#279). Risk level, unpromoted_only, and
	// paging remain list-only.
	student_id?: number;
	offering_id?: number;
}

export interface AttendanceOverviewItemResponse {
	course_id: number;
	course_code: string;
	course_name: string;
	sessions_count: number;
	avg_rate: number;
	trend: AttendanceTrend;
}

export interface RecentScanResponse {
	id: number;
	scanned_at: string;
	student_name: string;
	course_code: string;
	status: string;
}

// GET /admin/dashboard — the admin landing page in one call.
//
// `student_count` / `professor_count` / `program_count` count active roster
// rows. That is deliberately NOT the analytics overview's `total_students`,
// which counts students enrolled in a session in scope: the dashboard must
// agree with the roster list above it, and the two figures answer different
// questions.
export interface AdminDashboardResponse {
	student_count: number;
	professor_count: number;
	program_count: number;
	avg_rate: number;
	scans_today: number;
	pending_sync: number;
	recent_scans: RecentScanResponse[];
}

export interface AdminAnalyticsFilters {
	program_id?: number;
	year_level_id?: number;
	semester?: string;
	course_ids?: number[];
	date_from?: string;
	date_to?: string;
	granularity?: AnalyticsGranularity;
	risk_level?: AnalyticsRiskLevel;
	session_type?: 'lecture' | 'lab';
}

export interface AttendanceOverviewFilters {
	course_id?: number;
	professor_id?: number;
	date_from?: string;
	date_to?: string;
}

// --- Admin audit logs (live backend, api-contracts §System Settings & Backups) --
//
// GET /admin/audit-logs?entity_type&action&performed_by&date_from&date_to&page&size
// returns { items: [{ id, action, entity_type, entity_id, old_value, new_value,
// performed_by, performed_at }] }. Filters AND-combine; a blank value means
// "no filter". date_from is inclusive from 00:00 UTC, date_to inclusive to end
// of day. Values outside the entity/action vocabularies are 422
// invalid_audit_filter (never an empty page); an inverted range is 422
// invalid_audit_date_range.
//
// The academic-structure shape mirrors api-contracts
// GET /admin/system/academic-structure exactly (D38: program/year/course
// mutations with old/new values).
//
// The endpoint returns the stored row unaltered (ADR-064): `performed_by` is
// a `users.id` and `old_value`/`new_value` are the raw JSON snapshots. The
// names an administrator needs are derived on the read side — see
// `features/admin/audit/present.ts`, which reads the label out of the
// snapshot first and only falls back to a roster lookup.

export type AuditEntityType =
	| 'program'
	| 'year_level'
	| 'course'
	| 'course_offering'
	| 'offering_component'
	| 'student'
	| 'professor'
	| 'enrollment'
	| 'course_professor'
	| 'excuse'
	| 'session'
	| 'face_enrollment'
	| 'attendance_record'
	| 'backup'
	| 'app_setting'
	| 'user'
	| 'maintenance';

export type AuditAction =
	| 'create'
	| 'update'
	| 'archive'
	| 'delete'
	| 'import'
	| 'enroll'
	| 'unenroll'
	| 'assign'
	| 'reassign'
	| 'reopen'
	| 'unassign'
	| 'open'
	| 'close'
	| 'approve'
	| 'reject'
	| 'revoke'
	| 'lock'
	| 'unlock'
	| 'login_failed'
	| 'password_reset';

export type AuditActorRole = 'admin' | 'professor' | 'student' | 'system';

/**
 * Who performed an audited action.
 *
 * `kind` is `anonymous` when nobody was authenticated — a lockout from an
 * anonymous attempt, or an unattended run. Otherwise it is `user`.
 */
export interface AuditActorResponse {
	kind: 'user' | 'anonymous';
	id: number | null;
	name: string;
	email: string | null;
	role: string | null;
}

/**
 * What an audited action was about.
 *
 * `label` is the record's name. It is read out of the audit snapshot first
 * and only then from a join, so it survives the record's deletion — which
 * a join would not.
 */
export interface AuditSubjectResponse {
	type: AuditEntityType;
	id: number | null;
	label: string;
	sublabel: string | null;
}

/** One field that changed. */
export interface AuditChangeResponse {
	field: string;
	label: string;
	before: string;
	after: string;
}

export interface AuditLogItemResponse {
	id: number;
	action: AuditAction;
	entity_type: AuditEntityType;
	entity_id: number | null;
	/**
	 * The JSON snapshot the writer took, verbatim.
	 *
	 * A dict, not a string: the backend stores `JSONB`
	 * (`backend/src/features/system/model.py:68`), so the API returns an
	 * object. `old_value` is null on create, `new_value` is null on delete.
	 */
	old_value: Record<string, unknown> | null;
	new_value: Record<string, unknown> | null;
	/**
	 * `users.id` of the actor, or null when nobody was authenticated. The
	 * derived `actor` block names them; this stays the raw reference.
	 */
	performed_by: number | null;
	performed_at: string;
	/** The derived read model (ADR-086). */
	actor: AuditActorResponse;
	subject: AuditSubjectResponse;
	summary: string;
	action_label: string;
	changes: AuditChangeResponse[];
}

export interface AuditLogFilters {
	entity_type?: AuditEntityType;
	action?: AuditAction;
	/** `users.id`. The backend types it `int | None`, so it is a number here. */
	performed_by?: number;
	/** An account id, email or name fragment. Matched server-side. */
	actor?: string;
	date_from?: string;
	date_to?: string;
	sort_by?: 'time' | 'actor' | 'action';
	sort_dir?: 'asc' | 'desc';
	page?: number;
	size?: number;
}

/**
 * The academic-structure row.
 *
 * A subtype of the audit row rather than a copy, mirroring the backend
 * (`AcademicStructureRead` subclasses `AuditLogRead`,
 * `backend/src/features/system/schema.py:104-109`) so the two cannot drift.
 */
export interface StructureChangeResponse extends AuditLogItemResponse {}

export interface CsvImportError {
	line: number;
	reason: string;
}

export interface StudentImportResult {
	imported: number;
	duplicates: number;
	errors: CsvImportError[];
}

export interface ProfessorImportResult {
	imported: number;
	duplicates: number;
	errors: CsvImportError[];
}

export interface ProgramImportResult {
	imported: number;
	duplicates: number;
	errors: CsvImportError[];
}

export interface CourseImportResult {
	imported: number;
	duplicates: number;
	errors: CsvImportError[];
}

// --- Admin users (super_admin only, D60) --------------------------------------
//
// Wire shapes mirror backend/src/features/admin/schema.py exactly
// (snake_case): AdminUserRead + AdminUserCreateResponse (temp_password
// returned once on create). Only super_admin can list/create/deactivate;
// creatable roles are admin/professor/student (super_admin is seeded, 422).

export type AdminUserRole = 'super_admin' | 'admin' | 'professor' | 'student';

export type AdminCreatableRole = 'admin' | 'professor' | 'student';

export interface AdminUserResponse {
	id: number;
	email?: string | null;
	role: AdminUserRole;
	first_name: string | null;
	last_name: string | null;
	is_active: boolean;
	must_change_password: boolean;
	last_login: string | null;
	created_at: string;
}

export interface AdminUserCreateResponse extends AdminUserResponse {
	temp_password: string;
}

export interface AdminUser {
	id: number;
	email?: string | null;
	role: AdminUserRole;
	firstName?: string;
	lastName?: string;
	isActive: boolean;
	mustChangePassword: boolean;
	lastLogin?: string;
	createdAt: string;
}

export interface AdminUserCreatePayload {
	email: string;
	role: AdminCreatableRole;
	first_name: string;
	middle_name?: string;
	last_name: string;
}

export interface AdminUserFilters {
	search?: string;
	role?: AdminUserRole;
	is_active?: boolean;
	page?: number;
	size?: number;
}

// Admin-initiated password reset — one response shape behind all three routes
// (`POST /admin/users/{id}/reset-password`, and its student/professor
// equivalents). `temp_password` is returned exactly once and is not
// retrievable afterwards, so the UI has to show it in the same interaction
// that triggered the call.
export interface AdminPasswordResetResponse {
	temp_password: string;
}

// --- Account lockout (admin override, backend LockoutStatusResponse) -----------
//
// Wire shape mirrors backend/src/features/auth/schema.py::LockoutStatusResponse
// exactly (snake_case). The camelCase view-model is what pages render; the
// service layer maps wire → view. Display only fields present in the response;
// reason/source, failed-attempt count, and override history are unavailable.
export interface LockoutStatusResponse {
	user_id: number;
	email?: string | null;
	role: string;
	is_locked: boolean;
	is_permanently_locked: boolean;
	locked_at: string | null;
	lockout_level: number;
	lockout_duration_minutes: number;
	locked_until: string | null;
	remaining_minutes: number | null;
	last_lockout_at: string | null;
	override_until: string | null;
	override_remaining_minutes: number | null;
}

export interface LockoutStatus {
	userId: number;
	email?: string | null;
	role: string;
	isLocked: boolean;
	isPermanentlyLocked: boolean;
	lockedAt?: string;
	lockoutLevel: number;
	lockoutDurationMinutes: number;
	lockedUntil?: string;
	remainingMinutes?: number;
	lastLockoutAt?: string;
	overrideUntil?: string;
	overrideRemainingMinutes?: number;
}

export interface LockoutReasonRequest {
	reason: string;
}

export interface LockoutOverrideRequest {
	duration_minutes: number;
	reason: string;
}
