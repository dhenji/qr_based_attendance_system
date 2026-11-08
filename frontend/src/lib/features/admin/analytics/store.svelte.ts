// features/admin/analytics/store.svelte.ts
// Admin analytics state using Svelte 5 runes ($state object store).
//
// One region per tab (overview, comparison, trends, at-risk, export reads the
// same loaded rows) plus the attendance-overview table that backs the
// Attendance tab and the dashboard's at-a-glance strip. The filter rail writes
// `filters`; each tab loads through the service on Apply so tables never
// disagree with the server. Metric (compliance/participation, D36) is
// render-only — both rates ride every row.

import type {
	AdminAnalyticsFilters,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewFilters,
	AttendanceOverviewItemResponse,
	AttendanceRecordItemResponse,
	AttendanceSummaryResponse,
	PromoteStagingResponse,
	RiskRefreshResponse,
	RiskStagingFilters,
	RiskStagingItemResponse,
} from '$lib/shared/types';
import {
	getAnalyticsComparison,
	getAnalyticsOverview,
	getAnalyticsTrends,
	getAtRisk,
	getAttendanceOverview,
	getAttendanceRecords,
	getAttendanceSummary,
	listRiskStaging,
	promoteRiskStaging,
	refreshRiskScores,
	type AnalyticsMetric,
	type EnrichedComparisonRow,
} from '$lib/features/admin/analytics/service';

export const adminAnalyticsState = $state({
	filters: {} as AdminAnalyticsFilters,
	metric: 'compliance' as AnalyticsMetric,
	overview: null as AnalyticsOverviewResponse | null,
	comparison: [] as AnalyticsComparisonItemResponse[],
	// Server `total` for the comparison page: when it exceeds `comparison.length`
	// the tab shows a truncation hint rather than dropping cohorts silently.
	comparisonTotal: 0,
	trends: [] as AnalyticsTrendItemResponse[],
	atRisk: [] as AnalyticsAtRiskItemResponse[],
	loading: false,
	error: null as string | null,
	actionError: null as string | null,
	lastRefresh: null as RiskRefreshResponse | null,
});

export const adminAttendanceState = $state({
	items: [] as AttendanceOverviewItemResponse[],
	loading: false,
	error: null as string | null,
});

export const adminAttendanceSummaryState = $state({
	data: null as AttendanceSummaryResponse | null,
	loading: false,
	error: null as string | null,
});

export const adminAttendanceRecordsState = $state({
	items: [] as AttendanceRecordItemResponse[],
	total: 0,
	page: 1,
	size: 20,
	loading: false,
	error: null as string | null,
});

// Dry-run staging review (backend #137): staged rows plus paging, separate
// from the live At-Risk tab. lastPromote carries the most recent promote
// result for the confirmation summary.
export const adminStagingState = $state({
	items: [] as RiskStagingItemResponse[],
	total: 0,
	page: 1,
	size: 20,
	loading: false,
	error: null as string | null,
	lastPromote: null as PromoteStagingResponse | null,
});

const toMessage = (e: unknown, fallback: string) =>
	e instanceof Error && e.message ? e.message : fallback;

export const rateFor = (
	row: { compliance_rate: number; participation_rate: number },
	metric: AnalyticsMetric
): number => (metric === 'compliance' ? row.compliance_rate : row.participation_rate);

export const applyAnalyticsFilters = async (filters: AdminAnalyticsFilters): Promise<void> => {
	adminAnalyticsState.filters = filters;
	adminAnalyticsState.loading = true;
	adminAnalyticsState.error = null;
	try {
		const [overview, comparison, trends, atRisk] = await Promise.all([
			getAnalyticsOverview(filters),
			getAnalyticsComparison(filters),
			getAnalyticsTrends(filters),
			getAtRisk(filters),
		]);
		adminAnalyticsState.overview = overview;
		adminAnalyticsState.comparison = comparison.items;
		adminAnalyticsState.comparisonTotal = comparison.total;
		adminAnalyticsState.trends = trends;
		adminAnalyticsState.atRisk = atRisk;
	} catch (e: unknown) {
		adminAnalyticsState.error = toMessage(e, 'Failed to load analytics');
	} finally {
		adminAnalyticsState.loading = false;
	}
};

