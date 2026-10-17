<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import ReportBarChart from '$lib/features/report/components/ReportBarChart.svelte';
	import ReportTrendChart from '$lib/features/report/components/ReportTrendChart.svelte';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
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
	getCourseOptions,
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
	let dateFrom = $state(initialRange.from);
	let dateTo = $state(initialRange.to);
	let granularity = $state<'daily' | 'weekly' | 'monthly'>('daily');
	let riskLevel = $state<'' | 'low' | 'medium' | 'high'>('');
	let nameSortDir = $state<'asc' | 'desc'>('asc');
	let formError = $state<string | null>(null);
	let filterNotice = $state<string | null>(null);
	let refreshBusy = $state(false);

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
	});

	const apply = async () => {
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
		if (courseSearchTimer) clearTimeout(courseSearchTimer);
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

	let courseSearchTimer: ReturnType<typeof setTimeout> | null = null;

	const onCourseSearch = (value: string) => {
		courseSearch = value;
		// Catalogue search filters instantly via `visibleChoices`; a scoped
		// search round-trips, so debounce it.
		if (!programFilter) return;
		if (courseSearchTimer) clearTimeout(courseSearchTimer);
		courseSearchTimer = setTimeout(() => void loadScopedCourseChoices(false), 250);
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

	const stamp = (): string => new Date().toISOString().slice(0, 10);

	const exportOverview = () => {
		if (overview) downloadCsv(`analytics-overview-${stamp()}.csv`, overviewCsv(overview));
	};
	// Server-first comparison export (POST /admin/analytics/export): per-course
	// rows straight from the backend for the rail's filter set. Mock mode and
	// unreachable backends fall back to the client-side aggregate CSV.
	let exportNote = $state<string | null>(null);
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

<div class="page">
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
			<select class="input" aria-label="Program filter" bind:value={programFilter} onchange={changeProgram}>
				<option value="">All programs</option>
				{#each programOptions as p (p.id)}
					<option value={p.id}>{p.code} — {p.name}</option>
				{/each}
			</select>
			<select
				class="input"
				aria-label="Year level filter"
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
			<select
				class="input"
				aria-label="Semester filter"
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
			<select class="input" aria-label="Granularity" bind:value={granularity}>
				<option value="daily">Daily</option>
				<option value="weekly">Weekly</option>
				<option value="monthly">Monthly</option>
			</select>
			<input class="input" type="date" aria-label="From date" bind:value={dateFrom} />
			<input class="input" type="date" aria-label="To date" bind:value={dateTo} />
			<button class="btn btn-primary" data-testid="apply" onclick={apply}>Apply Filters</button>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
		{/if}
		{#if filterNotice}
			<p class="muted" role="status">{filterNotice}</p>
		{/if}
		<fieldset class="courses">
			<legend>Courses (multi)</legend>
			<div class="course-picker">
				<input
					class="input"
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
		</fieldset>
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
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminAnalyticsState.error}
		<section class="card"><p class="error">Could not load analytics: {adminAnalyticsState.error}</p></section>
	{:else if tab === 'overview' && overview}
		<section class="kpis" aria-busy={adminAnalyticsState.loading}>
			<div class="kpi"><span class="kpi-value">{overview.total_students}</span><span class="kpi-label">Students</span></div>
			<div class="kpi"><span class="kpi-value">{overview.total_sessions}</span><span class="kpi-label">Sessions</span></div>
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
							<tr><th>Course</th><th>Cohort</th><th>Sessions</th><th>Compliance</th><th>Participation</th></tr>
						</thead>
						<tbody>
							{#each comparison as r (`${r.course_id}-${r.program_id}-${r.year_level_id}`)}
								<tr>
									<td class="strong">{r.course_code}{r.courseName ? ` — ${r.courseName}` : ''}</td>
									<td>{[r.programCode ?? `Program ${r.program_id}`, r.yearLevelLabel ?? `Year ${r.year_level_id}`].join(' · ')}</td>
									<td>{r.total_sessions}</td>
									<td>{formatPercentage(r.compliance_rate * 100)}</td>
									<td>{formatPercentage(r.participation_rate * 100)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
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
							<tr><th>Period</th><th>Sessions</th><th>Compliance</th><th>Participation</th></tr>
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
				<select class="input" aria-label="Risk level filter" bind:value={riskLevel} onchange={apply}>
					<option value="">All levels</option>
					<option value="high">High</option>
					<option value="medium">Medium</option>
					<option value="low">Low</option>
				</select>
			</div>
			{#if atRiskSorted.length === 0}
				<p class="empty">No at-risk students match these filters.</p>
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
									<td class="strong">{r.student_name}<div class="muted small">{r.student_id} · {r.program} {r.year_level}</div></td>
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
			{/if}
		</section>
	{:else if tab === 'staging'}
		<section class="card">
			<div class="row-head">
				<div>
					<h2 class="card-title">Staging Review</h2>
					<p class="muted">Dry-run batch output (D35) · promoting copies unpromoted rows into the live At-Risk scores</p>
				</div>
				<button class="btn btn-primary" disabled={stagingBusy || stagingSorted.length === 0} onclick={() => (promoteOpen = true)}>
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
				<select class="input" aria-label="Risk level filter" bind:value={riskLevel} onchange={apply}>
					<option value="">All levels</option>
					<option value="high">High</option>
					<option value="medium">Medium</option>
					<option value="low">Low</option>
				</select>
			</div>
			{#if adminStagingState.loading && adminStagingState.items.length === 0}
				<p class="muted">Loading staged scores…</p>
			{:else if adminStagingState.error}
				<p class="error" role="alert">{adminStagingState.error}</p>
			{:else if stagingSorted.length === 0}
				{#if isMockMode()}
					<p class="empty">Staging review needs a backend dry-run batch — unavailable in mock mode.</p>
				{:else}
					<p class="empty">No staged scores match these filters. Run a dry-run batch, then review here before promoting.</p>
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
			{/if}
		</section>
	{:else if tab === 'export'}
		<section class="card">
			<h2 class="card-title">Export</h2>
			<p class="muted">CSV downloads of the current filter set — one file per dataset.</p>
			<div class="export-list">
				<div><div><div class="strong">Overview KPIs</div><div class="muted small">Totals + average rates</div></div><button class="btn btn-secondary" onclick={exportOverview} disabled={!overview}>Download CSV</button></div>
				<div><div><div class="strong">Course comparison</div><div class="muted small">{comparison.length} cohort rows</div></div><button class="btn btn-secondary" onclick={exportComparison}>Download CSV</button></div>
				<div><div><div class="strong">Trends</div><div class="muted small">{adminAnalyticsState.trends.length} periods</div></div><button class="btn btn-secondary" onclick={exportTrends}>Download CSV</button></div>
				<div><div><div class="strong">At-risk students</div><div class="muted small">{adminAnalyticsState.atRisk.length} rows</div></div><button class="btn btn-secondary" onclick={exportAtRisk}>Download CSV</button></div>
				<div><div><div class="strong">Staging review</div><div class="muted small">{adminStagingState.items.length} rows</div></div><button class="btn btn-secondary" onclick={exportStaging}>Download CSV</button></div>
			</div>
			{#if exportNote}
				<p class="muted" role="status">{exportNote}</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		font-family: system-ui, sans-serif;
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
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
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

	.course-picker .input {
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
		border-radius: 8px;
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

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
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

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
