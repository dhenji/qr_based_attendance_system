// features/admin/audit/schema.ts
// Zod schemas for the audit-log filters. All fields optional; the backend
// (when it lands in Phase 8) remains the source of truth for 422s.

import { z } from 'zod';

const dateField = z
	.string()
	.trim()
	.regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD')
	.optional()
	.or(z.literal(''));

export const auditFilterSchema = z
	.object({
		date_from: dateField,
		date_to: dateField,
		category: z
			.enum([
				'enrollment',
				'assignment',
				'excuse',
				'session',
				'face_enrollment',
				'backup',
				'structure',
				'settings',
				'lockout',
				'login',
			])
			.optional()
			.or(z.literal('')),
		search: z.string().trim().max(100).optional().or(z.literal('')),
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
