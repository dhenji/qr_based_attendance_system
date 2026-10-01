// features/admin/analytics/service.ts
// Admin analytics + attendance-overview service.
//
// The backend for these endpoints does not exist yet (features/analytics is
// model-only and unmounted), so the calls below go through endpoint defs
// whose mocks return deterministic, mutually consistent data. The def URLs
// and shapes mirror docs/architecture/api-contracts.md exactly, so the swap
// to the real backend stays mechanical: no page or service change needed.
// Real API by default; mocks only when PUBLIC_MOCK_MODE=true.
//
// Rate semantics (D36): compliance = present / total (default display),
// participation = (present + late + excused) / total (toggle). At-risk
// thresholds (D35) live in schema.ts as named constants mirroring the future
// backend heuristic; the backend remains the source of truth.

import { get, post } from '$lib/api/client';
import { buildCsv } from '$lib/features/report/service';
import type {
	AdminAnalyticsFilters,
	AdminCourse,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewFilters,
	AttendanceOverviewItemResponse,
	Program,
	RecentScanResponse,
	RiskRefreshResponse,
	YearLevel,
} from '$lib/shared/types';

export type AnalyticsMetric = 'compliance' | 'participation';

const analyticsParams = (f: AdminAnalyticsFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	if (f.course_ids && f.course_ids.length > 0) params.course_ids = f.course_ids.join(',');
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	if (f.granularity) params.granularity = f.granularity;
	if (f.risk_level) params.risk_level = f.risk_level;
	return params;
};

export const getAnalyticsOverview = async (
	filters: AdminAnalyticsFilters = {}
): Promise<AnalyticsOverviewResponse> =>
	get<AnalyticsOverviewResponse>('adminAnalyticsOverview', analyticsParams(filters));

export interface EnrichedComparisonRow extends AnalyticsComparisonItemResponse {
	courseName?: string;
	programCode?: string;
	yearLevelLabel?: string;
}

// Client-side joins for display: the comparison contract carries ids plus
// course_code only, so names resolve against the loaded dropdown sources.
export const enrichComparison = (
	items: AnalyticsComparisonItemResponse[],
	courses: AdminCourse[],
	programs: Program[],
	years: YearLevel[]
): EnrichedComparisonRow[] => {
	const courseById = new Map(courses.map((c) => [c.id, c]));
	const programById = new Map(programs.map((p) => [p.id, p]));
	const yearById = new Map(years.map((y) => [y.id, y]));
	return items.map((r) => ({
		...r,
		courseName: courseById.get(r.course_id)?.courseName,
		programCode: programById.get(r.program_id)?.code,
		yearLevelLabel: yearById.get(r.year_level_id)?.label,
	}));
};

export const getAnalyticsComparison = async (
	filters: AdminAnalyticsFilters = {}
): Promise<AnalyticsComparisonItemResponse[]> => {
	const response = await get<{ items: AnalyticsComparisonItemResponse[] }>(
		'adminAnalyticsComparison',
		analyticsParams(filters)
	);
	return response.items ?? [];
};

export const getAnalyticsTrends = async (
	filters: AdminAnalyticsFilters = {}
): Promise<AnalyticsTrendItemResponse[]> => {
	const response = await get<{ items: AnalyticsTrendItemResponse[] }>(
		'adminAnalyticsTrends',
		analyticsParams(filters)
	);
	return response.items ?? [];
};

export const getAtRisk = async (
	filters: AdminAnalyticsFilters = {}
): Promise<AnalyticsAtRiskItemResponse[]> => {
	const response = await get<{ items: AnalyticsAtRiskItemResponse[] }>(
		'adminAnalyticsAtRisk',
		analyticsParams(filters)
	);
	return response.items ?? [];
};

// Manual risk-score recalculation (admin-only). The contract rate-limits to
// 1 call per 60s per admin — the page surfaces the 429 message as-is.
export const refreshRiskScores = async (): Promise<RiskRefreshResponse> =>
	post<RiskRefreshResponse>('adminAnalyticsRefreshRisk');

const overviewParams = (f: AttendanceOverviewFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.course_id !== undefined) params.course_id = String(f.course_id);
	if (f.professor_id !== undefined) params.professor_id = String(f.professor_id);
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	return params;
};

export const getAttendanceOverview = async (
	filters: AttendanceOverviewFilters = {}
): Promise<AttendanceOverviewItemResponse[]> => {
	const response = await get<{ items: AttendanceOverviewItemResponse[] }>(
		'adminAttendanceOverview',
		overviewParams(filters)
	);
	return response.items ?? [];
};

export const getRecentScans = async (limit = 10): Promise<RecentScanResponse[]> => {
	const response = await get<{ items: RecentScanResponse[] }>('adminRecentScans', {
		limit: String(limit),
	});
	return response.items ?? [];
};

// --- CSV exports (Export tab + attendance overview) --------------------------

const percent = (rate: number): string => `${(rate * 100).toFixed(1)}%`;

export const overviewCsv = (overview: AnalyticsOverviewResponse): string =>
	buildCsv(
		['total_students', 'total_courses', 'avg_compliance_rate', 'avg_participation_rate', 'total_sessions'],
		[[
			overview.total_students,
			overview.total_courses,
			percent(overview.avg_compliance_rate),
			percent(overview.avg_participation_rate),
			overview.total_sessions,
		]]
	);

export const comparisonCsv = (rows: EnrichedComparisonRow[]): string =>
	buildCsv(
		['course_code', 'course_name', 'cohort', 'compliance_rate', 'participation_rate', 'total_sessions'],
		rows.map((r) => [
			r.course_code,
			r.courseName ?? '',
			[r.programCode ?? `Program ${r.program_id}`, r.yearLevelLabel ?? `Year ${r.year_level_id}`].join(' '),
			percent(r.compliance_rate),
			percent(r.participation_rate),
			r.total_sessions,
		])
	);

export const trendsCsv = (rows: AnalyticsTrendItemResponse[]): string =>
	buildCsv(
		['date', 'compliance_rate', 'participation_rate', 'total_sessions'],
		rows.map((r) => [r.date, percent(r.compliance_rate), percent(r.participation_rate), r.total_sessions])
	);

export const atRiskCsv = (rows: AnalyticsAtRiskItemResponse[]): string =>
	buildCsv(
		['student_id', 'student_name', 'program', 'year_level', 'course_code', 'course_name', 'absence_rate', 'max_streak', 'trend_slope', 'risk_level', 'computed_at'],
		rows.map((r) => [
			r.student_id,
			r.student_name,
			r.program,
			r.year_level,
			r.course_code,
			r.course_name,
			percent(r.absence_rate),
			r.max_streak,
			r.trend_slope,
			r.risk_level,
			r.computed_at,
		])
	);

export const attendanceOverviewCsv = (rows: AttendanceOverviewItemResponse[]): string =>
	buildCsv(
		['course_code', 'course_name', 'sessions_count', 'avg_rate', 'trend'],
		rows.map((r) => [r.course_code, r.course_name, r.sessions_count, percent(r.avg_rate), r.trend])
	);

export const downloadCsv = (filename: string, csv: string): void => {
	const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	document.body.appendChild(link);
	link.click();
	link.remove();
	URL.revokeObjectURL(url);
};
