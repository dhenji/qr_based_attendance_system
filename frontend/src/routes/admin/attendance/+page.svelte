<script lang="ts">
	import { onMount } from 'svelte';
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
	import {
		listLivenessReview,
		resolveLivenessReview,
		type LivenessStatus,
	} from '$lib/features/admin/liveness/service';
	import type { LivenessReviewItemResponse } from '$lib/api/endpoints';
	import type { AdminCourse, AdminProfessor, AttendanceOverviewItemResponse } from '$lib/shared/types';
	import { formatPercentage } from '$lib/shared/utils/format';
	import { goto } from '$app/navigation';
	import { adminCourse } from '$lib/shared/constants/routes';

	// Admin Attendance Overview (wireframe 4.6): per-course sessions, average
	// rate, and trend arrow over Course / Professor / Date filters. Rows come
	// from GET /admin/attendance/overview (backend #138); mocks only when
	// PUBLIC_MOCK_MODE=true.

	type SortColumn = 'course' | 'sessions' | 'avg' | 'trend';

	let courseFilter = $state('');
	let professorFilter = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let sortBy = $state<SortColumn>('course');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let courseOptions = $state<AdminCourse[]>([]);
	let professorOptions = $state<AdminProfessor[]>([]);

	// Liveness review (flagged-scan queue): records whose face_match_score fell
	// in the review band stay actionable only while pending; resolving via the
	// buttons below approves (restores present/late) or rejects them.
	type Section = 'overview' | 'liveness';
	let section = $state<Section>('overview');
	let liveStatus = $state<LivenessStatus>('pending');
	let liveItems = $state<LivenessReviewItemResponse[]>([]);
	let liveTotal = $state(0);
	let liveLoading = $state(false);
	let liveError = $state<string | null>(null);
	let resolvingId = $state<number | null>(null);
	let reviewNote = $state('');

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
		await loadLiveness();
	});

	const loadLiveness = async () => {
		liveLoading = true;
		liveError = null;
		try {
			const response = await listLivenessReview({ status: liveStatus, page: 1, size: 20 });
			liveItems = response.items ?? [];
			liveTotal = response.total ?? liveItems.length;
		} catch (e) {
			liveError = e instanceof Error ? e.message : 'Could not load the review queue.';
		} finally {
			liveLoading = false;
		}
	};

	const resolveRow = async (id: number, decision: 'approve' | 'reject') => {
		if (resolvingId !== null) return;
		resolvingId = id;
		liveError = null;
		try {
			await resolveLivenessReview(id, decision, reviewNote);
			reviewNote = '';
			await loadLiveness();
		} catch (e) {
			liveError = e instanceof Error ? e.message : 'Could not resolve this record.';
		} finally {
			resolvingId = null;
		}
	};

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

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte).
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
			downloadCsv(filename, attendanceOverviewCsv(adminAttendanceState.items));
		}
	};
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

	<div class="tabs" role="tablist" aria-label="Attendance sections">
		<button
			class="tab"
			class:selected={section === 'overview'}
			role="tab"
			aria-selected={section === 'overview'}
			type="button"
			onclick={() => (section = 'overview')}
		>
			Overview
		</button>
		<button
			class="tab"
			class:selected={section === 'liveness'}
			role="tab"
			aria-selected={section === 'liveness'}
			type="button"
			onclick={() => (section = 'liveness')}
		>
			Liveness review{liveTotal > 0 ? ` (${liveTotal})` : ''}
		</button>
	</div>

	{#if section === 'liveness'}
		<section class="card filters" aria-label="Review filters">
			<select
				class="input"
				aria-label="Review status"
				bind:value={liveStatus}
				onchange={() => void loadLiveness()}
			>
				<option value="pending">Pending</option>
				<option value="approved">Approved</option>
				<option value="rejected">Rejected</option>
			</select>
			<input
				class="input"
				type="text"
				placeholder="Review note (optional, stored with the decision)"
				aria-label="Review note"
				bind:value={reviewNote}
				maxlength={1000}
			/>
			<button class="btn btn-secondary" onclick={() => void loadLiveness()}>Refresh</button>
		</section>

		{#if liveLoading && liveItems.length === 0}
			<section class="card"><p class="muted">Loading review queue…</p></section>
		{:else if liveError}
			<section class="card"><p class="error">{liveError}</p></section>
		{:else if liveItems.length === 0}
			<section class="card"><p class="empty">No {liveStatus} records in the review queue.</p></section>
		{:else}
			<section class="card table-wrap" aria-busy={liveLoading}>
				<table>
					<thead>
						<tr>
							<th>Student</th>
							<th>Session</th>
							<th>Score</th>
							<th>Scanned</th>
							{#if liveStatus === 'pending'}<th>Decision</th>{/if}
						</tr>
					</thead>
					<tbody>
						{#each liveItems as row (row.id)}
							<tr>
								<td>
									<span class="strong">{row.student_name}</span>
									<div class="muted small">{row.student_number} · {row.course_code}</div>
								</td>
								<td>{row.session_code}</td>
								<td>{row.face_match_score.toFixed(2)}</td>
								<td>{row.scanned_at.slice(0, 16).replace('T', ' ')}</td>
								{#if liveStatus === 'pending'}
									<td>
										<div class="row-actions">
											<button
												class="btn btn-secondary"
												type="button"
												disabled={resolvingId !== null}
												onclick={() => void resolveRow(row.id, 'approve')}
											>
												Approve
											</button>
											<button
												class="btn btn-secondary"
												type="button"
												disabled={resolvingId !== null}
												onclick={() => void resolveRow(row.id, 'reject')}
											>
												Reject
											</button>
										</div>
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</section>
		{/if}
	{:else}
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

	.tabs {
		display: flex;
		gap: 0.5rem;
	}

	.tab {
		padding: 0.625rem 1rem;
		border: 1px solid var(--border-strong);
		border-radius: 999px;
		background: var(--bg-card);
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.tab.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.row-actions {
		display: flex;
		gap: 0.5rem;
	}

	.strong {
		font-weight: 700;
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

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
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
