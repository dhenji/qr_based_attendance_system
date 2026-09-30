// features/admin/programs/schema.ts
// Zod schemas for the program management forms. Mirrors the backend
// validators in features/program/schema.py (code upper-normalised, ranges);
// the backend remains the source of truth for 409s (duplicate code,
// year_number_exists, year_has_courses).

import { z } from 'zod';
import { TERM_CODES, TERM_LABELS } from '$lib/shared/constants/terms';

export const programCreateSchema = z.object({
	code: z.string().trim().toUpperCase().min(2).max(20),
	name: z.string().trim().min(1, 'Required').max(100),
	description: z.string().trim().max(1000).optional().or(z.literal('')),
	total_years: z.coerce.number().int().min(1).max(10),
});

export type ProgramCreateInput = z.infer<typeof programCreateSchema>;

export const programUpdateSchema = z.object({
	name: z.string().trim().min(1).max(100).optional(),
	description: z.string().trim().max(1000).optional().or(z.literal('')),
	is_active: z.boolean().optional(),
});

export type ProgramUpdateInput = z.infer<typeof programUpdateSchema>;

export const termSchema = z.object({
	code: z.enum(TERM_CODES, { message: 'Pick a term code' }),
	label: z.enum(TERM_LABELS, { message: 'Pick a term label' }),
});

export type TermInput = z.infer<typeof termSchema>;

// The backend's Term model is a bare { code, label } pair with no uniqueness
// check, and course_offerings.semester is free-text String(20) with no FK to
// these codes. A repeated code therefore reaches the database intact — and the
// detail page keys its term chips by code, where Svelte 5 throws on duplicate
// keys. Rejecting duplicates here turns that crash into a form error.
const uniqueTermCodes = <T extends z.ZodTypeAny>(schema: T) =>
	schema.refine(
		(terms: { code: string }[]) => new Set(terms.map((t) => t.code)).size === terms.length,
		{ message: 'Term codes must be unique' }
	);

export const yearLevelCreateSchema = z.object({
	year_number: z.coerce.number().int().min(1).max(10),
	label: z.string().trim().min(1, 'Required').max(50),
	terms: uniqueTermCodes(z.array(termSchema).default([])),
});

export type YearLevelCreateInput = z.infer<typeof yearLevelCreateSchema>;

export const yearLevelUpdateSchema = z.object({
	label: z.string().trim().min(1).max(50).optional(),
	terms: uniqueTermCodes(z.array(termSchema).optional()),
});

export type YearLevelUpdateInput = z.infer<typeof yearLevelUpdateSchema>;