export const setAnalyticsMetric = (metric: AnalyticsMetric): void => {
	adminAnalyticsState.metric = metric;
};

export const refreshAtRisk = async (): Promise<void> => {
	adminAnalyticsState.actionError = null;
	try {
		adminAnalyticsState.lastRefresh = await refreshRiskScores();
		adminAnalyticsState.atRisk = await getAtRisk(adminAnalyticsState.filters);
	} catch (e: unknown) {
		adminAnalyticsState.actionError = toMessage(e, 'Failed to refresh risk scores');
		throw e;
	}
};

export const applyStagingFilters = async (
	filters: RiskStagingFilters = {}
): Promise<void> => {
	adminStagingState.loading = true;
	adminStagingState.error = null;
	try {
		const response = await listRiskStaging({ unpromoted_only: true, ...filters });
		adminStagingState.items = response.items ?? [];
		adminStagingState.total = response.total;
		adminStagingState.page = response.page;
		adminStagingState.size = response.size;
	} catch (e: unknown) {
		adminStagingState.error = toMessage(e, 'Failed to load staged risk scores');
	} finally {
		adminStagingState.loading = false;
	}
};

// Promote staged rows in scope into the live scores, then re-read both the
// staging list (promoted rows drop out of the unpromoted view) and the live
// At-Risk tab so the two never disagree.
export const promoteStaging = async (
	listFilters: RiskStagingFilters = {}
): Promise<void> => {
	adminAnalyticsState.actionError = null;
	try {
		// The POST honors the rail's program/year/course scope plus semester
		// (#279); risk level / unpromoted_only / paging stay list-side.
		adminStagingState.lastPromote = await promoteRiskStaging({
			semester: listFilters.semester,
			program_id: listFilters.program_id,
			year_level_id: listFilters.year_level_id,
			course_ids: listFilters.course_ids,
		});
		await Promise.all([
			applyStagingFilters(listFilters),
			(async () => {
				adminAnalyticsState.atRisk = await getAtRisk(adminAnalyticsState.filters);
			})(),
		]);
	} catch (e: unknown) {
		adminAnalyticsState.actionError = toMessage(e, 'Failed to promote staged risk scores');
		throw e;
	}
};

export const initAttendanceOverview = async (
	filters: AttendanceOverviewFilters = {}
): Promise<void> => {
	adminAttendanceState.loading = true;
	adminAttendanceState.error = null;
	try {
		adminAttendanceState.items = await getAttendanceOverview(filters);
	} catch (e: unknown) {
		adminAttendanceState.error = toMessage(e, 'Failed to load attendance overview');
	} finally {
		adminAttendanceState.loading = false;
	}
};

export const initAttendanceSummary = async (
	filters: AttendanceOverviewFilters = {}
): Promise<void> => {
	adminAttendanceSummaryState.loading = true;
	adminAttendanceSummaryState.error = null;
	try {
		adminAttendanceSummaryState.data = await getAttendanceSummary(filters);
	} catch (e: unknown) {
		adminAttendanceSummaryState.error = toMessage(e, 'Failed to load attendance summary');
	} finally {
		adminAttendanceSummaryState.loading = false;
	}
};

export const initAttendanceRecords = async (
	filters: AttendanceOverviewFilters = {}
): Promise<void> => {
	adminAttendanceRecordsState.loading = true;
	adminAttendanceRecordsState.error = null;
	try {
		const res = await getAttendanceRecords(filters);
		adminAttendanceRecordsState.items = res.items;
		adminAttendanceRecordsState.total = res.total;
		adminAttendanceRecordsState.page = res.page;
		adminAttendanceRecordsState.size = res.size;
	} catch (e: unknown) {
		adminAttendanceRecordsState.error = toMessage(e, 'Failed to load attendance records');
	} finally {
		adminAttendanceRecordsState.loading = false;
	}
};

export type { EnrichedComparisonRow };
