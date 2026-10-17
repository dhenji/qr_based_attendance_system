// features/admin/programs/schema.ts
// Zod schemas for the program management forms. Mirrors the backend
// validators in features/program/schema.py (code upper-normalised, ranges);
// the backend remains the source of truth for 409s (duplicate code,
// year_number_exists, year_has_courses).

import { z } from 'zod';

export const programCreateSchema = z.object({
	code: z.string().trim().toUpperCase().min(2).max(20),
	name: z.string().trim().min(1, 'Required').max(100),
	description: z.string().trim().max(1000).optional().or(z.literal('')),
	total_years: z.coerce.number().int().min(1).max(10),
});

export type ProgramCreateInput = z.infer<typeof programCreateSchema>;

export const programUpdateSchema = z.object({
	name: z.string().trim().min(1, 'Required').max(100).optional(),
	description: z.string().trim().max(1000).optional().or(z.literal('')),
	is_active: z.boolean().optional(),
});

export type ProgramUpdateInput = z.infer<typeof programUpdateSchema>;

export const termSchema = z.object({
	// Free text, mirroring the backend `Term` (`min_length=1`, trimmed): the
	// editor offers canonical codes as suggestions, but existing codes
	// (`1st_sem`, `midyear`, …) must round-trip unchanged — an offering's
	// `semester` matches the term code verbatim, so renaming one would drop
	// that offering back to the default weeks (D86).
	code: z.string().trim().min(1, 'Pick a term code'),
	label: z.string().trim().min(1, 'Pick a display name'),
	weeks: z.coerce
		.number()
		.int('Whole weeks only')
		.min(1, 'Enter at least 1 week')
		.max(52, 'At most 52 weeks')
		.optional(),
});

export type TermInput = z.infer<typeof termSchema>;

export const yearLevelCreateSchema = z
	.object({
		year_number: z.coerce.number().int().min(1).max(10),
		label: z.string().trim().min(1, 'Required').max(50),
		terms: z.array(termSchema).default([]),
	})
	.refine(
		(data) => new Set(data.terms.map((term) => term.code)).size === data.terms.length,
		{ message: 'Term codes must be unique within a year.', path: ['terms'] }
	);

export type YearLevelCreateInput = z.infer<typeof yearLevelCreateSchema>;

export const yearLevelUpdateSchema = z
	.object({
		label: z.string().trim().min(1, 'Required').max(50).optional(),
		terms: z.array(termSchema).optional(),
	})
	.refine(
		(data) => !data.terms || new Set(data.terms.map((term) => term.code)).size === data.terms.length,
		{ message: 'Term codes must be unique within a year.', path: ['terms'] }
	);

export type YearLevelUpdateInput = z.infer<typeof yearLevelUpdateSchema>;
