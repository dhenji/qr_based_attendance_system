<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { initProfessorCourses, professorState } from '$lib/features/professor/store.svelte';
	import { listSessions } from '$lib/features/session/service';
	import {
		Routes,
		professorActiveSession,
		professorSessionCreate
	} from '$lib/shared/constants/routes';
	import { formatDate } from '$lib/shared/utils/format';

	type SessionSummary = Awaited<ReturnType<typeof listSessions>>['items'][number];

	type SortKey = 'date' | 'code' | 'course' | 'pla';
	type SortDirection = 'asc' | 'desc';

	let summaries = $state<SessionSummary[] | null>(null);
	let loadError = $state<string | null>(null);
	let offeringFilter = $state<number | null>(null);
	let refreshing = $state(false);
	let sortKey = $state<SortKey>('date');
	let sortDirection = $state<SortDirection>('desc');

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric'
		})
	);

	const filtered = $derived.by(() => {
		if (!summaries) return [];
		const rows =
			offeringFilter === null
				? [...summaries]
				: summaries.filter((session) => session.offeringId === offeringFilter);
		const direction = sortDirection === 'asc' ? 1 : -1;
		rows.sort((a, b) => {
			switch (sortKey) {
				case 'code':
					return a.sessionCode.localeCompare(b.sessionCode) * direction;
				case 'course':
					return (
						(a.courseCode.localeCompare(b.courseCode) ||
							a.createdAt.localeCompare(b.createdAt)) *
						direction
					);
				case 'pla':
					return (
						(a.presentCount - b.presentCount ||
							a.lateCount - b.lateCount ||
							a.createdAt.localeCompare(b.createdAt)) *
						direction
					);
				case 'date':
				default:
					return a.createdAt.localeCompare(b.createdAt) * direction;
			}
		});
		return rows;
	});

	const activeSessions = $derived(filtered.filter((session) => session.status === 'active'));
	const recentSessions = $derived(filtered.filter((session) => session.status !== 'active'));

	const load = async () => {
		refreshing = true;
		try {
			const result = await listSessions();
			summaries = result.items;
			loadError = null;
		} catch {
			loadError = 'Sessions could not be loaded.';
		} finally {
			refreshing = false;
		}
	};

	onMount(() => {
		void initProfessorCourses();
		void load();
	});

	const viewLive = (id: number) => void goto(professorActiveSession(id));
	const goCreate = () => void goto(Routes.PROFESSOR_SESSIONS_CREATE);
	const goHistory = () => void goto(Routes.PROFESSOR_SESSIONS_HISTORY);

	const setSort = (key: SortKey) => {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			// Dates read newest-first; everything else reads A-to-Z / low-to-high.
			sortDirection = key === 'date' ? 'desc' : 'asc';
		}
	};

	const sortArrow = (key: SortKey): string => {
		if (sortKey !== key) return '↕';
		return sortDirection === 'asc' ? '▲' : '▼';
	};

	const sortLabel = (key: SortKey, label: string): string => {
		if (sortKey !== key) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDirection === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (key: SortKey): 'ascending' | 'descending' | 'none' => {
		if (sortKey !== key) return 'none';
		return sortDirection === 'asc' ? 'ascending' : 'descending';
	};

	const plaText = (session: SessionSummary): string =>
		`${session.presentCount} / ${session.lateCount} / ${session.absentCount}`;
</script>

<div class="sessions">
	<header class="header">
		<div>
			<h1>Sessions</h1>
			<p class="muted">{today}</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" type="button" onclick={goHistory}>
				<AppIcon name="file" size={18} />
				History
			</button>
			<button class="btn btn-primary" type="button" onclick={goCreate}>
				<AppIcon name="plus" size={18} />
				New Session
			</button>
		</div>
	</header>

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void load()}>
				Try again
			</button>
		</section>
	{:else if !summaries}
		<section class="card">
			<p class="muted">Loading sessions…</p>
		</section>
	{:else}
		<section aria-label="Active sessions">
			<h2 class="section-title">Active now</h2>
			{#if activeSessions.length === 0}
				<div class="card">
					<p class="empty">
						No active session right now. Open one from
						<button class="link" type="button" onclick={goCreate}>New Session</button>
						and it will appear here with its projector code.
					</p>
				</div>
			{:else}
				<div class="active-grid">
					{#each activeSessions as session (session.id)}
						<article class="card active-card">
							<span class="code-label">Live · Show on projector</span>
							<span class="code">{session.sessionCode}</span>
							<p class="active-meta">
								{session.courseCode} — {session.courseName} · Section {session.section}
							</p>
							<p class="muted">
								Present {session.presentCount} · Late {session.lateCount} · Absent {session.absentCount}
							</p>
							<button class="btn btn-primary" type="button" onclick={() => viewLive(session.id)}>
								<AppIcon name="qr" size={18} />
								View live
							</button>
						</article>
					{/each}
				</div>
			{/if}
		</section>

		<section aria-label="Recent sessions">
			<div class="section-head">
				<h2 class="section-title">Recent sessions</h2>
				<div class="filter-row">
					<label class="form-label" for="offering-filter">Course</label>
					<select
						id="offering-filter"
						class="form-input"
						value={offeringFilter ?? ''}
						onchange={(e) => {
							const raw = e.currentTarget.value;
							offeringFilter = raw === '' ? null : Number(raw);
						}}
					>
						<option value="">All courses</option>
						{#each professorState.courses as course (course.offeringId)}
							<option value={course.offeringId}>
								{course.courseCode} · Section {course.sections.length > 0 ? course.sections.join(', ') : '—'}
							</option>
						{/each}
					</select>
					<button
						class="btn btn-ghost"
						type="button"
						disabled={refreshing}
						onclick={() => void load()}
					>
						{refreshing ? 'Refreshing…' : 'Refresh'}
					</button>
				</div>
			</div>

			{#if filtered.length === 0}
				<div class="card">
					<p class="empty">No sessions yet for this filter. Open one above.</p>
				</div>
			{:else}
				<div class="card table-card">
					<div class="table-wrap" role="region" aria-label="Recent sessions">
						<table>
							<thead>
								<tr>
									<th scope="col" aria-sort={ariaSort('date')}>
										<button
											class="sort"
											type="button"
											onclick={() => setSort('date')}
											aria-label={sortLabel('date', 'Date')}
										>
											<span>Date</span>
											<span class="sort-arrow" class:active={sortKey === 'date'} aria-hidden="true">
												{sortArrow('date')}
											</span>
										</button>
									</th>
									<th scope="col" aria-sort={ariaSort('code')}>
										<button
											class="sort"
											type="button"
											onclick={() => setSort('code')}
											aria-label={sortLabel('code', 'Code')}
										>
											<span>Code</span>
											<span class="sort-arrow" class:active={sortKey === 'code'} aria-hidden="true">
												{sortArrow('code')}
											</span>
										</button>
									</th>
									<th scope="col" aria-sort={ariaSort('course')}>
										<button
											class="sort"
											type="button"
											onclick={() => setSort('course')}
											aria-label={sortLabel('course', 'Course')}
										>
											<span>Course</span>
											<span class="sort-arrow" class:active={sortKey === 'course'} aria-hidden="true">
												{sortArrow('course')}
											</span>
										</button>
									</th>
									<th scope="col" aria-sort={ariaSort('pla')}>
										<button
											class="sort"
											type="button"
											onclick={() => setSort('pla')}
											aria-label={sortLabel('pla', 'Present / Late / Absent')}
										>
											<span>P / L / A</span>
											<span class="sort-arrow" class:active={sortKey === 'pla'} aria-hidden="true">
												{sortArrow('pla')}
											</span>
										</button>
									</th>
									<th scope="col">Status</th>
									<th scope="col"><span class="sr-only">Action</span></th>
								</tr>
							</thead>
							<tbody>
								{#each recentSessions as session (session.id)}
									<tr>
										<td>{formatDate(session.createdAt)}</td>
										<td class="mono">{session.sessionCode}</td>
										<td>
											<div class="course-name">{session.courseCode}</div>
											<div class="course-sub">Section {session.section}</div>
										</td>
										<td class="numeric">{plaText(session)}</td>
										<td><span class="status status-{session.status}">{session.status}</span></td>
										<td>
											<button
												class="mini"
												type="button"
												onclick={() => viewLive(session.id)}
												aria-label={`View session ${session.sessionCode}`}
											>
												View
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="hint">
						Showing {filtered.length}
						{filtered.length === 1 ? 'session' : 'sessions'} · full filterable history lives under
						<button class="link" type="button" onclick={goHistory}>History</button>.
					</p>
				</div>
			{/if}
		</section>
	{/if}
</div>

<style>
	.sessions {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
		font-family: system-ui, sans-serif;
	}

	.header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		margin: 0;
		color: #64748b;
		font-size: 0.875rem;
	}

	.header-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.section-title {
		margin: 0 0 0.75rem;
		font-size: 1rem;
		font-weight: 700;
		color: #1e293b;
	}

	.section-head {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.section-head .section-title {
		margin: 0;
	}

	.filter-row {
		display: flex;
		align-items: flex-end;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 12px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.empty {
		margin: 0;
		color: #64748b;
		font-size: 0.9375rem;
	}

	.error {
		margin: 0 0 1rem;
		color: #b91c1c;
		font-weight: 600;
	}

	.active-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
		gap: 1rem;
	}

	.active-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		text-align: center;
		background: linear-gradient(135deg, #f0fdf4, #dcfce7);
		border: 2px solid #22c55e;
		container-type: inline-size;
	}

	.code-label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: #15803d;
	}

	.code {
		font-family: 'JetBrains Mono', monospace;
		font-size: min(2.5rem, 16cqw);
		font-weight: 700;
		letter-spacing: 0.12em;
		line-height: 1;
		color: #14532d;
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	.active-meta {
		margin: 0;
		font-weight: 600;
		color: #14532d;
		font-size: 0.9375rem;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.7rem 1.2rem;
		border-radius: 8px;
		border: 1px solid transparent;
		font: inherit;
		font-size: 0.9375rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn:focus-visible,
	.mini:focus-visible,
	.link:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn-primary {
		background: #1e3a5f;
		border-color: #1e3a5f;
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: #16324f;
	}

	.btn-secondary {
		background: white;
		border-color: #cbd5e1;
		color: #0f172a;
	}

	.btn-ghost {
		background: white;
		border-color: #cbd5e1;
		color: #0f172a;
		padding: 0.5rem 0.9rem;
		font-size: 0.875rem;
	}

	.btn:disabled {
		background: #f8fafc;
		border-color: #e2e8f0;
		color: #94a3b8;
		cursor: not-allowed;
	}

	.link {
		padding: 0;
		border: none;
		background: none;
		color: #2563eb;
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		text-decoration: underline;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: #334155;
	}

	.form-input {
		padding: 0.5rem 0.625rem;
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font-size: 0.875rem;
		font-family: inherit;
		color: #0f172a;
		background: white;
		max-width: 16rem;
	}

	.table-card {
		padding: 0;
		overflow: hidden;
	}

	.table-card .hint {
		padding: 0 1.5rem 1.25rem;
	}

	.table-wrap {
		overflow: auto;
	}

	table {
		width: 100%;
		min-width: 640px;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid #f1f5f9;
		vertical-align: middle;
		color: #0f172a;
	}

	thead th {
		background: #f8fafc;
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #64748b;
	}

	.sort {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.375rem;
		margin: -0.25rem -0.375rem;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: inherit;
		font: inherit;
		letter-spacing: inherit;
		text-transform: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.sort:hover {
		background: #eef2f7;
		color: #0f172a;
	}

	.sort:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
	}

	.sort-arrow {
		color: #94a3b8;
		font-size: 0.6875rem;
	}

	.sort-arrow.active {
		color: #1e3a5f;
	}

	tbody tr:last-child td {
		border-bottom: none;
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-weight: 600;
		letter-spacing: 0.06em;
	}

	.numeric {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	.course-name {
		font-weight: 600;
	}

	.course-sub {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.status {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.status-active {
		background: #dcfce7;
		color: #15803d;
	}

	.status-closed {
		background: #f1f5f9;
		color: #64748b;
	}

	.mini {
		padding: 0.375rem 0.75rem;
		border-radius: 999px;
		border: 1px solid #cbd5e1;
		background: white;
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: #0f172a;
		cursor: pointer;
	}

	.mini:hover {
		background: #f1f5f9;
	}

	.hint {
		margin: 1rem 0 0;
		font-size: 0.8125rem;
		color: #64748b;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}

	@media (max-width: 640px) {
		.header-actions .btn {
			flex: 1 1 auto;
		}

		.code {
			letter-spacing: 0.06em;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.btn,
		.mini {
			transition: none;
		}
	}
</style>
