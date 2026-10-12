// features/admin/offerings/schema.ts
// Zod schemas for the offering + assignment forms. Mirrors the backend
// validators in features/course/schema.py (upper-normalised schedule_days,
// end-after-start, ranges); the backend remains the source of truth for 409s
// (offering_exists, overlapping_assignment) and 422s (windows_exceed_duration,
// invalid_schedule_window on the merged result).

import { z } from 'zod';

const timeField = z
	.string()
	.trim()
	.regex(/^([01]\d|2[0-3]):([0-5]\d)(:([0-5]\d))?$/, 'Use HH:MM (24h)');

const dateField = z
	.string()
	.trim()
	.regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD');

// End-after-start for a start/end pair carried in one payload. Single-sided
// PATCHes are checked against the stored offering on the page before submit
// (the schema only sees the fields it was sent — same blind spot the backend
// handles with invalid_schedule_window on the merged result).
const endAfterStart = <T extends { schedule_start_time?: string; schedule_end_time?: string }>(
	value: T,
	ctx: z.RefinementCtx
) => {
	if (value.schedule_start_time && value.schedule_end_time) {
		if (value.schedule_end_time <= value.schedule_start_time) {
			ctx.addIssue({
				code: z.ZodIssueCode.custom,
				message: 'End time must be after start time',
				path: ['schedule_end_time'],
			});
		}
	}
};

export const offeringCreateSchema = z
	.object({
		course_id: z.coerce.number().int().gt(0, 'Pick a course'),
		program_id: z.coerce.number().int().gt(0, 'Pick a program'),
		year_level_id: z.coerce.number().int().gt(0, 'Pick a year level'),
		semester: z.string().trim().min(1, 'Required').max(20),
		academic_year: z.string().trim().min(4).max(20),
		sessions_per_week: z.coerce.number().int().min(1).max(7),
		semester_weeks: z.coerce.number().int().min(1).max(52),
		schedule_days: z.string().trim().toUpperCase().min(1).max(10),
		schedule_start_time: timeField,
		schedule_end_time: timeField,
		course_type: z.enum(['lecture', 'lab']),
		classroom_name: z.string().trim().max(100).optional().or(z.literal('')),
		classroom_lat: z
			.string()
			.trim()
			.optional()
			.or(z.literal('')),
		classroom_lng: z
			.string()
			.trim()
			.optional()
			.or(z.literal('')),
		default_present_window_minutes: z.coerce.number().int().min(1).max(480).default(5),
		default_late_window_minutes: z.coerce.number().int().min(1).max(480).default(10),
	})
	.superRefine(endAfterStart);

export type OfferingCreateInput = z.infer<typeof offeringCreateSchema>;

export const offeringUpdateSchema = z
	.object({
		sessions_per_week: z.coerce.number().int().min(1).max(7).optional(),
		semester_weeks: z.coerce.number().int().min(1).max(52).optional(),
		schedule_days: z.string().trim().toUpperCase().min(1).max(10).optional(),
		schedule_start_time: timeField.optional(),
		schedule_end_time: timeField.optional(),
		course_type: z.enum(['lecture', 'lab']).optional(),
		classroom_name: z.string().trim().max(100).optional().or(z.literal('')),
		classroom_lat: z
			.string()
			.trim()
			.optional()
			.or(z.literal('')),
		classroom_lng: z
			.string()
			.trim()
			.optional()
			.or(z.literal('')),
		default_present_window_minutes: z.coerce.number().int().min(1).max(480).optional(),
		default_late_window_minutes: z.coerce.number().int().min(1).max(480).optional(),
		is_active: z.boolean().optional(),
	})
	.superRefine(endAfterStart);

export type OfferingUpdateInput = z.infer<typeof offeringUpdateSchema>;

export const assignmentCreateSchema = z
	.object({
		professor_id: z.coerce.number().int().gt(0, 'Pick a professor'),
		is_primary: z.boolean().default(false),
		effective_from: dateField,
		effective_to: dateField.optional().or(z.literal('')),
		semester: z.string().trim().min(1, 'Required').max(20),
	})
	.superRefine((value, ctx) => {
		if (value.effective_to && value.effective_to <= value.effective_from) {
			ctx.addIssue({
				code: z.ZodIssueCode.custom,
				message: 'End date must be after start date',
				path: ['effective_to'],
			});
		}
	});

export type AssignmentCreateInput = z.infer<typeof assignmentCreateSchema>;

// Windows-sum guard checked on the page before submit: present + late must
// fit inside the course session duration (backend 422 windows_exceed_duration).
export const windowsWithinDuration = (
	presentMinutes: number,
	lateMinutes: number,
	durationHours: number
): boolean => presentMinutes + lateMinutes <= durationHours * 60;
