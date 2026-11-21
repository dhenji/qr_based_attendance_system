<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import SkeletonCards from '$lib/components/SkeletonCards.svelte';
	import { onDestroy, onMount } from 'svelte';
	import ReportBarChart from '$lib/features/report/components/ReportBarChart.svelte';
	import {
		adminAttendanceState,
		adminAttendanceSummaryState,
		adminAttendanceRecordsState,
		initAttendanceOverview,
		initAttendanceSummary,
		initAttendanceRecords,
	} from '$lib/features/admin/analytics/store.svelte';
	import {
		attendanceOverviewCsv,
		downloadCsv,
		fetchAttendanceOverviewCsv,
		fetchAttendanceRecordsCsv,
	} from '$lib/features/admin/analytics/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listProfessors } from '$lib/features/admin/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { debounce } from '$lib/shared/utils/debounce';
	import type {
		AdminCourse,
		AdminProfessor,
		AttendanceOverviewItemResponse,
		AttendanceRecordItemResponse,
		Program,
		YearLevel,
	} from '$lib/shared/types';
	import { formatPercentage } from '$lib/shared/utils/format';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { goto } from '$app/navigation';
	import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import { adminCourse } from '$lib/shared/constants/routes';

	type SortColumn = 'course' | 'sessions' | 'avg' | 'trend';

	let programFilter = $state('');
	let yearFilter = $state('');
	let semesterFilter = $state('');
	let courseFilter = $state('');
	let professorFilter = $state('');
	let sessionTypeFilter = $state<'' | 'lecture' | 'lab'>('');
	let statusFilter = $state('');
	let studentSearch = $state('');
	let recordsPage = $state(1);
	let dateFrom = $state('');
	let dateTo = $state('');
	let datePreset = $state<'custom' | 'today' | 'week' | 'month' | 'semester' | 'year' | 'all'>('custom');
	let advancedOpen = $state(false);
	const studentSearchDebounced = debounce(() => void load());
	let sortBy = $state<SortColumn>('course');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let courseOptions = $state<AdminCourse[]>([]);
	let professorOptions = $state<AdminProfessor[]>([]);
	let filterNotice = $state<string | null>(null);
	let exportNote = $state<string | null>(null);
	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
	}>(null);

	const filters = $derived({
		program_id: programFilter ? Number(programFilter) : undefined,
		year_level_id: yearFilter ? Number(yearFilter) : undefined,
		semester: semesterFilter.trim() || undefined,
		course_id: courseFilter ? Number(courseFilter) : undefined,
		professor_id: professorFilter ? Number(professorFilter) : undefined,
		session_type: sessionTypeFilter || undefined,
		status: statusFilter || undefined,
		student_search: studentSearch.trim() || undefined,
		date_from: dateFrom.trim() || undefined,
		date_to: dateTo.trim() || undefined,
	});

	const advancedActiveCount = $derived(
		[semesterFilter, professorFilter, sessionTypeFilter, statusFilter, studentSearch].filter((v) => String(v).trim() !== '').length
	);

	const visibleItems = $derived.by(() => {
		const items = [...adminAttendanceState.items];
		const dir = sortDir === 'asc' ? 1 : -1;
		const trendRank = (t: string): number => (t === 'up' ? 2 : t === 'flat' ? 1 : 0);
		items.sort((a, b) => {
			switch (sortBy) {
				case 'sessions':
					return (a.sessions_count - b.sessions_count) * dir;
				case 'avg':
					return (a.avg_rate - b.avg_rate) * dir;
				case 'trend':
					return (trendRank(a.trend) - trendRank(b.trend)) * dir;
				default:
					return a.course_code.localeCompare(b.course_code) * dir;
			}
		});
		return items;
	});

	const statusBars = $derived.by(() => {
		const s = adminAttendanceSummaryState.data;
		if (!s || s.total_records === 0) return [];
		const total = s.total_records;
		return [
			{ label: 'Present', value: s.present / total, detail: `${s.present} records` },
			{ label: 'Late', value: s.late / total, detail: `${s.late} records` },
			{ label: 'Excused', value: s.excused / total, detail: `${s.excused} records` },
			{ label: 'Rejected', value: s.rejected / total, detail: `${s.rejected} records` },
		];
	});

	const loadRecords = async (page: number = recordsPage) => {
		recordsPage = page;
		await initAttendanceRecords({ ...filters, page, size: 20 });
	};

	const load = async () => {
		recordsPage = 1;
		await Promise.all([
			initAttendanceOverview(filters),
			initAttendanceSummary(filters),
			initAttendanceRecords({ ...filters, page: 1, size: 20 }),
		]);
	};

	const applyPreset = (preset: typeof datePreset) => {
		datePreset = preset;
		const now = new Date();
		const toIso = (d: Date) => d.toISOString().slice(0, 10);
		if (preset === 'today') {
			dateFrom = toIso(now);
			dateTo = toIso(now);
		} else if (preset === 'week') {
			const start = new Date(now);
			start.setDate(now.getDate() - now.getDay());
			dateFrom = toIso(start);
			dateTo = toIso(now);
		} else if (preset === 'month') {
			const start = new Date(now.getFullYear(), now.getMonth(), 1);
			dateFrom = toIso(start);
			dateTo = toIso(now);
		} else if (preset === 'year') {
			const start = new Date(now.getFullYear(), 0, 1);
			dateFrom = toIso(start);
			dateTo = toIso(now);
		} else if (preset === 'all') {
			dateFrom = '';
			dateTo = '';
		}
	};

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
	};

	const resetFilters = () => {
		programFilter = '';
		yearFilter = '';
		semesterFilter = '';
		courseFilter = '';
		professorFilter = '';
		sessionTypeFilter = '';
		statusFilter = '';
		studentSearch = '';
		dateFrom = '';
		dateTo = '';
		datePreset = 'custom';
		void load();
	};

	const toggleSort = (column: SortColumn) => {
		if (sortBy === column) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortDir = 'asc';
		}
	};

	const sortArrow = (column: SortColumn) =>
		sortBy === column ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

	const trendGlyph = (row: AttendanceOverviewItemResponse): string =>
		row.trend === 'up' ? '↑' : row.trend === 'down' ? '↓' : '→';

	const onExportOverview = async () => {
		const filename = `attendance-overview-${new Date().toISOString().slice(0, 10)}.csv`;
		exportNote = null;
		try {
			downloadCsv(
				filename,
				await fetchAttendanceOverviewCsv(filters)
			);
		} catch {
			exportNote = 'Server export unavailable — downloaded the on-screen rows instead.';
			downloadCsv(filename, attendanceOverviewCsv(adminAttendanceState.items));
		}
	};

	const onExportRecords = async () => {
		const filename = `attendance-records-${new Date().toISOString().slice(0, 10)}.csv`;
		exportNote = null;
		try {
			downloadCsv(filename, await fetchAttendanceRecordsCsv(filters));
		} catch {
			exportNote = 'Server export unavailable.';
		}
	};

	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		studentSearchDebounced.cancel();
		for (const stop of autoRefreshStops) stop();
	});

	onMount(async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
			filterNotice = 'Some filters failed to load — lists may be incomplete.';
		}
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
		}
		try {
			professorOptions = (await listProfessors({ page: 1, size: 100 })).items;
		} catch {
			professorOptions = [];
		}
		await load();
		if (!pageAlive) return;
		autoRefreshStops.push(
			subscribeEntity('courses', async () => {
				try {
					courseOptions = (await listCourses({ page: 1, size: 100 })).items;
				} catch {
					courseOptions = [];
				}
			}),
			subscribeEntity('professors', async () => {
				try {
					professorOptions = (await listProfessors({ page: 1, size: 100 })).items;
				} catch {
					professorOptions = [];
				}
			}),
			onFocusRevalidate(() => {
				if (adminAttendanceState.loading) return;
				void load();
			})
		);
	});
