// features/admin/analytics/service.ts
// Admin analytics + attendance-overview service.
//
// The analytics + attendance-overview routers landed in backend #136/#138,
// so the calls below hit the real API by default; mocks only when
// PUBLIC_MOCK_MODE=true (or when the backend is unreachable and the caller
// falls back). The def URLs and shapes mirror
// docs/architecture/api-contracts.md exactly.
//
// Rate semantics (D36): compliance = present / total (default display),
// participation = (present + late + excused) / total (toggle). At-risk
// thresholds (D35) live in schema.ts as named constants mirroring the future
// backend heuristic; the backend remains the source of truth.

import { get, getText, post } from '$lib/api/client';
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
	PromoteStagingResponse,
	RecentScanResponse,
	RiskRefreshResponse,
	RiskStagingFilters,
	RiskStagingItemResponse,
	RiskStagingResponse,
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

// Dry-run staging review (backend #137). listRiskStaging reads staged rows
// without touching live scores; promoteRiskStaging copies the unpromoted
// rows in scope into the live scores. Mock mode returns the empty fixtures,
// so the page renders the "no dry-run yet" hint instead of demo rows.
const stagingParams = (f: RiskStagingFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	if (f.risk_level) params.risk_level = f.risk_level;
	if (f.unpromoted_only !== undefined) params.unpromoted_only = String(f.unpromoted_only);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listRiskStaging = async (
	filters: RiskStagingFilters = {}
): Promise<RiskStagingResponse> =>
	get<RiskStagingResponse>('adminRiskStaging', stagingParams(filters));

export const promoteRiskStaging = async (
	filters: RiskStagingFilters = {}
): Promise<PromoteStagingResponse> =>
	post<PromoteStagingResponse>('adminRiskStagingPromote', undefined, stagingParams(filters));

export const stagingCsv = (rows: RiskStagingItemResponse[]): string =>
	buildCsv(
		['student_id', 'student_name', 'program', 'year_level', 'course_code', 'course_name', 'absence_rate', 'max_streak', 'trend_slope', 'risk_level', 'computed_at', 'promoted_at'],
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
			r.promoted_at ?? '',
		])
	);

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

// Server CSV export (GET /admin/attendance/overview/export, backend #138).
// Same filter set as getAttendanceOverview, so the download matches the
// on-screen table. Throws in mock mode and when the backend is unreachable —
// the attendance page falls back to attendanceOverviewCsv above.
export const fetchAttendanceOverviewCsv = (
	filters: AttendanceOverviewFilters = {}
): Promise<string> => getText('/admin/attendance/overview/export', overviewParams(filters));

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
