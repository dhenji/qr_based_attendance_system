// program.ts
// Program + year-level domain types (admin Phase A).
//
// Wire shapes mirror backend/src/features/program/schema.py exactly
// (snake_case); the camelCase view-models are what pages render. Services
// map wire → view. Aggregates (course_count/year_level_count/terms_count)
// are derived per request server-side — never stored, never invented
// client-side.

export interface ProgramTerm {
	code: string;
	label: string;
}

export interface ProgramTermStructure {
	terms: ProgramTerm[];
}

export interface ProgramResponse {
	id: number;
	code: string;
	name: string;
	description: string | null;
	total_years: number;
	is_active: boolean;
	course_count: number;
	year_level_count: number;
	terms_count: number;
	created_at: string;
	updated_at: string;
}

export interface YearLevelResponse {
	id: number;
	program_id: number;
	year_number: number;
	label: string;
	term_structure: ProgramTermStructure;
	sort_order: number;
}

export interface ProgramDetailResponse extends ProgramResponse {
	year_levels: YearLevelResponse[];
}

export interface Program {
	id: number;
	code: string;
	name: string;
	description?: string;
	totalYears: number;
	isActive: boolean;
	courseCount: number;
	yearLevelCount: number;
	termsCount: number;
	createdAt: string;
	updatedAt: string;
}

export interface YearLevel {
	id: number;
	programId: number;
	yearNumber: number;
	label: string;
	terms: ProgramTerm[];
	sortOrder: number;
}

export interface ProgramDetail extends Program {
	yearLevels: YearLevel[];
}

export interface ProgramCreatePayload {
	code: string;
	name: string;
	description?: string;
	total_years: number;
}

export interface ProgramUpdatePayload {
	name?: string;
	description?: string;
	is_active?: boolean;
}

export interface YearLevelCreatePayload {
	year_number: number;
	label: string;
	term_structure: ProgramTermStructure;
	sort_order?: number;
}

export interface YearLevelUpdatePayload {
	label?: string;
	term_structure?: ProgramTermStructure;
	sort_order?: number;
}

export interface ProgramFilters {
	search?: string;
	is_active?: boolean;
	page?: number;
	size?: number;
}
