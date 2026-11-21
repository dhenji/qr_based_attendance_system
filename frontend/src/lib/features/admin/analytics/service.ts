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

import { get, getText, post, postText, TEXT_EXPORTS, type QueryParams } from '$lib/api/client';
import { buildCsv, COMPARISON_PAGE_SIZE } from '$lib/features/report/service';
import { downloadTextFile } from '$lib/shared/utils/file';
import type {
	AdminAnalyticsFilters,
	AdminCourse,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsCourseOptionsResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewFilters,
	AttendanceOverviewItemResponse,
	AttendanceRecordItemResponse,
	AttendanceSummaryResponse,
	Program,
	PromoteStagingResponse,
	RiskRefreshResponse,
	RiskStagingFilters,
	RiskStagingItemResponse,
	RiskStagingResponse,
	YearLevel,
} from '$lib/shared/types';

export type AnalyticsMetric = 'compliance' | 'participation';

const analyticsParams = (f: AdminAnalyticsFilters): QueryParams => {
	const params: QueryParams = {};
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	// Repeated keys (?course_ids=1&course_ids=2): FastAPI parses these into
	// list[int]; a comma-joined string does not split server-side.
	if (f.course_ids && f.course_ids.length > 0)
		params.course_ids = f.course_ids.map(String);
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	if (f.granularity) params.granularity = f.granularity;
	if (f.risk_level) params.risk_level = f.risk_level;
	if (f.session_type) params.session_type = f.session_type;
	if ((f as any).q) params.q = (f as any).q;
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

// One row per (course, program, year level) cohort, so the set grows with the
// catalogue × cohorts. It renders as a single chart/table, so it is requested
// in one page at the server's max page size (`COMPARISON_PAGE_SIZE`, mirroring
// backend shared/pagination.py) and `total` lets the tab flag truncation
// instead of silently dropping cohorts past the page.
export const getAnalyticsComparison = async (
	filters: AdminAnalyticsFilters = {}
): Promise<{ items: AnalyticsComparisonItemResponse[]; total: number }> => {
	const page = (filters as any).page ?? 1;
	const size = (filters as any).size ?? COMPARISON_PAGE_SIZE;
	const response = await get<{
		items: AnalyticsComparisonItemResponse[];
		total?: number;
	}>('adminAnalyticsComparison', {
		...analyticsParams(filters),
		page: String(page),
		size: String(size),
	});
	const items = response.items ?? [];
	return { items, total: response.total ?? items.length };
};

export interface CourseOption {
	id: number;
	code: string;
	name: string;
}

// Courses with at least one offering in the picked scope (#279) — the rail's
// picker reads this instead of the whole catalogue, so a course no report can
// show in the current scope is not selectable.
export const getCourseOptions = async (
	filters: {
		program_id?: number;
		year_level_id?: number;
		semester?: string;
		q?: string;
		limit?: number;
	} = {}
): Promise<{ items: CourseOption[]; total: number }> => {
	const params: QueryParams = {};
	if (filters.program_id !== undefined) params.program_id = String(filters.program_id);
	if (filters.year_level_id !== undefined) params.year_level_id = String(filters.year_level_id);
	if (filters.semester) params.semester = filters.semester;
	if (filters.q) params.q = filters.q;
	if (filters.limit !== undefined) params.limit = String(filters.limit);
	const response = await get<AnalyticsCourseOptionsResponse>(
		'adminAnalyticsCourseOptions',
		params,
		undefined,
		{ cacheTtlMs: 10_000 }
	);
	const items = (response.items ?? []).map((o) => ({
		id: o.course_id,
		code: o.course_code,
		name: o.course_name,
	}));
	return { items, total: response.total ?? items.length };
};

export const getAnalyticsTrends = async (
	filters: AdminAnalyticsFilters = {}
): Promise<{ items: AnalyticsTrendItemResponse[]; total: number }> => {
	const page = (filters as any).page ?? 1;
	const size = (filters as any).size ?? 20;
	const params = { ...analyticsParams(filters), page: String(page), size: String(size) };
	const response = await get<{
		items: AnalyticsTrendItemResponse[];
		total?: number;
	}>('adminAnalyticsTrends', params);
	const items = response.items ?? [];
	return { items, total: response.total ?? items.length };
};

export const getAtRisk = async (
	filters: AdminAnalyticsFilters = {}
): Promise<{ items: AnalyticsAtRiskItemResponse[]; total: number }> => {
	const page = (filters as any).page ?? 1;
	const size = (filters as any).size ?? 20;
	const params = { ...analyticsParams(filters), page: String(page), size: String(size) };
	const response = await get<{
		items: AnalyticsAtRiskItemResponse[];
		total?: number;
	}>('adminAnalyticsAtRisk', params);
	const items = response.items ?? [];
	return { items, total: response.total ?? items.length };
};

// Manual risk-score recalculation (admin-only). The contract rate-limits to
// 1 call per 60s per admin — the page surfaces the 429 message as-is.
export const refreshRiskScores = async (): Promise<RiskRefreshResponse> =>
	post<RiskRefreshResponse>('adminAnalyticsRefreshRisk');

// Dry-run staging review (backend #137). listRiskStaging reads staged rows
// without touching live scores; promoteRiskStaging copies the unpromoted
// rows in scope into the live scores. Mock mode returns the empty fixtures,
// so the page renders the "no dry-run yet" hint instead of demo rows.
const stagingParams = (f: RiskStagingFilters): QueryParams => {
	const params: QueryParams = {};
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	if (f.course_ids && f.course_ids.length > 0)
		params.course_ids = f.course_ids.map(String);
	if (f.risk_level) params.risk_level = f.risk_level;
	if ((f as any).q) params.q = (f as any).q;
	if (f.unpromoted_only !== undefined) params.unpromoted_only = String(f.unpromoted_only);
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listRiskStaging = async (
	filters: RiskStagingFilters = {}
): Promise<RiskStagingResponse> =>
	get<RiskStagingResponse>('adminRiskStaging', stagingParams(filters));

// Promote honors the rail's scope (#279): program/year/course narrow which
// staged rows get copied, same as the review list they were chosen from.
// risk_level, unpromoted_only, and paging stay list-only, so they are left
// out of the call rather than promoted past their scope.
export const promoteRiskStaging = async (
	filters: Pick<
		RiskStagingFilters,
		'student_id' | 'offering_id' | 'semester' | 'program_id' | 'year_level_id' | 'course_ids'
	> = {}
): Promise<PromoteStagingResponse> => {
	const params: QueryParams = {};
	if (filters.student_id !== undefined) params.student_id = String(filters.student_id);
	if (filters.offering_id !== undefined) params.offering_id = String(filters.offering_id);
	if (filters.semester) params.semester = filters.semester;
	if (filters.program_id !== undefined) params.program_id = String(filters.program_id);
	if (filters.year_level_id !== undefined) params.year_level_id = String(filters.year_level_id);
	if (filters.course_ids && filters.course_ids.length > 0)
		params.course_ids = filters.course_ids.map(String);
	return post<PromoteStagingResponse>('adminRiskStagingPromote', undefined, params);
};

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
	if (f.program_id !== undefined) params.program_id = String(f.program_id);
	if (f.year_level_id !== undefined) params.year_level_id = String(f.year_level_id);
	if (f.semester) params.semester = f.semester;
	if (f.course_id !== undefined) params.course_id = String(f.course_id);
	if (f.professor_id !== undefined) params.professor_id = String(f.professor_id);
	if (f.session_type) params.session_type = f.session_type;
	if (f.status) params.status = f.status;
	if (f.student_search) params.student_search = f.student_search;
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	if (f.page !== undefined) params.page = String(f.page);
	if (f.size !== undefined) params.size = String(f.size);
	if (f.sort_by) params.sort_by = f.sort_by;
	if (f.sort_dir) params.sort_dir = f.sort_dir;
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

export const getAttendanceSummary = async (
	filters: AttendanceOverviewFilters = {}
): Promise<AttendanceSummaryResponse> =>
	get<AttendanceSummaryResponse>('adminAttendanceSummary', overviewParams(filters));

export const getAttendanceRecords = async (
	filters: AttendanceOverviewFilters = {}
): Promise<{ items: AttendanceRecordItemResponse[]; total: number; page: number; size: number }> => {
	const response = await get<{
		items: AttendanceRecordItemResponse[];
		total?: number;
		page?: number;
		size?: number;
	}>('adminAttendanceRecords', overviewParams(filters));
	return {
		items: response.items ?? [],
		total: response.total ?? (response.items?.length ?? 0),
		page: response.page ?? 1,
		size: response.size ?? 20,
	};
};

export const fetchAttendanceRecordsCsv = (filters: AttendanceOverviewFilters = {}): Promise<string> =>
	getText(TEXT_EXPORTS.adminAttendanceRecords, overviewParams(filters));

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
): Promise<string> => getText(TEXT_EXPORTS.adminOverview, overviewParams(filters));

// Server CSV export (POST /admin/analytics/export, backend #136). Body
// mirrors AnalyticsExportRequest; per-course rows for the filter set, so the
// download matches the Comparison tab. Throws in mock mode and when the
// backend is unreachable — the Export tab falls back to the client-side
// builders above.
export type AnalyticsExportBody = {
	program_id?: number;
	year_level_id?: number;
	semester?: string;
	course_ids?: number[];
	date_from?: string;
	date_to?: string;
	session_type?: 'lecture' | 'lab';
};

export const fetchAnalyticsExportCsv = (body: AnalyticsExportBody): Promise<string> =>
	postText(TEXT_EXPORTS.adminAnalytics, { format: 'csv', ...body });

export const downloadCsv = (filename: string, csv: string): void => {
	downloadTextFile(csv, filename);
};
