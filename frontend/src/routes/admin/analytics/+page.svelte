<script lang="ts">
	import { onMount } from 'svelte';
	import ReportBarChart from '$lib/features/report/components/ReportBarChart.svelte';
	import ReportTrendChart from '$lib/features/report/components/ReportTrendChart.svelte';
	import {
		adminAnalyticsState,
		applyAnalyticsFilters,
		rateFor,
		refreshAtRisk,
		setAnalyticsMetric,
	} from '$lib/features/admin/analytics/store.svelte';
	import {
		atRiskCsv,
		comparisonCsv,
		downloadCsv,
		enrichComparison,
		overviewCsv,
		trendsCsv,
		type AnalyticsMetric,
	} from '$lib/features/admin/analytics/service';
	import {
		analyticsFilterSchema,
		defaultAnalyticsRange,
	} from '$lib/features/admin/analytics/schema';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import type { AdminCourse, Program, YearLevel } from '$lib/shared/types';
	import { formatPercentage } from '$lib/shared/utils/format';

	// Analytics & Reports (wireframe 4.7, D33): one page, five tabs —
	// Overview, Comparison, Trends, At-Risk, Export — over a shared cascading
	// filter rail (Program → Year → Term → Courses multi → Date range →
	// Granularity). Same course appears once per cohort (D6/D34). The backend
	// for these endpoints does not exist yet, so numbers come from
	// contract-shaped mocks (deterministic and mutually consistent); the
	// filter rail reads live programs/courses endpoints for its options.
	// Compliance (present/total) is the default metric; participation
	// ((present+late+excused)/total) is a render toggle (D36).

	type Tab = 'overview' | 'comparison' | 'trends' | 'atrisk' | 'export';
	const TABS = [
		{ id: 'overview', label: 'Overview' },
		{ id: 'comparison', label: 'Comparison' },
		{ id: 'trends', label: 'Trends' },
		{ id: 'atrisk', label: 'At-Risk' },
		{ id: 'export', label: 'Export' },
	] as const;

	const initialRange = defaultAnalyticsRange();

	let tab = $state<Tab>('overview');
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
	let refreshBusy = $state(false);

	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let courseOptions = $state<AdminCourse[]>([]);
	let yearsCache = $state<Map<number, YearLevel[]>>(new Map());

	const metric = $derived(adminAnalyticsState.metric);
	const overview = $derived(adminAnalyticsState.overview);

	const semesterOptions = $derived(
		yearFilter ? (yearOptions.find((y) => String(y.id) === yearFilter)?.terms ?? []) : []
	);

	const allYears = $derived([...yearsCache.values()].flat());

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

	const avgRate = $derived(
		comparison.length === 0
			? 0
			: comparison.reduce((sum, r) => sum + rateFor(r, metric), 0) / comparison.length
	);

	const trendSeries = $derived([
		{
			label: metric === 'compliance' ? 'Compliance rate' : 'Participation rate',
			color: '#2563eb',
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
			program_id: programFilter,
			year_level_id: yearFilter,
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
		const programIds = new Set([
			...adminAnalyticsState.comparison.map((r) => r.program_id),
			...(programFilter ? [Number(programFilter)] : []),
		]);
		await Promise.all([...programIds].map(cacheYears));
	};

	onMount(async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
		}
		await apply();
	});

	const changeProgram = async () => {
		yearFilter = '';
		semesterFilter = '';
		yearOptions = [];
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
		}
		await apply();
	};

	const changeYear = async () => {
		semesterFilter = '';
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
	const exportComparison = () => downloadCsv(`analytics-comparison-${stamp()}.csv`, comparisonCsv(comparison));
	const exportTrends = () =>
		downloadCsv(`analytics-trends-${stamp()}.csv`, trendsCsv(adminAnalyticsState.trends));
	const exportAtRisk = () =>
		downloadCsv(`analytics-atrisk-${stamp()}.csv`, atRiskCsv(adminAnalyticsState.atRisk));

	const riskBadge = (level: string): string =>
		level === 'high' ? 'badge high' : level === 'medium' ? 'badge medium' : 'badge low';

	const trendArrow = (slope: number): string => (slope < -0.05 ? '↓' : slope > 0.05 ? '↑' : '→');
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Analytics &amp; Reports</h1>
			<p class="muted">Aggregates served by contract mocks until the analytics backend lands (Phase 7)</p>
		</div>
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
	</header>

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
				<option value={y.id}>{y.label}</option>
			{/each}
		</select>
		{#if semesterOptions.length > 0}
			<select class="input" aria-label="Semester filter" bind:value={semesterFilter}>
				<option value="">All semesters</option>
				{#each semesterOptions as t (t.code)}
					<option value={t.code}>{t.label}</option>
				{/each}
			</select>
		{:else}
			<input class="input" placeholder="Semester (e.g. 1st Sem)" aria-label="Semester filter" bind:value={semesterFilter} />
		{/if}
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
		<fieldset class="courses">
			<legend>Courses (multi)</legend>
			{#if courseOptions.length === 0}
				<span class="muted">No courses loaded.</span>
			{:else}
				{#each courseOptions as c (c.id)}
					<label class="check">
						<input
							type="checkbox"
							checked={selectedCourseIds.includes(c.id)}
							onchange={() => toggleCourse(c.id)}
						/>
						{c.courseCode}
					</label>
				{/each}
			{/if}
		</fieldset>
	</section>

	<nav class="tabs" aria-label="Analytics sections">
		{#each TABS as t (t.id)}
			<button class:active={tab === t.id} onclick={() => (tab = t.id)}>{t.label}</button>
		{/each}
	</nav>

	{#if adminAnalyticsState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminAnalyticsState.error}
		<section class="card"><p class="error">Could not load analytics: {adminAnalyticsState.error}</p></section>
	{:else if tab === 'overview' && overview}
		<section class="kpis">
			<div class="kpi"><span class="kpi-value">{overview.total_students}</span><span class="kpi-label">Students</span></div>
			<div class="kpi"><span class="kpi-value">{overview.total_sessions}</span><span class="kpi-label">Sessions</span></div>
			<div class="kpi"><span class="kpi-value">{formatPercentage(overview.avg_compliance_rate)}</span><span class="kpi-label">Avg compliance</span></div>
			<div class="kpi"><span class="kpi-value">{formatPercentage(overview.avg_participation_rate)}</span><span class="kpi-label">Avg participation</span></div>
		</section>
	{:else if tab === 'comparison'}
		<section class="card">
			<h2 class="card-title">Course Comparison</h2>
			<p class="muted">Same course shown once per cohort · {metric} rate</p>
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
									<td>{formatPercentage(r.compliance_rate)}</td>
									<td>{formatPercentage(r.participation_rate)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{:else if tab === 'trends'}
		<section class="card">
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
									<td>{formatPercentage(t.compliance_rate)}</td>
									<td>{formatPercentage(t.participation_rate)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{:else if tab === 'atrisk'}
		<section class="card">
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
								<th><button class="th-btn" onclick={() => (nameSortDir = nameSortDir === 'asc' ? 'desc' : 'asc')}>Name{nameSortDir === 'asc' ? ' ▲' : ' ▼'}</button></th>
								<th>Course</th>
								<th>Absence</th>
								<th>Streak</th>
								<th>Trend</th>
								<th>Risk</th>
							</tr>
						</thead>
						<tbody>
							{#each atRiskSorted as r (r.student_id)}
								<tr>
									<td class="strong">{r.student_name}<div class="muted small">{r.student_id} · {r.program} {r.year_level}</div></td>
									<td>{r.course_code}</td>
									<td>{formatPercentage(r.absence_rate)}</td>
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
	{:else if tab === 'export'}
		<section class="card">
			<h2 class="card-title">Export</h2>
			<p class="muted">CSV downloads of the current filter set — one file per dataset.</p>
			<div class="export-list">
				<div><div><div class="strong">Overview KPIs</div><div class="muted small">Totals + average rates</div></div><button class="btn btn-secondary" onclick={exportOverview} disabled={!overview}>Download CSV</button></div>
				<div><div><div class="strong">Course comparison</div><div class="muted small">{comparison.length} cohort rows</div></div><button class="btn btn-secondary" onclick={exportComparison}>Download CSV</button></div>
				<div><div><div class="strong">Trends</div><div class="muted small">{adminAnalyticsState.trends.length} periods</div></div><button class="btn btn-secondary" onclick={exportTrends}>Download CSV</button></div>
				<div><div><div class="strong">At-risk students</div><div class="muted small">{adminAnalyticsState.atRisk.length} rows</div></div><button class="btn btn-secondary" onclick={exportAtRisk}>Download CSV</button></div>
			</div>
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
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		color: #64748b;
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
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: #1e293b;
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
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #0f172a;
		background: white;
	}

	.input:focus {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
		border-color: #2563eb;
	}

	.input:disabled {
		background: #f1f5f9;
		color: #94a3b8;
		cursor: not-allowed;
	}

	.courses {
		display: flex;
		gap: 0.75rem 1.25rem;
		flex-wrap: wrap;
		align-items: center;
		border: 1px solid #e2e8f0;
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
		color: #64748b;
		padding: 0 0.375rem;
	}

	.check {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: #334155;
		cursor: pointer;
	}

	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid #e2e8f0;
		flex-wrap: wrap;
	}

	.tabs button {
		background: none;
		border: none;
		padding: 0.625rem 1rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		color: #64748b;
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -2px;
	}

	.tabs button:hover {
		color: #0f172a;
	}

	.tabs button.active {
		color: #1e3a5f;
		border-bottom-color: #1e3a5f;
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.kpi-value {
		font-size: 1.75rem;
		font-weight: 800;
		color: #1e293b;
	}

	.kpi-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #475569;
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
		border-bottom: 1px solid #f1f5f9;
		vertical-align: middle;
	}

	th {
		color: #64748b;
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
		color: #0f172a;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: #15803d;
		background: #dcfce7;
		text-transform: capitalize;
	}

	.badge.medium {
		color: #b45309;
		background: #fef3c7;
	}

	.badge.high {
		color: #b91c1c;
		background: #fee2e2;
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
		border: 1px solid #f1f5f9;
		border-radius: 8px;
		padding: 0.75rem 1rem;
	}

	.empty {
		color: #64748b;
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: #dc2626;
		font-size: 0.875rem;
		margin: 0;
		flex-basis: 100%;
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
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: #16324f;
	}

	.btn-secondary {
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
	}

	.btn-secondary:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.btn-secondary.selected {
		border-color: #1e3a5f;
		background: #1e3a5f;
		color: white;
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
