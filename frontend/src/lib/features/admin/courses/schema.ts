// features/admin/courses/schema.ts
// Zod schemas for the course-template forms. Mirrors the backend validators
// in features/course/schema.py (code upper-normalised, units 1-6, duration
// 0.5-8.0h); the backend remains the source of truth for 409s
// (course_code_exists).

import { z } from 'zod';

export const courseCreateSchema = z.object({
	course_code: z.string().trim().toUpperCase().min(2).max(20),
	course_name: z.string().trim().min(1, 'Required').max(100),
	units: z.coerce.number().int().min(1).max(6),
	session_duration_hours: z.coerce.number().min(0.5).max(8),
	// No type: a course template is type-agnostic (D77) — lecture/lab lives
	// on sessions and offering components, so one course can mix both.
});

export type CourseCreateInput = z.infer<typeof courseCreateSchema>;

export const courseUpdateSchema = z.object({
	course_code: z.string().trim().toUpperCase().min(2).max(20).optional(),
	course_name: z.string().trim().min(1, 'Required').max(100).optional(),
	units: z.coerce.number().int().min(1).max(6).optional(),
	session_duration_hours: z.coerce.number().min(0.5).max(8).optional(),
	is_active: z.boolean().optional(),
});

export type CourseUpdateInput = z.infer<typeof courseUpdateSchema>;
