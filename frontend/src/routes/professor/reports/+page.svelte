<script lang="ts">
	import { page } from '$app/state';
	import ReportBarChart from '$lib/features/report/components/ReportBarChart.svelte';
	import ReportTrendChart from '$lib/features/report/components/ReportTrendChart.svelte';
	import {
		buildCsv,
		defaultReportRange,
		fetchProfessorReportsCsv,
		getAllCoursesReport,
		getComparisonReport,
		getReportFilterOptions,
		getTrendsReport,
		initReportDirectory,
		type ReportCourseDir,
		type ReportFilters,
		type ReportGranularity,
		type ReportMeta,
		type ReportMetric
	} from '$lib/features/report/service';
	import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
	import { isMockMode } from '$lib/api/client';
	import { formatPercentage } from '$lib/shared/utils/format';

	type Tab = 'all' | 'comparison' | 'trends';
	const TABS = [
		{ id: 'all', label: 'All Courses' },
		{ id: 'comparison', label: 'Per-Course Comparison' },
		{ id: 'trends', label: 'Trends' }
	] as const;
	const GRANULARITIES: Array<{ id: ReportGranularity; label: string }> = [
		{ id: 'daily', label: 'Daily' },
		{ id: 'weekly', label: 'Weekly' },
		{ id: 'monthly', label: 'Monthly' }
	];
	const METRICS: Array<{ id: ReportMetric; label: string }> = [
		{ id: 'compliance', label: 'Compliance' },
		{ id: 'participation', label: 'Participation' }
	];
	const TREND_COLORS = ['#2563eb', '#16a34a', '#9333ea', '#ca8a04', '#0d9488', '#dc2626'];

	// Course directory: mock fixture only in mock mode; live mode starts
	// empty and warms from GET /professor/courses, so a failed warm shows an
	// error instead of silently rendering demo courses as filters.
	let directory = $state<ReportCourseDir[]>(isMockMode() ? PROFESSOR_COURSES : []);
	let directoryError = $state<string | null>(null);
	let directoryToken = $state(0);
	const filterOptions = $derived(getReportFilterOptions(directory));
	const initialRange = defaultReportRange();

	let tab = $state<Tab>('all');
	let program = $state('All');
	let year = $state('All');
	let course = $state('All');
	let section = $state('All');
	let from = $state(initialRange.from);
	let to = $state(initialRange.to);
	let granularity = $state<ReportGranularity>('daily');
	let metric = $state<ReportMetric>('compliance');
	let appliedOffering = $state<number | null>(null);
	let prefilteredOfferingId = $state<number | null>(null);
	let unknownOffering = $state(false);
	let isLoading = $state(true);
	let reportError = $state<string | null>(null);
	let reloadToken = $state(0);
	let aggregate = $state<Awaited<ReturnType<typeof getAllCoursesReport>> | null>(null);
	let comparison = $state<Awaited<ReturnType<typeof getComparisonReport>> | null>(null);
	let trends = $state<Awaited<ReturnType<typeof getTrendsReport>> | null>(null);
	let reportMeta = $state<ReportMeta>(
		isMockMode() ? { dataSource: 'demo', truncated: false } : { dataSource: 'live', truncated: false }
	);

	$effect(() => {
		directoryToken;
		let cancelled = false;
		void initReportDirectory().then(({ directory: warmed, live }) => {
			if (cancelled) return;
			if (warmed === directory) return;
			directory = warmed;
			// Mock mode always serves the fixture (live:false) — that is
			// expected, not an error. Live mode falling back means the
			// courses call failed or returned nothing.
			directoryError =
				!live && !isMockMode() ? 'Could not load your courses — filters show demo entries.' : null;
		});
		return () => {
			cancelled = true;
		};
	});

	const requestedOfferingId = $derived.by(() => {
		const raw = page.url.searchParams.get('offering');
		if (raw === null) return null;
		const parsed = Number(raw);
		return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
	});

	$effect(() => {
		const wanted = requestedOfferingId;
		if (wanted === appliedOffering) return;
		appliedOffering = wanted;

		if (wanted === null) {
			prefilteredOfferingId = null;
			unknownOffering = false;
			course = 'All';
			section = 'All';
			return;
		}

		const offering = directory.find((item) => item.offeringId === wanted);
		if (!offering) {
			prefilteredOfferingId = null;
			unknownOffering = true;
			course = 'All';
			section = 'All';
			return;
		}

		prefilteredOfferingId = wanted;
		unknownOffering = false;
		course = offering.courseCode;
		section = offering.section;
	});

	const availableCourses = $derived(
		directory.filter(
			(item) =>
				(program === 'All' || item.programCode === program) &&
				(year === 'All' || item.yearLevelLabel === year)
		)
	);
	const availableSections = $derived([
		...new Set(
			availableCourses
				.filter((item) => course === 'All' || item.courseCode === course)
				.map((item) => item.section)
		)
	]);

	$effect(() => {
		const courseCodes = new Set(availableCourses.map((item) => item.courseCode));
		if (course !== 'All' && !courseCodes.has(course)) course = 'All';
		if (section !== 'All' && !availableSections.includes(section)) section = 'All';
	});

	$effect(() => {
		const query: ReportFilters = {
			program,
			year,
			course,
			section,
			from,
			to,
			granularity,
			metric
		};
		const activeTab = tab;
		reloadToken;
		const activeDirectory = directory;

		let cancelled = false;
		isLoading = true;
		reportError = null;

		const load = async () => {
			try {
				if (activeTab === 'all') {
					const data = await getAllCoursesReport(query, activeDirectory);
					if (cancelled) return;
					aggregate = data;
					reportMeta = data.meta;
					comparison = null;
					trends = null;
				} else if (activeTab === 'comparison') {
					const data = await getComparisonReport(query, activeDirectory);
					if (cancelled) return;
					comparison = data;
					reportMeta = data.meta;
					aggregate = null;
					trends = null;
				} else {
					const data = await getTrendsReport(query, activeDirectory);
					if (cancelled) return;
					trends = data;
					reportMeta = data.meta;
					aggregate = null;
					comparison = null;
				}
			} catch (e) {
				if (cancelled) return;
				reportError = e instanceof Error ? e.message : 'Reports could not be loaded.';
			} finally {
				if (!cancelled) isLoading = false;
			}
		};

		void load();
		return () => {
			cancelled = true;
		};
	});

	const prefilteredOffering = $derived(
		prefilteredOfferingId === null
			? null
			: (directory.find((item) => item.offeringId === prefilteredOfferingId) ?? null)
	);
	const prefilterActive = $derived(
		prefilteredOffering !== null &&
			course === prefilteredOffering.courseCode &&
			section === prefilteredOffering.section
	);
	const clearPrefilter = () => {
		prefilteredOfferingId = null;
		course = 'All';
		section = 'All';
	};

	const rateFor = (compliance: number, participation: number): number =>
		metric === 'compliance' ? compliance : participation;

	const aggregateBars = $derived(
		(aggregate?.items ?? []).map((item) => ({
			label: item.label,
			value: rateFor(item.compliance_rate, item.participation_rate),
			detail: `${item.total_sessions} ${item.total_sessions === 1 ? 'session' : 'sessions'}`
		}))
	);
	const aggregateAverage = $derived(
		aggregate ? rateFor(aggregate.avg_compliance, aggregate.avg_participation) : null
	);
	const comparisonBars = $derived(
		(comparison?.items ?? []).map((item) => ({
			label: `${item.program_code}·${item.year_level_label} ${item.course_code}`,
			value: rateFor(item.compliance_rate, item.participation_rate),
			detail: `Section ${item.section}`
		}))
	);
	const trendSeries = $derived.by(() => {
		if (!trends) return [];
		const groups = new Map<
			number,
			{ label: string; points: Array<{ x: string; y: number }> }
		>();
		for (const point of trends.items) {
			const group = groups.get(point.offering_id) ?? { label: point.cohort, points: [] };
			group.points.push({ x: point.label, y: point.rate });
			groups.set(point.offering_id, group);
		}
		return [...groups.values()].map((group, index) => ({
			label: group.label,
			color: TREND_COLORS[index % TREND_COLORS.length],
			points: group.points
		}));
	});

	const csvHeader = $derived.by(() => {
		if (tab === 'all') {
			return ['Period', 'Total sessions', 'Total students', 'Compliance rate', 'Participation rate'];
		}
		if (tab === 'comparison') {
			return [
				'Course',
				'Course name',
				'Program',
				'Year level',
				'Section',
				'Total sessions',
				'Compliance rate',
				'Participation rate'
			];
		}
		return ['Period', 'Course', 'Cohort', `${metric} rate`, 'Metric'];
	});
	const csvRows = $derived.by<Array<Array<string | number>>>(() => {
		if (tab === 'all') {
			return (aggregate?.items ?? []).map((item) => [
				item.label,
				item.total_sessions,
				item.total_students,
				item.compliance_rate.toFixed(4),
				item.participation_rate.toFixed(4)
			]);
		}
		if (tab === 'comparison') {
			return (comparison?.items ?? []).map((item) => [
				item.course_code,
				item.course_name,
				item.program_code,
				item.year_level_label,
				item.section,
				item.total_sessions,
				item.compliance_rate.toFixed(4),
				item.participation_rate.toFixed(4)
			]);
		}
		return (trends?.items ?? []).map((item) => [
			item.label,
			item.course_code,
			item.cohort,
			item.rate.toFixed(4),
			metric
		]);
	});
	const csvFilename = $derived(
		`professor-${tab}-report-${from}-to-${to}.csv`.replace(/[^a-z0-9._-]+/gi, '-')
	);

	// Server export body: the backend takes one course_id, so a filtered
	// course resolves only when every matching directory entry agrees on it —
	// otherwise the union export (no course_id) covers the same rows.
	const exportBody = $derived.by(() => {
		const ids = new Set(
			directory.filter((item) => item.courseCode === course).map((item) => item.courseId)
		);
		return {
			...(course !== 'All' && ids.size === 1 ? { course_id: [...ids][0] } : {}),
			date_from: `${from <= to ? from : to}T00:00:00`,
			date_to: `${from <= to ? to : from}T23:59:59`
		};
	});

	const saveCsv = (text: string) => {
		const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = csvFilename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		URL.revokeObjectURL(url);
	};

	// Server-first export (POST /professor/reports/export): the download
	// matches the backend's per-scan rows. Mock mode and unreachable backends
	// fall back to the client-side aggregate CSV so Export always works.
	let exportNote = $state<string | null>(null);
	const downloadCsv = async () => {
		if (csvRows.length === 0) return;
		exportNote = null;
		try {
			saveCsv(await fetchProfessorReportsCsv(exportBody));
		} catch {
			exportNote = 'Server export unavailable — downloaded the on-screen rows instead.';
			saveCsv(buildCsv(csvHeader, csvRows));
		}
	};

	const retry = () => {
		reloadToken += 1;
	};
