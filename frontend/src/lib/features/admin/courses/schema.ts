// features/admin/courses/schema.ts
// Zod schemas for the course-template forms. Mirrors the backend validators
// in features/course/schema.py (code upper-normalised, units >= 1, duration
// 0.5-8.0h); the backend remains the source of truth for 409s
// (course_code_exists).

import { z } from 'zod';

export const courseCreateSchema = z.object({
	course_code: z
		.string()
		.trim()
		.toUpperCase()
		.min(2, 'Course code is required. Enter 2–20 characters.')
		.max(20, 'Course code is required. Enter 2–20 characters.'),
	course_name: z
		.string()
		.trim()
		.min(1, 'Course name is required. Enter up to 100 characters.')
		.max(100, 'Course name is required. Enter up to 100 characters.'),
	units: z.coerce
		.number()
		.int('Units are required. Enter a whole number of 1 or more.')
		.min(1, 'Units are required. Enter a whole number of 1 or more.'),
	session_duration_hours: z.coerce
		.number()
		.min(0.5, 'Session length is required. Enter a value between 0.5 and 8 hours.')
		.max(8, 'Session length is required. Enter a value between 0.5 and 8 hours.'),
});

export type CourseCreateInput = z.infer<typeof courseCreateSchema>;

export const courseUpdateSchema = z.object({
	course_code: z
		.string()
		.trim()
		.toUpperCase()
		.min(2, 'Course code is required. Enter 2–20 characters.')
		.max(20, 'Course code is required. Enter 2–20 characters.')
		.optional(),
	course_name: z
		.string()
		.trim()
		.min(1, 'Course name is required. Enter up to 100 characters.')
		.max(100, 'Course name is required. Enter up to 100 characters.')
		.optional(),
	units: z.coerce
		.number()
		.int('Units are required. Enter a whole number of 1 or more.')
		.min(1, 'Units are required. Enter a whole number of 1 or more.')
		.optional(),
	session_duration_hours: z.coerce
		.number()
		.min(0.5, 'Session length is required. Enter a value between 0.5 and 8 hours.')
		.max(8, 'Session length is required. Enter a value between 0.5 and 8 hours.')
		.optional(),
	is_active: z.boolean().optional(),
});

export type CourseUpdateInput = z.infer<typeof courseUpdateSchema>;