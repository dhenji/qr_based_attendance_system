<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonCards from '$lib/components/SkeletonCards.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import ReportBarChart from '$lib/features/report/components/ReportBarChart.svelte';
	import ReportTrendChart from '$lib/features/report/components/ReportTrendChart.svelte';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { debounce } from '$lib/shared/utils/debounce';
import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import AttendanceSnapshot from '$lib/features/admin/analytics/components/AttendanceSnapshot.svelte';
	import { page } from '$app/state';
import {
	adminAnalyticsState,
	adminStagingState,
	applyAnalyticsFilters,
	applyStagingFilters,
	promoteStaging,
	rateFor,
	refreshAtRisk,
	setAnalyticsMetric,
} from '$lib/features/admin/analytics/store.svelte';
import {
	atRiskCsv,
	comparisonCsv,
	downloadCsv,
	enrichComparison,
	fetchAnalyticsExportCsv,
	getAnalyticsComparison,
	getAnalyticsTrends,
	getAtRisk,
	getCourseOptions,
	listRiskStaging,
	overviewCsv,
	stagingCsv,
	trendsCsv,
	type AnalyticsMetric,
	type CourseOption,
} from '$lib/features/admin/analytics/service';
import { isMockMode } from '$lib/api/client';
import {
	analyticsFilterSchema,
	defaultAnalyticsRange,
} from '$lib/features/admin/analytics/schema';
import { listCourses } from '$lib/features/admin/courses/service';
import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
import { subscribeEntity } from '$lib/shared/utils/entityEvents';
import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
import type { AdminCourse, Program, YearLevel } from '$lib/shared/types';
import { formatPercentage, formatLocalDate } from '$lib/shared/utils/format';
import Pagination from '$lib/components/Pagination.svelte';
import FilterRail from '$lib/components/FilterRail.svelte';
import { type DatePresetId, type PresetId, presetDateRange } from '$lib/components/filter-rail';
import { goto } from '$app/navigation';
import { adminCourse, adminStudent } from '$lib/shared/constants/routes';

	// Analytics & Reports (wireframe 4.7, D33): one page, seven tabs —
	// Overview, Comparison, Trends, At-Risk, Staging, Attendance, Export — over
	// a shared cascading filter rail (Program → Year → Term → Courses multi →
	// Date range → Granularity). Same course appears once per cohort (D6/D34).
	// The Attendance tab is the per-course snapshot absorbed from the old
	// admin attendance page and keeps its own Course/Professor/date filters.
	// Numbers come from the live analytics backend (#136, mocks only when
	// PUBLIC_MOCK_MODE=true); the filter rail reads live programs/courses
	// endpoints for its options. Compliance (present/total) is the default
	// metric; participation ((present+late+excused)/total) is a render
	// toggle (D36).

	type Tab = 'overview' | 'comparison' | 'trends' | 'atrisk' | 'staging' | 'attendance' | 'export';
	const TABS = [
		{ id: 'overview', label: 'Overview' },
		{ id: 'comparison', label: 'Comparison' },
		{ id: 'trends', label: 'Trends' },
		{ id: 'atrisk', label: 'At-Risk' },
		{ id: 'staging', label: 'Staging' },
		{ id: 'attendance', label: 'Attendance' },
		{ id: 'export', label: 'Export' },
	] as const;

	const initialRange = defaultAnalyticsRange();

	// Deep link support (?tab=attendance): the dashboard's attendance strip
	// links straight to the snapshot tab; unknown values fall back to Overview.
	const initialTab = (): Tab => {
		const requested = page.url.searchParams.get('tab');
		return requested && TABS.some((t) => t.id === requested) ? (requested as Tab) : 'overview';
	};

	let tab = $state<Tab>(initialTab());
	let programFilter = $state('');
	let yearFilter = $state('');
	let semesterFilter = $state('');
	let selectedCourseIds = $state<number[]>([]);
	let dateFrom = $state('');
	let dateTo = $state('');
	let granularity = $state<'daily' | 'weekly' | 'monthly'>('daily');
	let riskLevel = $state<'' | 'low' | 'medium' | 'high'>('');
	let sessionTypeFilter = $state<'' | 'lecture' | 'lab'>('');
	let nameSortDir = $state<'asc' | 'desc'>('asc');
	let formError = $state<string | null>(null);
	let filterNotice = $state<string | null>(null);
	let refreshBusy = $state(false);
	// New UX state: date presets, advanced panel, pagination, chips.
	let datePreset = $state<DatePresetId>('custom');
	let advancedOpen = $state(false);
	let atRiskSearch = $state('');
	const atRiskSearchDebounced = debounce(() => void loadAtRiskPage(1));
	let stagingSearch = $state('');
	const stagingSearchDebounced = debounce(() => void loadStagingPage(1));
	let atriskPage = $state(1);
	let stagingPage = $state(1);
	let comparisonPage = $state(1);
	let trendsPage = $state(1);
	const PAGE_SIZE = 20;

	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let courseOptions = $state<AdminCourse[]>([]);
	let yearsCache = $state<Map<number, YearLevel[]>>(new Map());

	// Catalogue page size for the picker's unscoped fallback and the name-join
	// lookups; mirrors the backend's MAX_PAGE_SIZE so the list is honestly
	// bounded (with a "showing X of Y" hint) rather than silently capped.
	const COURSE_CHOICE_LIMIT = 200;
	// Scoped picker (#279): courses with at least one offering in the picked
	// Program/Year/Term. An unset program falls back to the catalogue above.
	let courseChoices = $state<CourseOption[]>([]);
	let courseChoicesTotal = $state(0);
	let courseChoicesLoading = $state(false);
	let courseLookupsTotal = $state(0);
	let courseSearch = $state('');

	const metric = $derived(adminAnalyticsState.metric);
	const overview = $derived(adminAnalyticsState.overview);

	const semesterOptions = $derived(
		yearFilter ? (yearOptions.find((y) => String(y.id) === String(yearFilter))?.terms ?? []) : []
	);

	const allYears = $derived([...yearsCache.values()].flat());

	// Picker source: scoped options when a program is picked, else the loaded
	// catalogue. `visibleChoices` adds the search narrowing for the catalogue
	// path; scoped results already arrive server-filtered by `q`.
	const pickerChoices = $derived(
		programFilter
			? courseChoices
			: courseOptions.map((c) => ({ id: c.id, code: c.courseCode, name: c.courseName }))
	);
	const pickerTotal = $derived(programFilter ? courseChoicesTotal : courseLookupsTotal);
	const visibleChoices = $derived.by(() => {
		if (programFilter) return pickerChoices;
		const needle = courseSearch.trim().toLowerCase();
		if (!needle) return pickerChoices;
		return pickerChoices.filter(
			(c) => c.code.toLowerCase().includes(needle) || c.name.toLowerCase().includes(needle)
		);
	});

	const comparison = $derived(
		enrichComparison(adminAnalyticsState.comparison, courseOptions, programOptions, [
			...yearOptions,
			...allYears,
		])
	);

	const cohortLabel = (r: (typeof comparison)[number]): string =>
		`${r.course_code} · ${r.programCode ?? `Program ${r.program_id}`} ${r.yearLevelLabel ?? `Year ${r.year_level_id}`}`;

	const bars = $derived(
		comparison.map((r) => ({
			label: cohortLabel(r),
			value: rateFor(r, metric),
			detail: `${r.total_sessions} sessions`,
		}))
	);

	const avgRate = $derived.by(() => {
		// Authoritative term-wide figure from the overview tab — the comparison
		// mean below is only a fallback when overview has not loaded.
		if (overview) return metric === 'compliance' ? overview.avg_compliance_rate : overview.avg_participation_rate;
		if (comparison.length === 0) return 0;
		return comparison.reduce((sum, r) => sum + rateFor(r, metric), 0) / comparison.length;
	});

	const trendSeries = $derived([
		{
			label: metric === 'compliance' ? 'Compliance rate' : 'Participation rate',
			color: 'var(--accent)',
			points: adminAnalyticsState.trends.map((t) => ({
				x: shortDate(t.date),
				y: rateFor(t, metric),
			})),
		},
	]);

	const atRiskSorted = $derived.by(() => {
		const rows = [...adminAnalyticsState.atRisk];
		const dir = nameSortDir === 'asc' ? 1 : -1;
		rows.sort((a, b) => a.student_name.localeCompare(b.student_name) * dir);
		return rows;
	});

	function shortDate(dateKey: string): string {
		// Daily keys (YYYY-MM-DD) render as MM-DD; weekly keys are Monday
		// dates; monthly buckets arrive as the first of the month.
		if (granularity === 'monthly') return dateKey.slice(0, 7);
		return dateKey.slice(5);
	}

	const cacheYears = async (programId: number) => {
		if (yearsCache.has(programId)) return;
		try {
			const years = await listYearLevels(programId);
			yearsCache.set(programId, years);
			yearsCache = new Map(yearsCache);
		} catch {
			// Joins fall back to ids; tables still render.
		}
	};

	const currentFilters = () => ({
		program_id: programFilter ? Number(programFilter) : undefined,
		year_level_id: yearFilter ? Number(yearFilter) : undefined,
		semester: semesterFilter.trim() || undefined,
		course_ids: selectedCourseIds,
		date_from: dateFrom.trim() || undefined,
		date_to: dateTo.trim() || undefined,
		granularity,
		risk_level: riskLevel || undefined,
		session_type: sessionTypeFilter || undefined,
		q: atRiskSearch.trim() || undefined,
	});

	const advancedActiveCount = $derived(
		[
			semesterFilter,
			riskLevel,
			selectedCourseIds.length > 0 ? 'x' : '',
		].filter((v) => String(v).trim() !== '').length
	);

	const applyPreset = (preset: PresetId) => {
		datePreset = preset;
		const range = presetDateRange(preset);
		dateFrom = range.from;
		dateTo = range.to;
	};

	const resetFilters = () => {
		courseSearchDebounced.cancel();
		programFilter = '';
		yearFilter = '';
		semesterFilter = '';
		sessionTypeFilter = '';
		riskLevel = '';
		selectedCourseIds = [];
		courseSearch = '';
		granularity = 'daily';
		datePreset = 'custom';
		dateFrom = '';
		dateTo = '';
		atriskPage = 1;
		stagingPage = 1;
		comparisonPage = 1;
		trendsPage = 1;
		void apply();
	};

	// Clear only the advanced-panel controls, then re-apply so the table never
	// disagrees with the visible filters.
	const clearAdvanced = () => {
		courseSearchDebounced.cancel();
		semesterFilter = '';
		riskLevel = '';
		clearCourseSelection();
		courseSearch = '';
		void apply();
	};

	const apply = async () => {
		atriskPage = 1;
		stagingPage = 1;
		comparisonPage = 1;
		trendsPage = 1;
		formError = null;
		const parsed = analyticsFilterSchema.safeParse({
			// Selects bind their raw option value (Svelte 5), so numeric ids
			// land in state as numbers — the schema models the string form.
			program_id: String(programFilter),
			year_level_id: String(yearFilter),
			semester: semesterFilter,
			course_ids: selectedCourseIds,
			date_from: dateFrom,
			date_to: dateTo,
			granularity,
			risk_level: riskLevel,
		});
		if (!parsed.success) {
			formError = parsed.error.issues[0]?.message ?? 'Check the filters and try again.';
			return;
		}
		await applyAnalyticsFilters(currentFilters());
		if (tab === 'staging') await applyStagingFilters(stagingFilters());
		const programIds = new Set([
			...adminAnalyticsState.comparison.map((r) => r.program_id),
			...(programFilter ? [Number(programFilter)] : []),
		]);
		await Promise.all([...programIds].map(cacheYears));
	};

	// alive-guard for the async onMount below: if the route unmounts while
	// the lookups/first page are still loading, destroy has already run and
	// the lookup subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		courseSearchDebounced.cancel();
		atRiskSearchDebounced.cancel();
		stagingSearchDebounced.cancel();
		for (const stop of autoRefreshStops) stop();
	});

	// Aggregate page (issue #221): tab focus re-applies the current filters
	// (skipped while loading); the manual Apply button stays.
	const refreshVisible = () => {
		if (adminAnalyticsState.loading || adminStagingState.loading || refreshBusy) return;
		void apply();
	};

	const reloadCourseLookups = async () => {
		try {
			const page = await listCourses({ page: 1, size: COURSE_CHOICE_LIMIT });
			courseOptions = page.items;
			courseLookupsTotal = page.total;
		} catch {
			courseOptions = [];
			courseLookupsTotal = 0;
		}
	};

	// Scoped picker options (#279). `reconcile` drops selections no longer in
	// scope, but only when the full in-scope set is present — a page truncated
	// at COURSE_CHOICE_LIMIT must never discard a valid selection.
	const loadScopedCourseChoices = async (reconcile = false) => {
		if (!programFilter) return;
		courseChoicesLoading = true;
		try {
			const { items, total } = await getCourseOptions({
				program_id: Number(programFilter),
				year_level_id: yearFilter ? Number(yearFilter) : undefined,
				semester: semesterFilter.trim() || undefined,
				q: courseSearch.trim() || undefined,
				limit: COURSE_CHOICE_LIMIT,
			});
			courseChoices = items;
			courseChoicesTotal = total;
			if (reconcile && !courseSearch.trim() && total <= items.length) {
				const available = new Set(items.map((c) => c.id));
				selectedCourseIds = selectedCourseIds.filter((id) => available.has(id));
			}
		} catch {
			// Best effort — the filterNotice covers lookup failures.
		} finally {
			courseChoicesLoading = false;
		}
	};

	const courseSearchDebounced = debounce(() => void loadScopedCourseChoices(false));

	const onCourseSearch = (value: string) => {
		courseSearch = value;
		// Catalogue search filters instantly via `visibleChoices`; a scoped
		// search round-trips, so debounce it.
		if (!programFilter) return;
		courseSearchDebounced();
	};

	const clearCourseSelection = () => {
		selectedCourseIds = [];
	};

	const reloadProgramLookups = async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
		// Year labels/terms may have changed: drop the join cache so the
		// comparison rows re-resolve, then re-warm the picked program.
		yearsCache = new Map();
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
			await cacheYears(Number(programFilter));
		}
	};

	onMount(async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
			filterNotice = 'Some filters failed to load — lists may be incomplete.';
		}
		try {
			const page = await listCourses({ page: 1, size: COURSE_CHOICE_LIMIT });
			courseOptions = page.items;
			courseLookupsTotal = page.total;
		} catch {
			courseOptions = [];
			courseLookupsTotal = 0;
			filterNotice = 'Some filters failed to load — lists may be incomplete.';
		}
		await apply();
		if (!pageAlive) return;
		autoRefreshStops.push(
			// Lookup entities reload filter-rail options only — never the
			// aggregates themselves (issue #221: no aggregate subscriptions).
			subscribeEntity('programs', () => void reloadProgramLookups()),
			subscribeEntity('courses', () => void reloadCourseLookups()),
			onFocusRevalidate(refreshVisible)
		);
	});

	const changeProgram = async () => {
		yearFilter = '';
		semesterFilter = '';
		yearOptions = [];
		courseSearch = '';
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
				filterNotice = 'Some filters failed to load — lists may be incomplete.';
			}
			await loadScopedCourseChoices(true);
		} else {
			// Back to the catalogue: every course is in scope, nothing to drop.
			courseChoices = [];
			courseChoicesTotal = 0;
		}
		await apply();
	};

	const changeYear = async () => {
		semesterFilter = '';
		courseSearch = '';
		await loadScopedCourseChoices(true);
		await apply();
	};

	const changeSemester = async () => {
		courseSearch = '';
		await loadScopedCourseChoices(true);
		await apply();
	};

	const toggleCourse = (id: number) => {
		selectedCourseIds = selectedCourseIds.includes(id)
			? selectedCourseIds.filter((v) => v !== id)
			: [...selectedCourseIds, id];
		void apply();
	};

	const setMetric = (m: AnalyticsMetric) => setAnalyticsMetric(m);

	const onRefreshRisk = async () => {
		if (refreshBusy) return;
		refreshBusy = true;
		try {
			await refreshAtRisk();
		} catch {
			// Surfaced via the store's actionError.
		} finally {
			refreshBusy = false;
		}
	};

	const baseFilters = () => currentFilters();

	const loadAtRiskPage = async (p: number) => {
		atriskPage = p;
		try {
			const r = await getAtRisk({ ...baseFilters(), q: atRiskSearch.trim() || undefined, page: p, size: PAGE_SIZE });
			adminAnalyticsState.atRisk = r.items;
			adminAnalyticsState.atRiskTotal = r.total;
		} catch (e) {
			adminAnalyticsState.error = e instanceof Error ? e.message : 'Failed to load at-risk';
		}
	};

	const loadStagingPage = async (p: number) => {
		stagingPage = p;
		try {
			const r = await listRiskStaging({ ...stagingFilters(), q: stagingSearch.trim() || undefined, page: p, size: PAGE_SIZE });
			adminStagingState.items = r.items ?? [];
			adminStagingState.total = r.total;
			adminStagingState.page = r.page;
			adminStagingState.size = r.size;
		} catch (e) {
			adminStagingState.error = e instanceof Error ? e.message : 'Failed to load staging';
		}
	};

	const loadComparisonPage = async (p: number) => {
		comparisonPage = p;
		try {
			const r = await getAnalyticsComparison({ ...baseFilters(), page: p, size: PAGE_SIZE });
			adminAnalyticsState.comparison = r.items;
			adminAnalyticsState.comparisonTotal = r.total;
		} catch (e) {
			adminAnalyticsState.error = e instanceof Error ? e.message : 'Failed to load comparison';
		}
	};

	const loadTrendsPage = async (p: number) => {
		trendsPage = p;
		try {
			const r = await getAnalyticsTrends({ ...baseFilters(), page: p, size: PAGE_SIZE });
			adminAnalyticsState.trends = r.items;
			adminAnalyticsState.trendsTotal = r.total;
		} catch (e) {
			adminAnalyticsState.error = e instanceof Error ? e.message : 'Failed to load trends';
		}
	};

	const stamp = (): string => new Date().toISOString().slice(0, 10);

	const exportOverview = () => {
		if (overview) downloadCsv(`analytics-overview-${stamp()}.csv`, overviewCsv(overview));
	};
	// Server-first comparison export (POST /admin/analytics/export): per-course
	// rows straight from the backend for the rail's filter set. Mock mode and
	// unreachable backends fall back to the client-side aggregate CSV.
	let exportNote = $state<string | null>(null);
	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);
	const exportComparison = async () => {
		const filename = `analytics-comparison-${stamp()}.csv`;
		exportNote = null;
		try {
			downloadCsv(
				filename,
				await fetchAnalyticsExportCsv({
					program_id: programFilter ? Number(programFilter) : undefined,
					year_level_id: yearFilter ? Number(yearFilter) : undefined,
					semester: semesterFilter.trim() || undefined,
					course_ids: selectedCourseIds.length > 0 ? selectedCourseIds : undefined,
					date_from: dateFrom.trim() || undefined,
					date_to: dateTo.trim() || undefined,
				})
			);
		} catch {
			exportNote = 'Server export unavailable — downloaded the on-screen rows instead.';
			downloadCsv(filename, comparisonCsv(comparison));
		}
	};
	const exportTrends = () =>
		downloadCsv(`analytics-trends-${stamp()}.csv`, trendsCsv(adminAnalyticsState.trends));
	const exportAtRisk = () =>
		downloadCsv(`analytics-atrisk-${stamp()}.csv`, atRiskCsv(adminAnalyticsState.atRisk));
	const exportStaging = () =>
		downloadCsv(`analytics-staging-${stamp()}.csv`, stagingCsv(adminStagingState.items));

	// Dry-run staging review (backend #137): staged rows under the rail's
	// program/year/semester/risk filters, unpromoted only. Promote copies the
	// in-scope rows into the live scores and refreshes both lists.
	const stagingFilters = () => ({
		program_id: programFilter ? Number(programFilter) : undefined,
		year_level_id: yearFilter ? Number(yearFilter) : undefined,
		semester: semesterFilter.trim() || undefined,
		course_ids: selectedCourseIds,
		risk_level: riskLevel || undefined,
		q: stagingSearch.trim() || undefined,
		unpromoted_only: true,
	});
	const stagingSorted = $derived.by(() => {
		const rows = [...adminStagingState.items];
		const dir = nameSortDir === 'asc' ? 1 : -1;
		rows.sort((a, b) => a.student_name.localeCompare(b.student_name) * dir);
		return rows;
	});
	let stagingBusy = $state(false);
	let promoteOpen = $state(false);

	// Lazy load: staging reads only when its tab opens (it pages separately
	// from the main datasets above).
	$effect(() => {
		if (tab === 'staging') void applyStagingFilters(stagingFilters());
	});

	const onPromote = async () => {
		if (stagingBusy) return;
		stagingBusy = true;
		promoteOpen = false;
		try {
			await promoteStaging(stagingFilters());
		} catch {
			// Surfaced via the store's actionError.
		} finally {
			stagingBusy = false;
		}
	};

	const riskBadge = (level: string): string =>
		level === 'high' ? 'badge high' : level === 'medium' ? 'badge medium' : 'badge low';

	const trendArrow = (slope: number): string => (slope < -0.05 ? '↓' : slope > 0.05 ? '↑' : '→');
