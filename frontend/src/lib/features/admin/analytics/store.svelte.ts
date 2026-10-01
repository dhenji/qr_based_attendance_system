// features/admin/analytics/store.svelte.ts
// Admin analytics state using Svelte 5 runes ($state object store).
//
// One region per tab (overview, comparison, trends, at-risk, export reads the
// same loaded rows) plus the attendance-overview table and the dashboard
// recent-scans feed. The filter rail writes `filters`; each tab loads through
// the service on Apply so tables never disagree with the server. Metric
// (compliance/participation, D36) is render-only — both rates ride every row.

import type {
	AdminAnalyticsFilters,
	AnalyticsAtRiskItemResponse,
	AnalyticsComparisonItemResponse,
	AnalyticsOverviewResponse,
	AnalyticsTrendItemResponse,
	AttendanceOverviewFilters,
	AttendanceOverviewItemResponse,
	RecentScanResponse,
	RiskRefreshResponse,
} from '$lib/shared/types';
import {
	getAnalyticsComparison,
	getAnalyticsOverview,
	getAnalyticsTrends,
	getAtRisk,
	getAttendanceOverview,
	getRecentScans,
	refreshRiskScores,
	type AnalyticsMetric,
	type EnrichedComparisonRow,
} from '$lib/features/admin/analytics/service';

export const adminAnalyticsState = $state({
	filters: {} as AdminAnalyticsFilters,
	metric: 'compliance' as AnalyticsMetric,
	overview: null as AnalyticsOverviewResponse | null,
	comparison: [] as AnalyticsComparisonItemResponse[],
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

export const adminScansState = $state({
	items: [] as RecentScanResponse[],
	loading: false,
	error: null as string | null,
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
		adminAnalyticsState.comparison = comparison;
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

export const initRecentScans = async (limit = 10): Promise<void> => {
	adminScansState.loading = true;
	adminScansState.error = null;
	try {
		adminScansState.items = await getRecentScans(limit);
	} catch (e: unknown) {
		adminScansState.error = toMessage(e, 'Failed to load recent scans');
	} finally {
		adminScansState.loading = false;
	}
};

export type { EnrichedComparisonRow };
