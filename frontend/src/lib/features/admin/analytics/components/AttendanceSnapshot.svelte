<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import {
		adminAttendanceState,
		initAttendanceOverview,
	} from '$lib/features/admin/analytics/store.svelte';
	import {
		attendanceOverviewCsv,
		downloadCsv,
		fetchAttendanceOverviewCsv,
	} from '$lib/features/admin/analytics/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listProfessors } from '$lib/features/admin/service';
	import type {
		AdminCourse,
		AdminProfessor,
		AttendanceOverviewItemResponse,
	} from '$lib/shared/types';
	import { formatPercentage } from '$lib/shared/utils/format';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { goto } from '$app/navigation';
	import { adminCourse } from '$lib/shared/constants/routes';

	// Per-course attendance snapshot (wireframe 4.6), rendered as the
	// "Attendance" tab of Analytics & Reports. Rows come from
	// GET /admin/attendance/overview (backend #138); mocks only when
	// PUBLIC_MOCK_MODE=true.
	//
	// It keeps its own Course/Professor/date filter row: the analytics rail's
	// Program → Year → Term axis is a different slice of the data, and the
	// professor filter has no equivalent there.

	type SortColumn = 'course' | 'sessions' | 'avg' | 'trend';

	let courseFilter = $state('');
	let professorFilter = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let sortBy = $state<SortColumn>('course');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let courseOptions = $state<AdminCourse[]>([]);
	let professorOptions = $state<AdminProfessor[]>([]);
	let filterNotice = $state<string | null>(null);
	let exportNote = $state<string | null>(null);

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

	const load = () =>
		initAttendanceOverview({
			course_id: courseFilter ? Number(courseFilter) : undefined,
			professor_id: professorFilter ? Number(professorFilter) : undefined,
			date_from: dateFrom.trim() || undefined,
			date_to: dateTo.trim() || undefined,
		});

	// alive-guard for the async onMount below: if the tab unmounts while the
	// lookups/first page are still loading, destroy has already run and the
	// entity/focus subscriptions must never attach afterwards.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		for (const stop of autoRefreshStops) stop();
	});

	const reloadCourseLookups = async () => {
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
		}
	};

	const reloadProfessorLookups = async () => {
		try {
			professorOptions = (await listProfessors({ page: 1, size: 100 })).items;
		} catch {
			professorOptions = [];
		}
	};

	// Aggregate view: no entity subscriptions on the rows — the snapshot is a
	// point-in-time report. Tab focus re-runs it with current filters (skipped
	// while loading); lookup entities reload picker options only.
	const refreshVisible = () => {
		if (adminAttendanceState.loading) return;
		void load();
	};

	onMount(async () => {
		try {
			courseOptions = (await listCourses({ page: 1, size: 100 })).items;
		} catch {
			courseOptions = [];
			filterNotice = 'Some filters failed to load — lists may be incomplete.';
		}
		try {
			professorOptions = (await listProfessors({ page: 1, size: 100 })).items;
		} catch {
			professorOptions = [];
			filterNotice = 'Some filters failed to load — lists may be incomplete.';
		}
		await load();
		if (!pageAlive) return;
		autoRefreshStops.push(
			subscribeEntity('courses', () => void reloadCourseLookups()),
			subscribeEntity('professors', () => void reloadProfessorLookups()),
			onFocusRevalidate(refreshVisible)
		);
	});

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

	// Sort state for assistive tech, mirroring the professor ledger pattern.
	const sortLabel = (column: SortColumn, label: string): string => {
		if (sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: SortColumn): 'ascending' | 'descending' | 'none' =>
		sortBy === column ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none';

	const trendGlyph = (row: AttendanceOverviewItemResponse): string =>
		row.trend === 'up' ? '↑' : row.trend === 'down' ? '↓' : '→';

	const trendLabel = (row: AttendanceOverviewItemResponse): string =>
		row.trend === 'up' ? 'Rising' : row.trend === 'down' ? 'Falling' : 'Flat';

	// Server-first export (GET /admin/attendance/overview/export) with the
	// active filters, so the download matches the on-screen table. Mock mode
	// and unreachable backends fall back to the client-side aggregate CSV.
	const onExport = async () => {
		const filename = `attendance-overview-${new Date().toISOString().slice(0, 10)}.csv`;
		exportNote = null;
		try {
			downloadCsv(
				filename,
				await fetchAttendanceOverviewCsv({
					course_id: courseFilter ? Number(courseFilter) : undefined,
					professor_id: professorFilter ? Number(professorFilter) : undefined,
					date_from: dateFrom.trim() || undefined,
					date_to: dateTo.trim() || undefined,
				})
			);
		} catch {
			exportNote = 'Server export unavailable — downloaded the on-screen rows instead.';
			downloadCsv(filename, attendanceOverviewCsv(adminAttendanceState.items));
		}
	};
</script>

<section class="card">
	<div class="row-head">
		<div>
			<h2 class="card-title">Attendance snapshot</h2>
			<p class="muted">
				Per-course sessions, average rate, and trend · {adminAttendanceState.items.length} courses
			</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" onclick={() => window.print()}>Print</button>
			<button class="btn btn-primary" data-testid="export-overview" onclick={onExport}>
				Export Overview
			</button>
		</div>
	</div>

	{#if exportNote}
		<p class="muted" role="status">{exportNote}</p>
	{/if}

	<div class="filters" aria-label="Attendance snapshot filters">
		<select class="input" aria-label="Course filter" bind:value={courseFilter} onchange={load}>
			<option value="">All courses</option>
			{#each courseOptions as c (c.id)}
				<option value={c.id}>{c.courseCode} — {c.courseName}</option>
			{/each}
		</select>
		<select
			class="input"
			aria-label="Professor filter"
			bind:value={professorFilter}
			onchange={load}
		>
			<option value="">All professors</option>
			{#each professorOptions as p (p.id)}
				<option value={p.id}>{p.firstName} {p.lastName}</option>
			{/each}
		</select>
		<input class="input" type="date" aria-label="From date" bind:value={dateFrom} />
		<input class="input" type="date" aria-label="To date" bind:value={dateTo} />
		<button class="btn btn-secondary" data-testid="apply" onclick={load}>Apply</button>
		{#if filterNotice}
			<p class="muted" role="status">{filterNotice}</p>
		{/if}
	</div>
</section>

{#if adminAttendanceState.loading && adminAttendanceState.items.length === 0}
	<section class="card"><p class="muted">Loading…</p></section>
{:else if adminAttendanceState.error}
	<section class="card"><p class="error">Could not load overview: {adminAttendanceState.error}</p></section>
{:else if visibleItems.length === 0}
	<section class="card">
		<p class="empty">No courses match these filters.</p>
	</section>
{:else}
	<section class="card table-wrap" aria-busy={adminAttendanceState.loading}>
		<table>
			<thead>
				<tr>
					<th scope="col" aria-sort={ariaSort('course')}>
						<button class="th-btn" type="button" onclick={() => toggleSort('course')} aria-label={sortLabel('course', 'Course')}>
							Course<span aria-hidden="true">{sortArrow('course')}</span>
						</button>
					</th>
					<th scope="col" aria-sort={ariaSort('sessions')}>
						<button class="th-btn" type="button" onclick={() => toggleSort('sessions')} aria-label={sortLabel('sessions', 'Sessions')}>
							Sessions<span aria-hidden="true">{sortArrow('sessions')}</span>
						</button>
					</th>
					<th scope="col" aria-sort={ariaSort('avg')}>
						<button class="th-btn" type="button" onclick={() => toggleSort('avg')} aria-label={sortLabel('avg', 'Average rate')}>
							Avg<span aria-hidden="true">{sortArrow('avg')}</span>
						</button>
					</th>
					<th scope="col" aria-sort={ariaSort('trend')}>
						<button class="th-btn" type="button" onclick={() => toggleSort('trend')} aria-label={sortLabel('trend', 'Trend')}>
							Trend<span aria-hidden="true">{sortArrow('trend')}</span>
						</button>
					</th>
				</tr>
			</thead>
			<tbody>
				{#each visibleItems as r (r.course_id)}
					<tr>
						<td><button class="link strong" onclick={() => goto(adminCourse(r.course_id))}>{r.course_code}</button><div class="muted small">{r.course_name}</div></td>
						<td>{r.sessions_count}</td>
						<td>{formatPercentage(r.avg_rate * 100)}</td>
						<td title={trendLabel(r)}><span class="trend" aria-label={trendLabel(r)}>{trendGlyph(r)}</span></td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{/if}

<style>
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

	.row-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.muted.small {
		font-size: 0.75rem;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
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

	.strong {
		font-weight: 700;
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
	}

	.link.strong {
		font-size: 0.875rem;
		font-weight: 700;
	}

	.trend {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--brand);
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

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
