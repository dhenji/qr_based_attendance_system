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
