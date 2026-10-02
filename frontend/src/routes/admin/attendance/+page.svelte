<script lang="ts">
	import { onMount } from 'svelte';
	import {
		adminAttendanceState,
		initAttendanceOverview,
	} from '$lib/features/admin/analytics/store.svelte';
	import {
		attendanceOverviewCsv,
		downloadCsv,
	} from '$lib/features/admin/analytics/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listProfessors } from '$lib/features/admin/service';
	import type { AdminCourse, AdminProfessor, AttendanceOverviewItemResponse } from '$lib/shared/types';
	import { formatPercentage } from '$lib/shared/utils/format';
	import { goto } from '$app/navigation';
	import { adminCourse } from '$lib/shared/constants/routes';

	// Admin Attendance Overview (wireframe 4.6): per-course sessions, average
	// rate, and trend arrow over Course / Professor / Date filters. The
	// backend endpoint does not exist yet, so rows come from the
	// contract-shaped mock; the swap to the real backend stays mechanical.

	type SortColumn = 'course' | 'sessions' | 'avg' | 'trend';

	let courseFilter = $state('');
	let professorFilter = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let sortBy = $state<SortColumn>('course');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let courseOptions = $state<AdminCourse[]>([]);
	let professorOptions = $state<AdminProfessor[]>([]);

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

	onMount(async () => {
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
	});

	const applyFilters = () => {
		load();
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

	const trendLabel = (row: AttendanceOverviewItemResponse): string =>
		row.trend === 'up' ? 'Rising' : row.trend === 'down' ? 'Falling' : 'Flat';

	const onExport = () =>
		downloadCsv(
			`attendance-overview-${new Date().toISOString().slice(0, 10)}.csv`,
			attendanceOverviewCsv(adminAttendanceState.items)
		);
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Attendance Overview</h1>
			<p class="muted">Per-course sessions, average rate, and trend · {adminAttendanceState.items.length} courses</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" onclick={() => window.print()}>Print</button>
			<button class="btn btn-primary" data-testid="export-overview" onclick={onExport}>Export Overview</button>
		</div>
	</header>

	<section class="card filters" aria-label="Overview filters">
		<select class="input" aria-label="Course filter" bind:value={courseFilter} onchange={applyFilters}>
			<option value="">All courses</option>
			{#each courseOptions as c (c.id)}
				<option value={c.id}>{c.courseCode} — {c.courseName}</option>
			{/each}
		</select>
		<select class="input" aria-label="Professor filter" bind:value={professorFilter} onchange={applyFilters}>
			<option value="">All professors</option>
			{#each professorOptions as p (p.id)}
				<option value={p.id}>{p.firstName} {p.lastName}</option>
			{/each}
		</select>
		<input class="input" type="date" aria-label="From date" bind:value={dateFrom} />
		<input class="input" type="date" aria-label="To date" bind:value={dateTo} />
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminAttendanceState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminAttendanceState.error}
		<section class="card"><p class="error">Could not load overview: {adminAttendanceState.error}</p></section>
	{:else if visibleItems.length === 0}
		<section class="card">
			<p class="empty">No courses match these filters.</p>
		</section>
	{:else}
		<section class="card table-wrap">
			<table>
				<thead>
					<tr>
						<th><button class="th-btn" onclick={() => toggleSort('course')}>Course{sortArrow('course')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('sessions')}>Sessions{sortArrow('sessions')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('avg')}>Avg{sortArrow('avg')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('trend')}>Trend{sortArrow('trend')}</button></th>
					</tr>
				</thead>
				<tbody>
					{#each visibleItems as r (r.course_id)}
						<tr>
							<td><button class="link strong" onclick={() => goto(adminCourse(r.course_id))}>{r.course_code}</button><div class="muted small">{r.course_name}</div></td>
							<td>{r.sessions_count}</td>
							<td>{formatPercentage(r.avg_rate)}</td>
							<td title={trendLabel(r)}><span class="trend" aria-label={trendLabel(r)}>{trendGlyph(r)}</span></td>
						</tr>
					{/each}
				</tbody>
			</table>
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
		gap: 0.75rem;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
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

	.table-wrap {
		overflow-x: auto;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
