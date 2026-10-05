// features/admin/audit/schema.ts
// Zod schemas for the audit-log filters. All fields optional; a blank value
// means "no filter" (the backend AND-combines them). Values outside the
// entity/action vocabularies are 422 invalid_audit_filter server-side, so the
// client validates against the same lists for fast errors.

import { z } from 'zod';

const dateField = z
	.string()
	.trim()
	.regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD')
	.optional()
	.or(z.literal(''));

export const AUDIT_ENTITY_VALUES = [
	'program',
	'year_level',
	'course',
	'course_offering',
	'student',
	'professor',
	'enrollment',
	'course_professor',
	'excuse',
	'session',
	'face_enrollment',
	'attendance_record',
	'backup',
	'app_setting',
	'user',
	'maintenance',
] as const;

export const AUDIT_ACTION_VALUES = [
	'create',
	'update',
	'archive',
	'delete',
	'import',
	'enroll',
	'assign',
	'unassign',
	'open',
	'close',
	'approve',
	'reject',
	'revoke',
	'lock',
	'unlock',
	'login_failed',
	'password_reset',
] as const;

export const auditFilterSchema = z
	.object({
		date_from: dateField,
		date_to: dateField,
		entity_type: z
			.enum(AUDIT_ENTITY_VALUES)
			.optional()
			.or(z.literal('')),
		action: z
			.enum(AUDIT_ACTION_VALUES)
			.optional()
			.or(z.literal('')),
		performed_by: z.string().trim().max(100).optional().or(z.literal('')),
	})
	.superRefine((value, ctx) => {
		if (value.date_from && value.date_to && value.date_from > value.date_to) {
			ctx.addIssue({
				code: z.ZodIssueCode.custom,
				message: 'From date must be on or before To date',
				path: ['date_from'],
			});
		}
	});

export type AuditFilterInput = z.infer<typeof auditFilterSchema>;
