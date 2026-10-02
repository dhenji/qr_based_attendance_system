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
	username?: string;
}

export interface AdminStudentUpdatePayload {
	first_name?: string;
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
	username?: string;
	courses?: number[];
}

export interface AdminProfessorUpdatePayload {
	first_name?: string;
	last_name?: string;
	email?: string;
	department?: string;
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

export interface AdminCourseResponse {
	id: number;
	course_code: string;
	course_name: string;
	units: number;
	session_duration_hours: number;
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
	isActive: boolean;
	createdAt: string;
	updatedAt: string;
}

export interface AdminCourseCreatePayload {
	course_code: string;
	course_name: string;
	units: number;
	session_duration_hours: number;
}

export interface AdminCourseUpdatePayload {
	course_code?: string;
	course_name?: string;
	units?: number;
	session_duration_hours?: number;
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
// The backend for these endpoints does not exist yet (features/analytics is
// model-only), so the service layer reads these through endpoint defs whose
// mocks return deterministic, mutually consistent data; real wiring is ready
// for when the backend lands. Rate semantics (D36): compliance = present /
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

// --- Admin audit logs (Phase 8 backend; designed shape, D38/D20-D22) ---------
//
// No audit contract or table exists yet (audit_logs lands in Phase 8.5/8.7),
// so the shape below is designed from wireframe 4.8 (Time/User/Action) plus
// the action taxonomy in security-model §Audit-Log-Coverage. Category values
// are the ten logged action families. Rows come from two sources (see the
// audit service): live record-creation rows derived from roster lists
// (marked origin "system") and deterministic mock operational rows (origin
// "seed") until the backend trail lands.
//
// The academic-structure shape mirrors api-contracts
// GET /admin/system/academic-structure exactly (D38: program/year/course
// mutations with old/new values).

export type AuditCategory =
	| 'enrollment'
	| 'assignment'
	| 'excuse'
	| 'session'
	| 'face_enrollment'
	| 'backup'
	| 'structure'
	| 'settings'
	| 'lockout'
	| 'login';

export type AuditActorRole = 'admin' | 'professor' | 'student' | 'system';

export interface AuditLogItemResponse {
	id: number;
	occurred_at: string;
	actor_name: string;
	actor_role: AuditActorRole;
	action: string;
	category: AuditCategory;
	entity: string;
	detail?: string;
}

export interface AuditLogFilters {
	date_from?: string;
	date_to?: string;
	category?: AuditCategory;
	search?: string;
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
	username: string | null;
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
	username?: string;
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
	username?: string;
}

export interface AdminUserFilters {
	search?: string;
	role?: AdminUserRole;
	is_active?: boolean;
	page?: number;
	size?: number;
}
