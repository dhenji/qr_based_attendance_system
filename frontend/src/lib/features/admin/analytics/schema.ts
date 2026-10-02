// features/admin/analytics/schema.ts
// Zod schemas for the analytics filter rail. Mirrors the backend list-query
// params in docs/architecture/api-contracts.md (all optional); the backend
// remains the source of truth for 422s.
//
// At-risk heuristic thresholds (D35) as named constants so the table badges
// and the future backend batch read the same numbers. Env-configurable
// server-side; these client copies only label the mock rows.

import { z } from 'zod';

export const ABSENCE_RATE_HIGH = 0.3;
export const ABSENCE_RATE_MEDIUM = 0.15;
export const ABSENCE_STREAK_HIGH = 3;
export const TREND_SLOPE_NEGATIVE = -0.05;

const dateField = z
	.string()
	.trim()
	.regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD')
	.optional()
	.or(z.literal(''));

export const analyticsFilterSchema = z
	.object({
		program_id: z.string().trim().optional().or(z.literal('')),
		year_level_id: z.string().trim().optional().or(z.literal('')),
		semester: z.string().trim().max(20).optional().or(z.literal('')),
		course_ids: z.array(z.number().int().gt(0)).default([]),
		date_from: dateField,
		date_to: dateField,
		granularity: z.enum(['daily', 'weekly', 'monthly']).default('daily'),
		risk_level: z.enum(['low', 'medium', 'high']).optional().or(z.literal('')),
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

export type AnalyticsFilterInput = z.infer<typeof analyticsFilterSchema>;

export const defaultAnalyticsRange = (days = 30): { from: string; to: string } => {
	const to = new Date();
	to.setHours(0, 0, 0, 0);
	const from = new Date(to);
	from.setDate(to.getDate() - (days - 1));
	const key = (d: Date): string => d.toISOString().slice(0, 10);
	return { from: key(from), to: key(to) };
};