</script>

<div class="reports">
	<header class="header">
		<div>
			<h1>Attendance Reports</h1>
			<p class="muted">
				{#if isLoading}
					Loading attendance reports…
				{:else if reportMeta.dataSource === 'live'}
					Live attendance data from your reports.
				{:else}
					Demo report data — live reports are unavailable.
				{/if}
			</p>
			{#if reportMeta.truncated}
				<p class="warning" role="status">
					Showing the 500 most recent sessions in this range; narrow the dates to see older ones.
				</p>
			{/if}
			{#if directoryError}
				<p class="warning" role="alert">
					{directoryError}
					<button class="link-button" type="button" onclick={() => (directoryToken += 1)}>
						Try again
					</button>
				</p>
			{/if}
		</div>
	</header>

	<section class="card">
		<div class="filter-grid">
			<div class="field">
				<label class="form-label" for="report-program">Program</label>
				<select id="report-program" class="form-input" bind:value={program}>
					<option value="All">All programs</option>
					{#each filterOptions.programs as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="report-year">Year level</label>
				<select id="report-year" class="form-input" bind:value={year}>
					<option value="All">All year levels</option>
					{#each filterOptions.years as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="report-course">Course</label>
				<select id="report-course" class="form-input" bind:value={course}>
					<option value="All">All courses</option>
					{#each filterOptions.courses as option (option.code)}
						<option value={option.code}>{option.code} — {option.name}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="report-section">Section</label>
				<select id="report-section" class="form-input" bind:value={section}>
					<option value="All">All sections</option>
					{#each availableSections as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="report-from">From</label>
				<input id="report-from" class="form-input" type="date" bind:value={from} />
			</div>
			<div class="field">
				<label class="form-label" for="report-to">To</label>
				<input id="report-to" class="form-input" type="date" bind:value={to} />
			</div>
		</div>

		<div class="option-row">
			<fieldset>
				<legend>Granularity</legend>
				{#each GRANULARITIES as option (option.id)}
					<label class="choice">
						<input type="radio" name="report-granularity" value={option.id} bind:group={granularity} />
						<span>{option.label}</span>
					</label>
				{/each}
			</fieldset>
			<fieldset>
				<legend>Metric</legend>
				{#each METRICS as option (option.id)}
					<label class="choice">
						<input type="radio" name="report-metric" value={option.id} bind:group={metric} />
						<span>{option.label}</span>
					</label>
				{/each}
			</fieldset>
		</div>

		{#if unknownOffering}
			<p class="warning" role="status">That course link was not recognized, so all courses are shown.</p>
		{/if}
		{#if prefilterActive && prefilteredOffering}
			<p class="prefilter" role="status">
				Prefiltered from My Courses: {prefilteredOffering.courseCode} · Section {prefilteredOffering.section}
				<button class="link-button" type="button" onclick={clearPrefilter}>Clear</button>
			</p>
		{/if}
	</section>

	<div class="tabs" role="radiogroup" aria-label="Report views">
		{#each TABS as item (item.id)}
			<label class="tab" class:selected={tab === item.id}>
				<input type="radio" name="report-tab" value={item.id} bind:group={tab} />
				<span>{item.label}</span>
			</label>
		{/each}
	</div>

	{#if reportError}
		<section class="card">
			<p class="error">{reportError}</p>
			<button class="btn btn-secondary" type="button" onclick={retry}>Try again</button>
		</section>
	{:else if isLoading}
		<section class="card">
			<p class="muted">Loading reports…</p>
		</section>
	{:else if tab === 'all' && aggregate}
		<section class="kpis" aria-label="Aggregate report summary">
			<article class="kpi">
				<span class="kpi-value">{formatPercentage((metric === 'compliance' ? aggregate.avg_compliance : aggregate.avg_participation) * 100)}</span>
				<span class="kpi-label">Average {metric}</span>
			</article>
			<article class="kpi">
				<span class="kpi-value">{aggregate.total_sessions}</span>
				<span class="kpi-label">Sessions</span>
			</article>
			<article class="kpi">
				<span class="kpi-value">{aggregate.total_students}</span>
				<span class="kpi-label">Student sessions</span>
			</article>
		</section>
		<section class="card">
			<h2 class="section-title">All courses</h2>
			<ReportBarChart
				title="All courses report"
				description="Aggregate attendance rate by reporting period."
				bars={aggregateBars}
				average={aggregateAverage}
			/>
		</section>
		<section class="card">
			<h2 class="section-title">Period breakdown</h2>
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th scope="col">Period</th>
							<th scope="col">Sessions</th>
							<th scope="col">Students</th>
							<th scope="col">Compliance</th>
							<th scope="col">Participation</th>
						</tr>
					</thead>
					<tbody>
						{#each aggregate.items as item (item.key)}
							<tr>
								<td>{item.label}</td>
								<td>{item.total_sessions}</td>
								<td>{item.total_students}</td>
								<td>{formatPercentage(item.compliance_rate * 100)}</td>
								<td>{formatPercentage(item.participation_rate * 100)}</td>
							</tr>
						{:else}
							<tr>
								<td colspan="5" class="muted">No sessions in this range.</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else if tab === 'comparison' && comparison}
		<section class="kpis" aria-label="Comparison report summary">
			<article class="kpi">
				<span class="kpi-value">{comparison.items.length}</span>
				<span class="kpi-label">Cohorts</span>
			</article>
			<article class="kpi">
				<span class="kpi-value">{comparison.items.reduce((total, item) => total + item.total_sessions, 0)}</span>
				<span class="kpi-label">Sessions</span>
			</article>
		</section>
		<section class="card">
			<h2 class="section-title">Per-course comparison</h2>
			<ReportBarChart
				title="Per-course comparison report"
				description="Attendance rate for each course cohort."
				bars={comparisonBars}
			/>
		</section>
		<section class="card">
			<h2 class="section-title">Cohort breakdown</h2>
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th scope="col">Course</th>
							<th scope="col">Cohort</th>
							<th scope="col">Section</th>
							<th scope="col">Sessions</th>
							<th scope="col">Compliance</th>
							<th scope="col">Participation</th>
						</tr>
					</thead>
					<tbody>
						{#each comparison.items as item (`${item.course_code}-${item.program_code}-${item.year_level_label}-${item.section}`)}
							<tr>
								<td>{item.course_code} — {item.course_name}</td>
								<td>{item.program_code}·{item.year_level_label}</td>
								<td>{item.section}</td>
								<td>{item.total_sessions}</td>
								<td>{formatPercentage(item.compliance_rate * 100)}</td>
								<td>{formatPercentage(item.participation_rate * 100)}</td>
							</tr>
						{:else}
							<tr>
								<td colspan="6" class="muted">No sessions in this range.</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else if tab === 'trends' && trends}
		<section class="kpis" aria-label="Trend report summary">
			<article class="kpi">
				<span class="kpi-value">{trendSeries.length}</span>
				<span class="kpi-label">Course series</span>
			</article>
			<article class="kpi">
				<span class="kpi-value">{trends.items.length}</span>
				<span class="kpi-label">Data points</span>
			</article>
		</section>
		<section class="card">
			<h2 class="section-title">{metric === 'compliance' ? 'Compliance' : 'Participation'} trends</h2>
			<ReportTrendChart
				title="Attendance trend report"
				description="Attendance rate over time for each selected course cohort."
				series={trendSeries}
			/>
		</section>
		<section class="card">
			<h2 class="section-title">Trend breakdown</h2>
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th scope="col">Period</th>
							<th scope="col">Course</th>
							<th scope="col">Cohort</th>
							<th scope="col">Rate</th>
						</tr>
					</thead>
					<tbody>
						{#each trends.items as item (`${item.date}-${item.offering_id}`)}
							<tr>
								<td>{item.label}</td>
								<td>{item.course_code}</td>
								<td>{item.cohort}</td>
								<td>{formatPercentage(item.rate * 100)}</td>
							</tr>
						{:else}
							<tr>
								<td colspan="4" class="muted">No sessions in this range.</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if !reportError && !isLoading}
		<section class="card export">
			<div>
				<h2 class="section-title">Export current view</h2>
				<p class="muted">CSV contains the rows shown for the active tab and filters.</p>
			</div>
			<div class="export-actions">
				<button
					class="btn btn-secondary"
					type="button"
					disabled={csvRows.length === 0}
					title={csvRows.length === 0 ? 'No report rows to export' : 'Download the current report as CSV'}
					onclick={downloadCsv}
				>
					Download CSV
				</button>				<button
					class="btn btn-secondary"
					type="button"
					disabled={csvRows.length === 0}
					title={csvRows.length === 0 ? 'No report rows to export' : 'Print the current report as PDF'}
					onclick={() => window.print()}
				>
					Download PDF
				</button>
			</div>
			{#if exportNote}
				<p class="muted" role="status">{exportNote}</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.reports {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
		font-family: system-ui, sans-serif;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		margin: 0 0 0.25rem;
		color: var(--text);
	}

	.muted {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.section-title {
		margin: 0 0 1rem;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text);
	}

	.filter-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.form-input {
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font: inherit;
		font-size: 0.9375rem;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.option-row {
		display: flex;
		flex-wrap: wrap;
		gap: 1.5rem;
		margin-top: 1.25rem;
	}

	.option-row fieldset {
		border: 0;
		margin: 0;
		padding: 0;
	}

	.option-row legend {
		padding: 0;
		margin-bottom: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.choice {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		margin-right: 1rem;
		font-size: 0.875rem;
		color: var(--text-strong);
	}

	.warning {
		margin: 1rem 0 0;
		color: var(--warning-text);
		font-size: 0.875rem;
		font-weight: 600;
	}

	.prefilter {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 1rem 0 0;
		font-size: 0.875rem;
		color: var(--brand);
	}

	.link-button {
		border: 0;
		background: transparent;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		text-decoration: underline;
	}

	.tabs {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.tab {
		position: relative;
		display: inline-flex;
		padding: 0.625rem 1rem;
		border: 1px solid var(--border-strong);
		border-radius: 999px;
		background: var(--bg-card);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.tab input {
		position: absolute;
		opacity: 0;
		inset: 0;
		margin: 0;
		cursor: pointer;
	}

	.tab.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.tab:focus-within {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 1rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
	}

	.kpi-value {
		font-size: 1.625rem;
		font-weight: 800;
		font-variant-numeric: tabular-nums;
		color: var(--brand);
	}

	.kpi-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.table-wrap {
		overflow: auto;
		max-height: 24rem;
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	table {
		width: 100%;
		min-width: 620px;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.75rem;
		text-align: left;
		border-bottom: 1px solid var(--divider);
		color: var(--text-strong);
	}

	thead th {
		position: sticky;
		top: 0;
		z-index: 1;
		background: var(--bg-page);
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	tbody tr:last-child td {
		border-bottom: none;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.7rem 1.2rem;
		border-radius: 8px;
		border: 1px solid transparent;
		font: inherit;
		font-size: 0.9375rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-secondary {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
	}

	.btn:disabled {
		background: var(--bg-page);
		border-color: var(--border);
		color: #94a3b8;
		cursor: not-allowed;
	}

	.error {
		margin: 0 0 1rem;
		color: var(--danger-strong);
		font-weight: 600;
	}

	.export {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.export-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	@media (max-width: 720px) {
		.filter-grid {
			grid-template-columns: 1fr;
		}

		.kpis {
			grid-template-columns: 1fr;
		}

		.export-actions .btn,
		.card .btn {
			flex: 1 1 auto;
		}
	}
</style>