</script>

<div class="page page-enter">
	<header class="header">
		<div>
			<h1>Analytics &amp; Reports</h1>
			<p class="muted">Aggregates from the live analytics backend</p>
		</div>
		{#if tab !== 'attendance'}
			<div class="header-actions" role="group" aria-label="Rate metric">
				<button
					class="btn btn-secondary"
					class:selected={metric === 'compliance'}
					onclick={() => setMetric('compliance')}
				>
					Compliance
				</button>
				<button
					class="btn btn-secondary"
					class:selected={metric === 'participation'}
					onclick={() => setMetric('participation')}
				>
					Participation
				</button>
			</div>
		{/if}
	</header>

	{#if tab !== 'attendance'}
		<section class="card filters" aria-label="Analytics filters">
			<FilterRail
				idPrefix="an"
				preset={datePreset}
				from={dateFrom}
				to={dateTo}
				advancedOpen={advancedOpen}
				advancedActiveCount={advancedActiveCount}
				onPreset={(preset) => {
					applyPreset(preset);
					void apply();
				}}
				onFromChange={(value) => {
					dateFrom = value;
					datePreset = 'custom';
					void apply();
				}}
				onToChange={(value) => {
					dateTo = value;
					datePreset = 'custom';
					void apply();
				}}
				onReset={resetFilters}
				onAdvancedToggle={() => (advancedOpen = !advancedOpen)}
				onClearAdvanced={clearAdvanced}
			>
				{#snippet scope()}
					<div class="field">
						<label class="form-label" for="an-program">Program</label>
						<select id="an-program" class="form-input" bind:value={programFilter} onchange={changeProgram}>
							<option value="">All programs</option>
							{#each programOptions as p (p.id)}
								<option value={p.id}>{p.code} — {p.name}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label class="form-label" for="an-year">Year level</label>
						<select
							id="an-year"
							class="form-input"
							bind:value={yearFilter}
							onchange={changeYear}
							disabled={!programFilter}
							title={!programFilter ? 'Pick a program first — year levels belong to a program' : undefined}
						>
							<option value="">All years</option>
							{#each yearOptions as y (y.id)}
								<option value={y.id}>{y.label}{y.terms.length === 0 ? ' (no terms)' : ''}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label class="form-label" for="an-semester">Semester</label>
						<select
							id="an-semester"
							class="form-input"
							bind:value={semesterFilter}
							onchange={changeSemester}
							disabled={!yearFilter || semesterOptions.length === 0}
							title={!yearFilter
								? "Pick a year level first — semesters are the year level's terms"
								: semesterOptions.length === 0
									? 'This year level has no terms configured'
									: undefined}
						>
							<option value="">All semesters</option>
							{#each semesterOptions as t (t.code)}
								<option value={t.code}>{t.label}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label class="form-label" for="an-session-type">Session type</label>
						<select id="an-session-type" class="form-input" bind:value={sessionTypeFilter} onchange={apply}>
							<option value="">All session types</option>
							<option value="lecture">Lecture (LEC)</option>
							<option value="lab">Laboratory (LAB)</option>
						</select>
					</div>
					{#if tab === 'trends'}
						<div class="field">
							<label class="form-label" for="an-granularity">Granularity</label>
							<select id="an-granularity" class="form-input" bind:value={granularity} onchange={apply}>
								<option value="daily">Daily</option>
								<option value="weekly">Weekly</option>
								<option value="monthly">Monthly</option>
							</select>
						</div>
					{/if}
				{/snippet}

				{#snippet advanced()}
					<fieldset class="courses">
						<legend>Courses (multi)</legend>
						<div class="course-picker">
							<input
								class="form-input"
								type="search"
								placeholder={programFilter ? 'Search courses in scope' : 'Search courses'}
								aria-label="Search courses"
								value={courseSearch}
								oninput={(e) => onCourseSearch((e.currentTarget as HTMLInputElement).value)}
							/>
							<span class="muted small">
								{selectedCourseIds.length} selected{#if selectedCourseIds.length > 0}
									<button type="button" class="link-btn" onclick={clearCourseSelection}>Clear</button>{/if}
							</span>
						</div>
						<div class="course-grid">
							{#if courseChoicesLoading && pickerChoices.length === 0}
								<span class="muted">Loading courses…</span>
							{:else if pickerChoices.length === 0}
								<span class="muted">
									{programFilter
										? 'No courses are offered in the selected program/year/term.'
										: 'No courses loaded.'}
								</span>
							{:else}
								{#each visibleChoices as c (c.id)}
									<label class="check">
										<input
											type="checkbox"
											checked={selectedCourseIds.includes(c.id)}
											onchange={() => toggleCourse(c.id)}
										/>
										{c.code}
									</label>
								{:else}
									<span class="muted">No courses match “{courseSearch}”.</span>
								{/each}
								{#if pickerChoices.length < pickerTotal}
									<span class="muted small">
										Showing {pickerChoices.length} of {pickerTotal} — search to narrow.
									</span>
								{/if}
							{/if}
						</div>
					</fieldset>
					<div class="field">
						<label class="form-label" for="an-risk">Risk level</label>
						<select id="an-risk" class="form-input" bind:value={riskLevel} onchange={apply}>
							<option value="">All risk levels</option>
							<option value="high">High</option>
							<option value="medium">Medium</option>
							<option value="low">Low</option>
						</select>
					</div>
				{/snippet}
			</FilterRail>

			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			{#if filterNotice}
				<p class="muted" role="status">{filterNotice}</p>
			{/if}
		</section>
	{/if}

	<nav class="tabs" aria-label="Analytics sections">
		{#each TABS as t (t.id)}
			<button class:active={tab === t.id} onclick={() => (tab = t.id)}>{t.label}</button>
		{/each}
	</nav>

	{#if tab === 'attendance'}
		<AttendanceSnapshot />
	{:else if adminAnalyticsState.loading && adminAnalyticsState.overview === null}
		<SkeletonCards count={4} label="Loading analytics…" />
		<SkeletonTable rows={4} cols={6} />
	{:else if adminAnalyticsState.error}
		<section class="card">
			<p class="error">Could not load analytics: {adminAnalyticsState.error}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void apply()}>Try again</button>
		</section>
	{:else if tab === 'overview' && overview}
		<section class="kpis" aria-busy={adminAnalyticsState.loading}>
			<div class="kpi"><span class="kpi-value">{overview.total_students}</span><span class="kpi-label">Students</span></div>
			<div class="kpi"><span class="kpi-value">{overview.total_sessions}</span><span class="kpi-label">Sessions</span></div>
			{#if sessionTypeFilter !== 'lab'}
				<div class="kpi"><span class="kpi-value">{overview.lecture_sessions}</span><span class="kpi-label">Lecture (LEC)</span></div>
			{/if}
			{#if sessionTypeFilter !== 'lecture'}
				<div class="kpi"><span class="kpi-value">{overview.lab_sessions}</span><span class="kpi-label">Laboratory (LAB)</span></div>
			{/if}
			<!-- Both rates arrive as 0-1 fractions (backend `_rates` does
			     round(present/enrolled, 4)), so they need scaling before
			     formatting. The CSV export in features/admin/analytics/service.ts
			     already does this, which is why the omission here went unnoticed:
			     85% was rendering as "1%". -->
			<div class="kpi"><span class="kpi-value">{formatPercentage(overview.avg_compliance_rate * 100)}</span><span class="kpi-label">Avg compliance</span></div>
			<div class="kpi"><span class="kpi-value">{formatPercentage(overview.avg_participation_rate * 100)}</span><span class="kpi-label">Avg participation</span></div>
		</section>
	{:else if tab === 'comparison'}
		<section class="card" aria-busy={adminAnalyticsState.loading}>
			<h2 class="card-title">Course Comparison</h2>
			<p class="muted">Same course shown once per cohort · {metric} rate</p>
			{#if adminAnalyticsState.comparisonTotal > comparison.length}
				<p class="muted">
					Showing {comparison.length} of {adminAnalyticsState.comparisonTotal} cohorts — narrow the
					filters to see the rest.
				</p>
			{/if}
			<ReportBarChart
				title="Course comparison"
				description="Per-cohort rate bars for the current filter set."
				bars={bars}
				average={avgRate}
				emptyMessage="No comparison data for the selected filters."
			/>
			{#if comparison.length > 0}
				<div class="table-wrap">
					<table>
						<thead>
							<tr><th scope="col">Course</th><th scope="col">Cohort</th><th scope="col">Sessions</th><th scope="col">Compliance</th><th scope="col">Participation</th></tr>
						</thead>
						<tbody>
							{#each comparison as r (`${r.course_id}-${r.program_id}-${r.year_level_id}`)}
								<tr>
									<td class="strong">
										<button class="link" type="button" onclick={() => void goto(adminCourse(r.course_id))}>{r.course_code}</button>
										{r.courseName ? ` — ${r.courseName}` : ''}
									</td>
									<td>{[r.programCode ?? `Program ${r.program_id}`, r.yearLevelLabel ?? `Year ${r.year_level_id}`].join(' · ')}</td>
									<td>{r.total_sessions}</td>
									<td>{formatPercentage(r.compliance_rate * 100)}</td>
									<td>{formatPercentage(r.participation_rate * 100)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if adminAnalyticsState.comparisonTotal > PAGE_SIZE}
					<Pagination page={comparisonPage} totalPages={Math.max(1, Math.ceil(adminAnalyticsState.comparisonTotal / PAGE_SIZE))} onPageChange={(p) => void loadComparisonPage(p)} />
				{/if}
			{/if}
		</section>
	{:else if tab === 'trends'}
		<section class="card" aria-busy={adminAnalyticsState.loading}>
			<h2 class="card-title">Trends ({granularity})</h2>
			<p class="muted">{metric} rate over the selected range</p>
			<ReportTrendChart
				title="Attendance trends"
				description="Aggregate rate per period for the current filter set."
				series={trendSeries}
				emptyMessage="No trend data for the selected filters."
			/>
			{#if adminAnalyticsState.trends.length > 0}
				<div class="table-wrap">
					<table>
						<thead>
							<tr><th scope="col">Period</th><th scope="col">Sessions</th><th scope="col">Compliance</th><th scope="col">Participation</th></tr>
						</thead>
						<tbody>
							{#each adminAnalyticsState.trends as t (t.date)}
								<tr>
									<td class="strong">{t.date}</td>
									<td>{t.total_sessions}</td>
									<td>{formatPercentage(t.compliance_rate * 100)}</td>
									<td>{formatPercentage(t.participation_rate * 100)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if adminAnalyticsState.trendsTotal > PAGE_SIZE}
					<Pagination page={trendsPage} totalPages={Math.max(1, Math.ceil(adminAnalyticsState.trendsTotal / PAGE_SIZE))} onPageChange={(p) => void loadTrendsPage(p)} />
				{/if}
			{/if}
		</section>
	{:else if tab === 'atrisk'}
		<section class="card" aria-busy={adminAnalyticsState.loading}>
			<div class="row-head">
				<div>
					<h2 class="card-title">At-Risk Students</h2>
					<p class="muted">Heuristic thresholds (D35) · batch runs daily, manual refresh is admin-only</p>
				</div>
				<button class="btn btn-primary" disabled={refreshBusy} onclick={onRefreshRisk}>
					{refreshBusy ? 'Refreshing…' : 'Refresh Risk Scores'}
				</button>
			</div>
			{#if adminAnalyticsState.actionError}
				<p class="error" role="alert">{adminAnalyticsState.actionError}</p>
			{/if}
			{#if adminAnalyticsState.lastRefresh}
				<p class="muted" role="status">
					Last refresh: processed {adminAnalyticsState.lastRefresh.processed} ·
					high {adminAnalyticsState.lastRefresh.high} · medium {adminAnalyticsState.lastRefresh.medium} ·
					low {adminAnalyticsState.lastRefresh.low} ({adminAnalyticsState.lastRefresh.duration_ms} ms)
				</p>
			{/if}
			<div class="filters inline">
				<input
					class="input"
					type="search"
					aria-label="Search at-risk students"
					placeholder="Search by name"
					bind:value={atRiskSearch}
					oninput={() => atRiskSearchDebounced()}
				/>
				<select class="input" aria-label="Risk level filter" bind:value={riskLevel} onchange={apply}>
					<option value="">All levels</option>
					<option value="high">High</option>
					<option value="medium">Medium</option>
					<option value="low">Low</option>
				</select>
			</div>
			{#if atRiskSorted.length === 0}
				<EmptyState
					icon="chart"
					title="No at-risk students match these filters"
					hint="Adjust the filters or run a risk batch to populate scores."
				/>
			{:else}
				<div class="table-wrap">
					<table>
						<thead>
							<tr>
								<th scope="col" aria-sort={nameSortDir === 'asc' ? 'ascending' : 'descending'}>
									<button
										class="th-btn"
										type="button"
										onclick={() => (nameSortDir = nameSortDir === 'asc' ? 'desc' : 'asc')}
										aria-label={`Sort by name ${nameSortDir === 'asc' ? 'descending' : 'ascending'}`}
									>
										Name<span aria-hidden="true">{nameSortDir === 'asc' ? ' ▲' : ' ▼'}</span>
									</button>
								</th>
								<th scope="col">Course</th>
								<th scope="col">Absence</th>
								<th scope="col">Streak</th>
								<th scope="col">Trend</th>
								<th scope="col">Risk</th>
							</tr>
						</thead>
						<tbody>
							{#each atRiskSorted as r (r.student_id)}
								<tr>
									<td class="strong">
										<button class="link" type="button" onclick={() => void goto(adminStudent(Number(r.student_id)))}>{r.student_name}</button>
										<div class="muted small">{r.student_id} · {r.program} {r.year_level}</div>
									</td>
									<td>{r.course_code}</td>
									<td>{formatPercentage(r.absence_rate * 100)}</td>
									<td>{r.max_streak}</td>
									<td>{trendArrow(r.trend_slope)}</td>
									<td><span class={riskBadge(r.risk_level)}>{r.risk_level}</span></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if adminAnalyticsState.atRiskTotal > PAGE_SIZE}
					<Pagination page={atriskPage} totalPages={Math.max(1, Math.ceil(adminAnalyticsState.atRiskTotal / PAGE_SIZE))} onPageChange={(p) => void loadAtRiskPage(p)} />
				{/if}
			{/if}
		</section>
	{:else if tab === 'staging'}
		<section class="card">
			<div class="row-head">
				<div>
					<h2 class="card-title">Staging Review</h2>
					<p class="muted">Dry-run batch output (D35) · promoting copies unpromoted rows into the live At-Risk scores</p>
				</div>
				<button class="btn btn-primary" aria-busy={stagingBusy} disabled={stagingBusy || stagingSorted.length === 0} onclick={() => (promoteOpen = true)}>
					{stagingBusy ? 'Promoting…' : 'Promote to Live'}
				</button>
			</div>
			{#if adminAnalyticsState.actionError}
				<p class="error" role="alert">{adminAnalyticsState.actionError}</p>
			{/if}
			{#if adminStagingState.lastPromote}
				<p class="muted" role="status">
					Last promote: {adminStagingState.lastPromote.promoted} promoted ·
					{adminStagingState.lastPromote.skipped} skipped ({adminStagingState.lastPromote.duration_ms} ms)
				</p>
			{/if}
			{#if promoteOpen}
				<div
					class="confirm"
					role="alertdialog"
					aria-label="Confirm promote"
					tabindex="-1"
					use:trapFocus={{ onEscape: () => (stagingBusy ? undefined : (promoteOpen = false)) }}
				>
					<p class="strong">Promote {stagingSorted.length} staged row{stagingSorted.length === 1 ? '' : 's'}?</p>
					<p class="muted small">
						Promote acts on every unpromoted row in the current scope{#if semesterFilter.trim()}{` (${semesterFilter.trim()})`}{:else} (all semesters){/if} — program, year,
						and course narrow the promoted set; risk level narrows this review list only. Promoted rows leave the list and appear in At-Risk.
					</p>
					<div class="confirm-actions">
						<button class="btn btn-secondary" onclick={() => (promoteOpen = false)}>Cancel</button>
						<button class="btn btn-primary" disabled={stagingBusy} onclick={onPromote}>Confirm Promote</button>
					</div>
				</div>
			{/if}
			<div class="filters inline">
				<input
					class="input"
					type="search"
					aria-label="Search staged students"
					placeholder="Search by name"
					bind:value={stagingSearch}
					oninput={() => stagingSearchDebounced()}
				/>
				<select class="input" aria-label="Risk level filter" bind:value={riskLevel} onchange={apply}>
					<option value="">All levels</option>
					<option value="high">High</option>
					<option value="medium">Medium</option>
					<option value="low">Low</option>
				</select>
			</div>
			{#if adminStagingState.loading && adminStagingState.items.length === 0}
				<SkeletonTable bare rows={4} cols={6} label="Loading staged scores…" />
			{:else if adminStagingState.error}
				<p class="error" role="alert">{adminStagingState.error}</p>
			{:else if stagingSorted.length === 0}
				{#if isMockMode()}
					<EmptyState
						icon="chart"
						title="Staging review needs a backend dry-run batch"
						hint="Unavailable in mock mode."
					/>
				{:else}
					<EmptyState
						icon="chart"
						title="No staged scores match these filters"
						hint="Run a dry-run batch, then review here before promoting."
					/>
				{/if}
			{:else}
				<div class="table-wrap">
					<table>
						<thead>
							<tr>
								<th scope="col" aria-sort={nameSortDir === 'asc' ? 'ascending' : 'descending'}>
									<button
										class="th-btn"
										type="button"
										onclick={() => (nameSortDir = nameSortDir === 'asc' ? 'desc' : 'asc')}
										aria-label={`Sort by name ${nameSortDir === 'asc' ? 'descending' : 'ascending'}`}
									>
										Name<span aria-hidden="true">{nameSortDir === 'asc' ? ' ▲' : ' ▼'}</span>
									</button>
								</th>
								<th scope="col">Course</th>
								<th scope="col">Absence</th>
								<th scope="col">Streak</th>
								<th scope="col">Trend</th>
								<th scope="col">Risk</th>
								<th scope="col">Computed</th>
							</tr>
						</thead>
						<tbody>
							{#each stagingSorted as r (r.student_id)}
								<tr>
									<td class="strong">{r.student_name}<div class="muted small">#{r.student_id} · {r.program} {r.year_level}</div></td>
									<td>{r.course_code}<div class="muted small">{r.course_name}</div></td>
									<td>{formatPercentage(r.absence_rate * 100)}</td>
									<td>{r.max_streak}</td>
									<td>{trendArrow(r.trend_slope)}</td>
									<td><span class={riskBadge(r.risk_level)}>{r.risk_level}</span></td>
									<td class="muted small">{formatLocalDate(r.computed_at)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if adminStagingState.total > PAGE_SIZE}
					<Pagination page={stagingPage} totalPages={Math.max(1, Math.ceil(adminStagingState.total / PAGE_SIZE))} onPageChange={(p) => void loadStagingPage(p)} />
				{/if}
			{/if}
		</section>
	{:else if tab === 'export'}
		<section class="card">
			<h2 class="card-title">Export</h2>
			<p class="muted">CSV downloads of the current filter set — one file per dataset.</p>
			<div class="export-list">
				<div><div><div class="strong">Overview KPIs</div><div class="muted small">Totals + average rates</div></div><button class="btn btn-secondary" onclick={() => (pendingExport = { run: exportOverview, details: [{ label: 'Dataset', value: 'Overview KPIs' }, { label: 'Format', value: 'CSV' }] })} disabled={!overview}>Download CSV</button></div>
				<div><div><div class="strong">Course comparison</div><div class="muted small">{comparison.length} cohort rows</div></div><button class="btn btn-secondary" onclick={() => (pendingExport = { run: exportComparison, details: [{ label: 'Dataset', value: 'Course comparison' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(comparison.length) }] })}>Download CSV</button></div>
				<div><div><div class="strong">Trends</div><div class="muted small">{adminAnalyticsState.trends.length} periods</div></div><button class="btn btn-secondary" onclick={() => (pendingExport = { run: exportTrends, details: [{ label: 'Dataset', value: 'Trends' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminAnalyticsState.trends.length) }] })}>Download CSV</button></div>
				<div><div><div class="strong">At-risk students</div><div class="muted small">{adminAnalyticsState.atRisk.length} rows</div></div><button class="btn btn-secondary" onclick={() => (pendingExport = { run: exportAtRisk, details: [{ label: 'Dataset', value: 'At-risk students' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminAnalyticsState.atRisk.length) }] })}>Download CSV</button></div>
				<div><div><div class="strong">Staging review</div><div class="muted small">{adminStagingState.items.length} rows</div></div><button class="btn btn-secondary" onclick={() => (pendingExport = { run: exportStaging, details: [{ label: 'Dataset', value: 'Staging review' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminStagingState.items.length) }] })}>Download CSV</button></div>
			</div>
			{#if exportNote}
				<p class="muted" role="status">{exportNote}</p>
			{/if}
		</section>
	{/if}
	{#if pendingExport}
		<ConfirmExportDialog
			title={pendingExport.title}
			message={pendingExport.message}
			confirmLabel={pendingExport.confirmLabel}
			busyLabel={pendingExport.busyLabel}
			details={pendingExport.details}
			onconfirm={pendingExport.run}
			onclose={() => (pendingExport = null)}
		/>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1400px;
		margin: 0 auto;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.muted.small {
		font-size: 0.75rem;
	}

	.header-actions {
		display: flex;
		gap: 0.5rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
		transition: box-shadow 0.15s ease;
	}
	.card:hover {
		box-shadow: 0 6px 24px rgba(15, 23, 42, 0.1);
	}

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.card .muted {
		margin-bottom: 1rem;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
	}

	.filters.inline {
		margin-bottom: 1rem;
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.courses {
		display: flex;
		gap: 0.75rem 1.25rem;
		flex-wrap: wrap;
		align-items: center;
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.625rem 0.875rem;
		margin: 0;
		flex-basis: 100%;
	}

	.courses legend {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
		padding: 0 0.375rem;
	}

	.check {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.course-picker {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		flex-basis: 100%;
	}

	.course-picker .form-input {
		flex: 1 1 16rem;
	}

	.link-btn {
		background: none;
		border: none;
		padding: 0;
		margin-left: 0.375rem;
		font: inherit;
		color: var(--brand);
		cursor: pointer;
		text-decoration: underline;
	}

	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid var(--border);
		flex-wrap: wrap;
	}

	.tabs button {
		background: none;
		border: none;
		padding: 0.625rem 1rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--text-muted);
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -2px;
	}

	.tabs button:hover {
		color: var(--text-strong);
	}

	.tabs button.active {
		color: var(--brand);
		border-bottom-color: var(--brand);
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		box-shadow: var(--shadow-sm);
	}

	.kpi-value {
		font-size: 1.75rem;
		font-weight: 800;
		color: var(--text);
	}

	.kpi-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.row-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.625rem 0.5rem;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.strong {
		font-weight: 700;
	}

	td .strong {
		font-size: 0.875rem;
	}

	.th-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.th-btn:hover {
		color: var(--text-strong);
	}

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
		text-transform: capitalize;
	}

	.badge.medium {
		color: var(--warning-text);
		background: var(--warning-bg);
	}

	.badge.high {
		color: var(--danger-strong);
		background: var(--danger-bg);
	}

	.export-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.export-list > div {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		border: 1px solid var(--divider);
		border-radius: 8px;
		padding: 0.75rem 1rem;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
		flex-basis: 100%;
	}

	.confirm {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		margin: 1rem 0;
		background: var(--bg-muted, transparent);
	}

	.confirm-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	/* Intentional lift variant; the shared .btn supplies the colors, so keep
	   the transform/box-shadow in the transition. */
	.btn {
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			transform 0.18s ease,
			box-shadow 0.18s ease;
	}

	.btn:hover:not(:disabled) {
		transform: translateY(-1px);
		box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
	}
	.btn:active:not(:disabled) {
		transform: translateY(0);
		box-shadow: none;
	}

	.btn-secondary.selected {
		border-color: var(--brand);
		background: var(--brand);
		color: var(--on-brand);
	}

	/* The generic secondary hover carries :not(:disabled) (specificity 0,3,0),
	   which outranks the selected state (0,2,0) — without this rule, hovering a
	   selected metric button repainted it --divider (near-white) under the
	   white text. Selected buttons hover into the darker brand shade instead. */
	.btn-secondary.selected:hover:not(:disabled) {
		background: var(--brand-hover);
		border-color: var(--brand-hover);
	}

	.table-wrap {
		overflow-x: auto;
		margin-top: 1rem;
	}

	@media (max-width: 900px) {
		.kpis {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-weight: 700;
		cursor: pointer;
		text-decoration: none;
	}
	.link:hover { text-decoration: underline; }

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.4375rem;
		min-width: 0;
	}
	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
	}

	.course-grid {
		display: flex;
		gap: 0.5rem 1rem;
		flex-wrap: wrap;
		align-items: center;
		margin-top: 0.5rem;
	}
	.chips {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 0.75rem;
		align-items: flex-start;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.625rem;
		border-radius: 999px;
		background: var(--divider);
		color: var(--text-secondary);
		font-size: 0.8125rem;
		font-weight: 600;
	}
	.chip-x {
		background: none;
		border: none;
		padding: 0;
		color: var(--text-muted);
		cursor: pointer;
		font: inherit;
		line-height: 1;
	}
	.chip-x:hover { color: var(--danger); }

	@media (max-width: 900px) {
		.kpis {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
