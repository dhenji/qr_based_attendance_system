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
	classroom_name: string | null;
	classroom_lat: number | null;
	classroom_lng: number | null;
	default_present_window_minutes: number;
	default_late_window_minutes: number;
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
	classroomName?: string;
	classroomLat?: number;
	classroomLng?: number;
	presentWindowMinutes: number;
	lateWindowMinutes: number;
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
	semester_weeks: number;
	schedule_days: string;
	schedule_start_time: string;
	schedule_end_time: string;
	// Local-only label (see AdminOfferingResponse.course_type).
	course_type?: CourseType;
	classroom_name?: string;
	classroom_lat?: number;
	classroom_lng?: number;
	default_present_window_minutes?: number;
	default_late_window_minutes?: number;
}

// Mutable subset only: course_id/program_id/year_level_id/semester/
// academic_year are identity and rejected server-side when patched.
export interface AdminOfferingUpdatePayload {
	sessions_per_week?: number;
	semester_weeks?: number;
	schedule_days?: string;
	schedule_start_time?: string;
	schedule_end_time?: string;
	course_type?: CourseType;
	classroom_name?: string | null;
	classroom_lat?: number | null;
	classroom_lng?: number | null;
	default_present_window_minutes?: number;
	default_late_window_minutes?: number;
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
	semester: string;
}

export interface AdminRosterItemResponse {
	student_id: string;
	name: string;
	section: string | null;
	enrolled_at: string;
}

export interface AdminRosterItem {
	studentId: string;
	name: string;
	section?: string;
	enrolledAt: string;
}

export interface AdminRosterFilters {
	section?: string;
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
	risk_level?: AnalyticsRiskLevel;
	unpromoted_only?: boolean;
	page?: number;
	size?: number;
	// Promote-scope keys only (the POST ignores every other filter).
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

export type AuditEntityType =
	| 'program'
	| 'year_level'
	| 'course'
	| 'course_offering'
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
	| 'assign'
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

export interface AuditLogItemResponse {
	id: number;
	action: string;
	entity_type: string;
	entity_id: number | null;
	old_value: unknown;
	new_value: unknown;
	performed_by: string | number | null;
	performed_at: string;
}

export interface AuditLogFilters {
	entity_type?: AuditEntityType;
	action?: AuditAction;
	performed_by?: string;
	date_from?: string;
	date_to?: string;
	page?: number;
	size?: number;
}

export interface StructureChangeResponse {
	id: number;
	action: string;
	entity_type: string;
	entity_id: number;
	old_value: string | null;
	new_value: string | null;
	performed_by: string;
	performed_at: string;
}

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
	email: string;
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
	email: string;
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
