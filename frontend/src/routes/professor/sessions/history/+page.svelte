<script lang="ts">
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
	import {
		buildCsv,
		defaultReportRange,
		getReportFilterOptions
	} from '$lib/features/report/service';
	import {
		listSessionHistory,
		type SessionHistorySortBy,
		type SessionHistorySortDir
	} from '$lib/features/session/service';
	import { professorActiveSession } from '$lib/shared/constants/routes';
	import { formatDate, formatPercentage } from '$lib/shared/utils/format';

	type HistoryRow = Awaited<ReturnType<typeof listSessionHistory>>['items'][number];

	const PAGE_SIZE = 10;

	const filterOptions = getReportFilterOptions();
	const initialRange = defaultReportRange();

	let course = $state('All');
	let section = $state('All');
	let from = $state(initialRange.from);
	let to = $state(initialRange.to);
	let sortBy = $state<SessionHistorySortBy>('date');
	let sortDir = $state<SessionHistorySortDir>('desc');
	let currentPage = $state(1);
	let rows = $state<HistoryRow[]>([]);
	let total = $state(0);
	let avgCompliance = $state(0);
	let totalSessions = $state(0);
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);
	let exporting = $state(false);

	// Sections narrow to the selected course so the filter cannot select a
	// section the course is never taught in.
	const availableSections = $derived(
		course === 'All'
			? filterOptions.sections
			: [
					...new Set(
						PROFESSOR_COURSES.filter((item) => item.courseCode === course).map(
							(item) => item.section
						)
					)
				]
	);

	$effect(() => {
		if (section !== 'All' && !availableSections.includes(section)) {
			section = 'All';
			currentPage = 1;
		}
	});

	$effect(() => {
		const query = {
			course: course === 'All' ? undefined : course,
			section: section === 'All' ? undefined : section,
			from: from || undefined,
			to: to || undefined,
			sortBy,
			sortDir,
			page: currentPage,
			size: PAGE_SIZE
		};
		reloadToken;

		let cancelled = false;
		isLoading = true;
		loadError = null;

		const load = async () => {
			try {
				const result = await listSessionHistory(query);
				if (cancelled) return;
				rows = result.items;
				total = result.total;
				avgCompliance = result.avg_compliance;
				totalSessions = result.total_sessions;
				// The service clamps out-of-range pages (e.g. filters shrank the
				// result under us); follow it so the pager never points nowhere.
				if (result.page !== currentPage) currentPage = result.page;
			} catch {
				if (!cancelled) loadError = 'Session history could not be loaded.';
			} finally {
				if (!cancelled) isLoading = false;
			}
		};

		void load();
		return () => {
			cancelled = true;
		};
	});

	const pageCount = $derived(Math.max(1, Math.ceil(total / PAGE_SIZE)));
	const pageNumbers = $derived(Array.from({ length: pageCount }, (_, index) => index + 1));
	const rangeText = $derived.by(() => {
		if (total === 0) return '0 of 0 sessions';
		const start = (currentPage - 1) * PAGE_SIZE + 1;
		const end = Math.min(currentPage * PAGE_SIZE, total);
		return `${start}–${end} of ${total} sessions`;
	});

	const setSort = (key: SessionHistorySortBy) => {
		if (sortBy === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortBy = key;
			// Dates read newest-first; everything else reads A-to-Z / low-to-high.
			sortDir = key === 'date' ? 'desc' : 'asc';
		}
		currentPage = 1;
	};

	const sortArrow = (key: SessionHistorySortBy): string => {
		if (sortBy !== key) return '↕';
		return sortDir === 'asc' ? '▲' : '▼';
	};

	const sortLabel = (key: SessionHistorySortBy, label: string): string => {
		if (sortBy !== key) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (key: SessionHistorySortBy): 'ascending' | 'descending' | 'none' => {
		if (sortBy !== key) return 'none';
		return sortDir === 'asc' ? 'ascending' : 'descending';
	};

	const resetFilters = () => {
		course = 'All';
		section = 'All';
		from = initialRange.from;
		to = initialRange.to;
		currentPage = 1;
	};

	const viewDetail = (id: number) => void goto(professorActiveSession(id));

	const exportCsv = async () => {
		if (exporting) return;
		exporting = true;
		try {
			const result = await listSessionHistory({
				course: course === 'All' ? undefined : course,
				section: section === 'All' ? undefined : section,
				from: from || undefined,
				to: to || undefined,
				sortBy,
				sortDir,
				page: 1,
				size: 10000
			});
			const csv = buildCsv(
				[
					'Date',
					'Session code',
					'Course',
					'Section',
					'Present',
					'Late',
					'Absent',
					'Enrolled',
					'Compliance %',
					'Participation %'
				],
				result.items.map((row) => [
					row.created_at.slice(0, 10),
					row.session_code,
					row.course_code,
					row.section,
					row.present_count,
					row.late_count,
					row.absent_count,
					row.enrolled_count,
					Math.round(row.compliance_rate * 100),
					Math.round(row.participation_rate * 100)
				])
			);
			const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = `session-history-${to || initialRange.to}.csv`;
			document.body.appendChild(anchor);
			anchor.click();
			anchor.remove();
			URL.revokeObjectURL(url);
		} finally {
			exporting = false;
		}
	};

	const print = () => window.print();

	const plaText = (row: HistoryRow): string =>
		`${row.present_count} / ${row.late_count} / ${row.absent_count}`;

	const rateTitle = (row: HistoryRow): string =>
		`Compliance: present / total. Participation: ${formatPercentage(row.participation_rate * 100)} (present + late + excused) / total.`;
</script>

<div class="history">
	<header class="header">
		<div>
			<h1>Session History</h1>
			<p class="muted">Past sessions across your courses · {rangeText}</p>
		</div>
	</header>

	<section class="card filters no-print" aria-label="History filters">
		<div class="filter-grid">
			<div class="field">
				<label class="form-label" for="course">Course</label>
				<select
					id="course"
					class="form-input"
					bind:value={course}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">All courses</option>
					{#each filterOptions.courses as option (option.code)}
						<option value={option.code}>{option.code} — {option.name}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="section">Section</label>
				<select
					id="section"
					class="form-input"
					bind:value={section}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">All sections</option>
					{#each availableSections as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="from">From</label>
				<input
					id="from"
					class="form-input"
					type="date"
					bind:value={from}
					onchange={() => (currentPage = 1)}
				/>
			</div>
			<div class="field">
				<label class="form-label" for="to">To</label>
				<input
					id="to"
					class="form-input"
					type="date"
					bind:value={to}
					onchange={() => (currentPage = 1)}
				/>
			</div>
		</div>
		<div class="filter-actions">
			<button class="btn btn-ghost" type="button" onclick={resetFilters}>Reset filters</button>
		</div>
	</section>

	{#if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => (reloadToken += 1)}>
				Try again
			</button>
		</section>
	{:else if isLoading && rows.length === 0}
		<section class="card">
			<p class="muted">Loading session history…</p>
		</section>
	{:else if rows.length === 0}
		<section class="card">
			<p class="empty">No sessions match these filters. Try widening the date range.</p>
		</section>
	{:else}
		<section class="card table-card" aria-label="Session history table">
			<div class="table-wrap" role="region" aria-label="Session history">
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
									<span class="sort-arrow" class:active={sortBy === 'date'} aria-hidden="true">
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
									<span class="sort-arrow" class:active={sortBy === 'code'} aria-hidden="true">
										{sortArrow('code')}
									</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('section')}>
								<button
									class="sort"
									type="button"
									onclick={() => setSort('section')}
									aria-label={sortLabel('section', 'Section')}
								>
									<span>Section</span>
									<span class="sort-arrow" class:active={sortBy === 'section'} aria-hidden="true">
										{sortArrow('section')}
									</span>
								</button>
							</th>
							<th scope="col">P / L / A</th>
							<th scope="col" aria-sort={ariaSort('rate')}>
								<button
									class="sort"
									type="button"
									onclick={() => setSort('rate')}
									aria-label={sortLabel('rate', 'Rate')}
								>
									<span>Rate</span>
									<span class="sort-arrow" class:active={sortBy === 'rate'} aria-hidden="true">
										{sortArrow('rate')}
									</span>
								</button>
							</th>
							<th scope="col"><span class="sr-only">Action</span></th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.id)}
							<tr>
								<td>{formatDate(row.created_at)}</td>
								<td class="mono">{row.session_code}</td>
								<td>
									<div class="course-name">{row.course_code}</div>
									<div class="course-sub">Section {row.section}</div>
								</td>
								<td class="numeric">{plaText(row)}</td>
								<td>
									<button
										class="rate"
										type="button"
										title={rateTitle(row)}
										aria-label={`Compliance ${formatPercentage(row.compliance_rate * 100)}, participation ${formatPercentage(row.participation_rate * 100)}`}
									>
										{formatPercentage(row.compliance_rate * 100)}
									</button>
								</td>
								<td>
									<button
										class="mini"
										type="button"
										onclick={() => viewDetail(row.id)}
										aria-label={`View detail for session ${row.session_code}`}
									>
										View
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="table-foot">
				<p class="average">
					Average: {formatPercentage(avgCompliance * 100)} over {totalSessions}
					{totalSessions === 1 ? 'session' : 'sessions'}
				</p>
				<nav class="pages no-print" aria-label="History pages">
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = Math.max(1, currentPage - 1))}
						aria-label="Go to previous history page"
					>
						Previous
					</button>
					{#each pageNumbers as pageNumber (pageNumber)}
						<button
							class="page"
							class:current={pageNumber === currentPage}
							type="button"
							disabled={pageNumber === currentPage}
							onclick={() => (currentPage = pageNumber)}
							aria-label={`Go to history page ${pageNumber}`}
							aria-current={pageNumber === currentPage ? 'page' : undefined}
						>
							{pageNumber}
						</button>
					{/each}
					<button
						class="page"
						type="button"
						disabled={currentPage >= pageCount}
						onclick={() => (currentPage = Math.min(pageCount, currentPage + 1))}
						aria-label="Go to next history page"
					>
						Next
					</button>
				</nav>
				<div class="table-actions no-print">
					<button class="btn btn-secondary" type="button" onclick={print}>
						<AppIcon name="file" size={18} />
						Print
					</button>
					<button
						class="btn btn-secondary"
						type="button"
						disabled={exporting || total === 0}
						onclick={() => void exportCsv()}
					>
						<AppIcon name="file" size={18} />
						{exporting ? 'Exporting…' : 'Export CSV'}
					</button>
				</div>
			</div>
		</section>
	{/if}
</div>

<style>
	.history {
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
		font-weight: 700;
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		margin: 0;
		color: #64748b;
		font-size: 0.875rem;
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

	.filter-grid {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1rem;
	}

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
		color: #334155;
	}

	.form-input {
		padding: 0.625rem 0.75rem;
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #0f172a;
		background: white;
		width: 100%;
	}

	.form-input:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
		border-color: #2563eb;
	}

	.filter-actions {
		display: flex;
		justify-content: flex-end;
		margin-top: 1rem;
	}

	.table-card {
		padding: 0;
		overflow: hidden;
	}

	.table-wrap {
		overflow: auto;
	}

	table {
		width: 100%;
		min-width: 680px;
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

	tbody tr:last-child td {
		border-bottom: none;
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

	.sort:focus-visible,
	.mini:focus-visible,
	.btn:focus-visible,
	.rate:focus-visible {
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

	/* D36: compliance by default; the title/aria-label reveals participation. */
	.rate {
		display: inline-block;
		padding: 0;
		border: none;
		border-bottom: 1px dotted #94a3b8;
		background: none;
		font: inherit;
		font-variant-numeric: tabular-nums;
		font-weight: 700;
		color: #1e3a5f;
		cursor: help;
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

	.table-foot {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		padding: 1.25rem 1.5rem;
		border-top: 1px solid #f1f5f9;
	}

	.average {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 600;
		color: #334155;
	}

	.pages {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
	}

	.page {
		min-width: 2.375rem;
		padding: 0.4375rem 0.625rem;
		border-radius: 8px;
		border: 1px solid #cbd5e1;
		background: white;
		color: #0f172a;
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.page:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.page:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
	}

	.page.current {
		background: #1e3a5f;
		border-color: #1e3a5f;
		color: white;
	}

	.page:disabled:not(.current) {
		color: #94a3b8;
		background: #f8fafc;
		border-color: #e2e8f0;
		cursor: not-allowed;
	}

	.table-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
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

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}

	@media (max-width: 860px) {
		.filter-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 560px) {
		.filter-grid {
			grid-template-columns: minmax(0, 1fr);
		}

		.table-actions .btn {
			flex: 1 1 auto;
		}
	}

	@media print {
		.no-print {
			display: none;
		}

		.history {
			max-width: none;
		}

		.card {
			box-shadow: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.btn,
		.mini,
		.page {
			transition: none;
		}
	}
</style>
