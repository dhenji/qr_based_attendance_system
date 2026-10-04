// professor.ts
// Professor domain types.
//
// `Professor` is the camelCase view-model used across the UI.
// `ProfessorProfileResponse` is the raw snake_case wire shape from
// GET /professor/profile (docs/architecture/api-contracts.md "Profile") —
// services map it to the view-model. Mirrors
// backend/src/features/professor/schema.py (ProfessorProfileRead +
// AssignedOfferingItem) exactly, so the mapping stays mechanical.
export interface ProfessorAssignedOffering {
	id?: number;
	offering_id: number;
	course_id: number;
	course_code: string;
	course_name: string;
	program_id?: number;
	program_code: string;
	year_level_id?: number;
	year_level_label: string;
	semester: string;
	academic_year: string;
	section: string[];
	is_primary: boolean;
	effective_from?: string;
	effective_to?: string | null;
	units?: number;
	enrolled_count?: number;
}

export interface Professor {
	id: number;
	firstName: string;
	middleName?: string;
	lastName: string;
	email: string;
	department?: string;
	assignedCourses: ProfessorAssignedOffering[];
	claimStatus: 'Claimed' | 'Unclaimed';
	createdAt: string;
	sessionCount: number;
}

// GET /professor/profile
export interface ProfessorProfileResponse {
	id: number;
	first_name: string;
	middle_name: string | null;
	last_name: string;
	email: string;
	department: string | null;
	assigned_courses: ProfessorAssignedOffering[];
	claim_status: 'Claimed' | 'Unclaimed';
	created_at: string;
	session_count: number;
}

// Course-card view-model assembled from GET /professor/courses.
//
// Only fields the contract actually returns: schedule clock-times, classroom
// and window defaults are NOT on AssignedOfferingItem, so cards must not ask
// for them. `sections` stays an array end-to-end (the backend derives it as
// the distinct set of student sections across the offering's enrollments, and
// it is empty when nothing is enrolled yet) — the page joins it at render.
export interface ProfessorCourseSummary {
	offeringId: number;
	courseId: number;
	courseCode: string;
	courseName: string;
	units: number;
	programCode: string;
	yearLevelLabel: string;
	semester: string;
	academicYear: string;
	sections: string[];
	isPrimary: boolean;
	enrolledCount: number;
}

// GET /professor/dashboard
//
// One entry per session the professor runs today, carrying the scanned/enrolled
// pair the live session tiles show. It deliberately carries no course identity
// (no code, name, section, or clock time): the dashboard page still lists
// today's sessions through GET /professor/sessions for those columns and joins
// these counts on `session_id`. Same convention as the professor attendance
// ledger, which also joins course identity client-side.
export interface ProfessorTodaySessionResponse {
	session_id: number;
	offering_id: number;
	scanned: number;
	enrolled: number;
}

export interface ProfessorDashboardResponse {
	sessions_today: number;
	sessions_completed: number;
	total_students: number;
	avg_rate: number;
	today_sessions: ProfessorTodaySessionResponse[];
}