</script>

<section class="card">
	<div class="row-head">
		<div>
			<h2 class="card-title">Attendance analytics</h2>
			<p class="muted">
				Per-course sessions, average rate, and trend · {adminAttendanceState.items.length} courses
			</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" onclick={() => window.print()}>Print</button>
			<button
				class="btn btn-primary"
				data-testid="export-overview"
				onclick={() => (pendingExport = { run: onExportOverview, details: [{ label: 'Dataset', value: 'Attendance overview' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminAttendanceState.items.length) }] })}
			>
				Export Overview
			</button>
			<button
				class="btn btn-secondary"
				onclick={() => (pendingExport = { run: onExportRecords, details: [{ label: 'Dataset', value: 'Attendance records' }, { label: 'Format', value: 'CSV' }, { label: 'Rows', value: String(adminAttendanceRecordsState.total) }] })}
			>
				Export Records
			</button>
		</div>
	</div>

	{#if exportNote}
		<p class="muted" role="status">{exportNote}</p>
	{/if}

	<div class="filters" aria-label="Attendance analytics filters">
		<p class="eyebrow">Scope</p>
		<div class="filter-grid">
			<div class="field">
				<label class="form-label" for="att-program">Program</label>
				<select id="att-program" class="form-input" bind:value={programFilter} onchange={() => { changeProgram(); void load(); }}>
					<option value="">All programs</option>
					{#each programOptions as p (p.id)}
						<option value={p.id}>{p.code} — {p.name}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="att-year">Year level</label>
				<select
					id="att-year"
					class="form-input"
					bind:value={yearFilter}
					onchange={() => void load()}
					disabled={!programFilter}
				>
					<option value="">All years</option>
					{#each yearOptions as y (y.id)}
						<option value={y.id}>{y.label}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="att-course">Course</label>
				<select id="att-course" class="form-input" bind:value={courseFilter} onchange={() => void load()}>
					<option value="">All courses</option>
					{#each courseOptions as c (c.id)}
						<option value={c.id}>{c.courseCode} — {c.courseName}</option>
					{/each}
				</select>
			</div>
		</div>

		<p class="eyebrow" style="margin-top:1rem;">Time range</p>
		<div class="preset-row">
			{#each ['today', 'week', 'month', 'year', 'all'] as p (p)}
				<button class="btn btn-ghost" class:selected={datePreset === p} onclick={() => { applyPreset(p as any); void load(); }}>
					{p === 'today' ? 'Today' : p === 'week' ? 'This week' : p === 'month' ? 'This month' : p === 'year' ? 'This year' : 'All time'}
				</button>
			{/each}
		</div>
		<div class="filter-grid filter-grid-4">
			<div class="field">
				<label class="form-label" for="att-from">From date</label>
				<input id="att-from" class="form-input" type="date" bind:value={dateFrom} onchange={() => { datePreset = 'custom'; void load(); }} />
			</div>
			<div class="field">
				<label class="form-label" for="att-to">To date</label>
				<input id="att-to" class="form-input" type="date" bind:value={dateTo} onchange={() => { datePreset = 'custom'; void load(); }} />
			</div>
			<div class="field">
				<span class="form-label">&nbsp;</span>
				<button class="btn btn-secondary" onclick={resetFilters}>Reset filters</button>
			</div>
			<div class="field">
				<span class="form-label">&nbsp;</span>
				<button
					class="btn btn-secondary advanced-toggle"
					type="button"
					aria-expanded={advancedOpen}
					aria-controls="advanced-filters"
					onclick={() => (advancedOpen = !advancedOpen)}
				>
					Advanced filters{#if advancedActiveCount > 0} ({advancedActiveCount}){/if}
				</button>
			</div>
		</div>
		{#if advancedOpen}
			<div id="advanced-filters" class="advanced-panel" style="margin-top:1rem;">
				<div class="field">
					<label class="form-label" for="att-semester">Semester</label>
					<select id="att-semester" class="form-input" bind:value={semesterFilter} onchange={() => void load()}>
						<option value="">All semesters</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="att-professor">Professor</label>
					<select id="att-professor" class="form-input" bind:value={professorFilter} onchange={() => void load()}>
						<option value="">All professors</option>
						{#each professorOptions as p (p.id)}
							<option value={p.id}>{p.firstName} {p.lastName}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="att-session-type">Session type</label>
					<select id="att-session-type" class="form-input" bind:value={sessionTypeFilter} onchange={() => void load()}>
						<option value="">All types</option>
						<option value="lecture">Lecture</option>
						<option value="lab">Lab</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="att-status">Status</label>
					<select id="att-status" class="form-input" bind:value={statusFilter} onchange={() => void load()}>
						<option value="">All statuses</option>
						<option value="present">Present</option>
						<option value="late">Late</option>
						<option value="excused">Excused</option>
						<option value="rejected">Rejected</option>
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="att-student-search">Student search</label>
					<input id="att-student-search" class="form-input" type="search" placeholder="Student name or number" bind:value={studentSearch} oninput={() => studentSearchDebounced()} />
				</div>
				<div class="field">
					<span class="form-label">&nbsp;</span>
					<button class="btn btn-secondary" type="button" onclick={() => { semesterFilter=''; professorFilter=''; sessionTypeFilter=''; statusFilter=''; studentSearch=''; }}>Clear advanced</button>
				</div>
			</div>
		{/if}
		{#if filterNotice}
			<p class="muted" role="status">{filterNotice}</p>
		{/if}
	</div>
</section>

{#if adminAttendanceSummaryState.loading && !adminAttendanceSummaryState.data}
	<SkeletonCards count={6} label="Loading attendance summary…" />
{:else if adminAttendanceSummaryState.data}
	<section class="stat-strip" aria-busy={adminAttendanceSummaryState.loading}>
		<div class="kpi"><span class="kpi-value">{adminAttendanceSummaryState.data.total_records}</span><span class="kpi-label" title="All attendance scans in the selected filters">Total records</span></div>
		<div class="kpi"><span class="kpi-value">{adminAttendanceSummaryState.data.present}</span><span class="kpi-label">Present</span></div>
		<div class="kpi"><span class="kpi-value">{adminAttendanceSummaryState.data.late}</span><span class="kpi-label">Late</span></div>
		<div class="kpi"><span class="kpi-value">{adminAttendanceSummaryState.data.excused}</span><span class="kpi-label">Excused</span></div>
		<div class="kpi"><span class="kpi-value">{adminAttendanceSummaryState.data.rejected}</span><span class="kpi-label">Rejected</span></div>
		<div class="kpi">
		<span class="kpi-value">{formatPercentage(adminAttendanceSummaryState.data.compliance_rate * 100)}</span>
		<span class="kpi-label" title="Present scans divided by enrolled students">Compliance rate</span>
	</div>
	</section>
{/if}

{#if adminAttendanceState.items.length > 0}
	<section class="card">
		<p class="eyebrow">Breakdown</p>
		<h3 class="card-title">Status distribution</h3>
		<ReportBarChart
			title="Status distribution"
			description="Counts of attendance records by status for the current filters."
			bars={statusBars}
			emptyMessage="No status data."
		/>
	</section>
{/if}

{#if adminAttendanceState.loading && adminAttendanceState.items.length === 0}
	<SkeletonTable rows={6} cols={6} label="Loading attendance overview…" />
{:else if adminAttendanceState.error}
	<section class="card"><p class="error">Could not load overview: {adminAttendanceState.error}</p></section>
{:else if visibleItems.length === 0}
	<section class="card">
		<EmptyState icon="chart" title="No courses match these filters" hint="Adjust the filters to widen the view." />
	</section>
{:else}
	<section class="card table-wrap" aria-busy={adminAttendanceState.loading}>
		<p class="eyebrow">By course</p>
		<h3 class="card-title">Per-course attendance</h3>
		<table>
			<thead>
				<tr>
					<th scope="col" aria-sort={sortBy === 'course' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
						<button class="th-btn" type="button" onclick={() => toggleSort('course')} aria-label="Sort by course">Course<span aria-hidden="true">{sortArrow('course')}</span></button>
					</th>
					<th scope="col" aria-sort={sortBy === 'sessions' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
						<button class="th-btn" type="button" onclick={() => toggleSort('sessions')} aria-label="Sort by sessions">Sessions<span aria-hidden="true">{sortArrow('sessions')}</span></button>
					</th>
					<th scope="col" aria-sort={sortBy === 'avg' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
						<button class="th-btn" type="button" onclick={() => toggleSort('avg')} aria-label="Sort by average rate">Avg<span aria-hidden="true">{sortArrow('avg')}</span></button>
					</th>
					<th scope="col" aria-sort={sortBy === 'trend' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
						<button class="th-btn" type="button" onclick={() => toggleSort('trend')} aria-label="Sort by trend">Trend<span aria-hidden="true">{sortArrow('trend')}</span></button>
					</th>
				</tr>
			</thead>
			<tbody>
				{#each visibleItems as r (r.course_id)}
					<tr>
						<td><button class="link strong" onclick={() => goto(adminCourse(r.course_id))}>{r.course_code}</button><div class="muted small">{r.course_name}</div></td>
						<td>{r.sessions_count}</td>
						<td>{formatPercentage(r.avg_rate * 100)}</td>
						<td title={r.trend}><span class="trend" aria-label={r.trend}>{trendGlyph(r)}</span></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{/if}

<section class="card">
	<div class="row-head">
		<div>
			<p class="eyebrow">Records</p>
		<h3 class="card-title">Detailed attendance records</h3>
			<p class="muted">{adminAttendanceRecordsState.total} records</p>
		</div>
	</div>
	{#if adminAttendanceRecordsState.loading && adminAttendanceRecordsState.items.length === 0}
		<SkeletonTable rows={6} cols={8} label="Loading records…" />
	{:else if adminAttendanceRecordsState.error}
		<p class="error" role="alert">{adminAttendanceRecordsState.error}</p>
	{:else if adminAttendanceRecordsState.items.length === 0}
		<EmptyState icon="chart" title="No records match these filters" hint="Adjust the filters to widen the view." />
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th scope="col">Student</th>
						<th scope="col">Course</th>
						<th scope="col">Program</th>
						<th scope="col">Year</th>
						<th scope="col">Instructor</th>
						<th scope="col">Session</th>
						<th scope="col">Status</th>
						<th scope="col">Scanned at</th>
					</tr>
				</thead>
				<tbody>
					{#each adminAttendanceRecordsState.items as r (r.id)}
						<tr>
							<td class="strong">{r.student_name}<div class="muted small">{r.student_number}</div></td>
							<td>{r.course_code}</td>
							<td>{r.program_code ?? ''}</td>
							<td>{r.year_level_label ?? ''}</td>
							<td>{r.professor_name ?? '—'}</td>
							<td>{r.session_code ?? ''}</td>
							<td><span class="badge status-{r.status}">{r.status}</span></td>
							<td class="muted small">{r.scanned_at}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		{#if adminAttendanceRecordsState.total > 20}
			<Pagination
				page={recordsPage}
				totalPages={Math.max(1, Math.ceil(adminAttendanceRecordsState.total / 20))}
				onPageChange={(p) => void loadRecords(p)}
			/>
		{/if}
	{/if}
</section>

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

<style>
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
	.card-title { margin: 0 0 0.375rem; font-size: 1.125rem; font-weight: 700; color: var(--text); }
	.eyebrow { margin: 0 0 0.5rem; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }
	.filter-grid { display: grid; gap: 1rem; grid-template-columns: repeat(3, minmax(0, 1fr)); }
	.filter-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	.filter-grid .btn { width: 100%; justify-content: center; }
	.field { display: flex; flex-direction: column; gap: 0.4375rem; min-width: 0; }
	.form-label { font-size: 0.8125rem; font-weight: 600; letter-spacing: 0.02em; color: var(--text-secondary); }
	.form-input { padding: 0.625rem 0.75rem; border: 1px solid var(--border-strong); border-radius: 8px; font-size: 0.9375rem; font-family: inherit; color: var(--text-strong); background: var(--bg-card); width: 100%; }
	.form-input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.form-input:disabled { background: var(--divider); color: var(--text-muted); cursor: not-allowed; }
	.btn-ghost { background: var(--bg-card); border: 1px solid var(--border-strong); color: var(--text-strong); padding: 0.5rem 0.9rem; font-size: 0.875rem; border-radius: 8px; }
	.btn-ghost:hover:not(:disabled) { background: var(--bg-hover, var(--divider)); }
	.btn-ghost.selected { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
	.btn-ghost.selected:hover:not(:disabled) { background: var(--brand-hover); border-color: var(--brand-hover); color: var(--on-brand); }
	.row-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
	.header-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
	.muted { color: var(--text-muted); font-size: 0.875rem; margin: 0; }
	.muted.small { font-size: 0.75rem; }
	.filters { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }
	.input { padding: 0.625rem 0.875rem; border: 1px solid var(--border-strong); border-radius: 8px; font-size: 0.9375rem; font-family: inherit; color: var(--text-strong); background: var(--bg-card); }
	.input:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.stat-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem; margin: 1rem 0; padding: 1rem; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow-sm); }
	.stat-strip .kpi { background: transparent; border: none; box-shadow: none; padding: 0.5rem 0.25rem; }
	.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; display: flex; flex-direction: column; gap: 0.125rem; box-shadow: var(--shadow-sm); }
	.kpi-value { font-size: 1.75rem; font-weight: 800; color: var(--text); }
	.kpi-label { font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); }
	.kpi-delta { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); }
	.kpi-delta.up { color: var(--success); }
	.kpi-delta.down { color: var(--danger); }
	.preset-row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin: 0.75rem 0; }
	.advanced-panel { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; flex-basis: 100%; padding: 0.75rem; border: 1px dashed var(--border); border-radius: 8px; background: var(--bg-muted, transparent); }
	.advanced-toggle { justify-content: center; }
	.table-wrap { overflow-x: auto; margin-top: 1rem; }
	.pagination { display: flex; align-items: center; gap: 0.75rem; margin-top: 1rem; }
	table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
	th, td { text-align: left; padding: 0.625rem 0.5rem; border-bottom: 1px solid var(--divider); vertical-align: middle; }
	th { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
	.strong { font-weight: 700; }
	.link { background: none; border: none; padding: 0; color: var(--accent); font-size: 0.8125rem; font-weight: 600; cursor: pointer; }
	.link.strong { font-size: 0.875rem; font-weight: 700; }
	.link:hover { text-decoration: underline; }
	.trend { font-size: 1.125rem; font-weight: 700; color: var(--brand); }
	.th-btn { background: none; border: none; padding: 0; font: inherit; color: inherit; cursor: pointer; white-space: nowrap; }
	.th-btn:hover { color: var(--text-strong); }
	.th-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
	.error { color: var(--danger); font-size: 0.875rem; margin: 0; }
	.btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.625rem 1rem; border-radius: 8px; font-size: 0.875rem; font-weight: 600; font-family: inherit; cursor: pointer; white-space: nowrap; transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease; }
	.btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08); }
	.btn:active:not(:disabled) { transform: translateY(0); box-shadow: none; }
	.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.btn:disabled { opacity: 0.6; cursor: not-allowed; }
	.btn-primary { background: var(--brand); border: 1px solid var(--brand); color: var(--on-brand); }
	.btn-primary:hover:not(:disabled) { background: var(--brand-hover); }
	.btn-secondary { background: var(--bg-card); border: 1px solid var(--border-strong); color: var(--text-strong); }
	.btn-secondary:hover:not(:disabled) { background: var(--divider); }
	.btn-secondary.selected { border-color: var(--brand); background: var(--brand); color: var(--on-brand); }
	.btn-secondary.selected:hover:not(:disabled) { background: var(--brand-hover); border-color: var(--brand-hover); }
	.badge { display: inline-block; padding: 0.125rem 0.5rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); background: var(--divider); text-transform: capitalize; }
	.badge.status-present { color: var(--success); background: var(--success-bg); }
	.badge.status-late { color: var(--warning-text); background: var(--warning-bg); }
	.badge.status-excused { color: var(--accent); background: var(--accent-bg, var(--divider)); }
	.badge.status-rejected { color: var(--danger-strong); background: var(--danger-bg); }
	@media (max-width: 860px) { .filter-grid, .filter-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (max-width: 560px) { .filter-grid, .filter-grid-4 { grid-template-columns: minmax(0, 1fr); } }
	@media (max-width: 900px) { .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
	@media (max-width: 640px) { .card { padding: 1.25rem; } .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>