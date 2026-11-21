<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
import ConfirmExportDialog from '$lib/components/ConfirmExportDialog.svelte';
	import {
		buildCsv,
		defaultReportRange
	} from '$lib/features/report/service';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import {
		listSessionHistory,
		type SessionHistorySortBy,
		type SessionHistorySortDir
	} from '$lib/features/session/service';
	import { professorActiveSession } from '$lib/shared/constants/routes';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';
	import { formatDate, formatPercentage } from '$lib/shared/utils/format';
	import { downloadTextFile } from '$lib/shared/utils/file';
	import { debounce } from '$lib/shared/utils/debounce';

	type HistoryRow = Awaited<ReturnType<typeof listSessionHistory>>['items'][number];

	const PAGE_SIZE = 10;

	const initialRange = defaultReportRange();

	onMount(() => {
		initProfessorCourses();
	});

	let course = $state('All');
	let section = $state('All');
	let sessionType = $state<'All' | 'lecture' | 'lab'>('All');
	let statusFilter = $state<'All' | 'scheduled' | 'active' | 'closed'>('All');
	let searchInput = $state('');
	let searchQuery = $state('');
	let from = $state('');
	let to = $state('');
	let sortBy = $state<SessionHistorySortBy>('date');
	let sortDir = $state<SessionHistorySortDir>('desc');
	let currentPage = $state(1);
	let rows = $state<HistoryRow[]>([]);
	let total = $state(0);
	let avgCompliance = $state(0);
	let totalSessions = $state(0);
	let avgScope = $state<'page' | 'filtered'>('page');
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);
	let exportWarning = $state<string | null>(null);
	let exportProgress = $state<string | null>(null);
	let exportToken = $state(0);
	let pendingExport = $state<null | {
		run: () => void | Promise<void>;
		details?: { label: string; value: string }[];
		title?: string;
		message?: string;
		confirmLabel?: string;
		busyLabel?: string;
		onabort?: () => void;
	}>(null);

	// Course options deduped by code; sections join from the live courses
	// store (the history rows carry no section identity of their own, and the
	// backend sorts date/code/rate only — hence no section sort header).
	const courseOptions = $derived(
		[...new Map(professorState.courses.map((item) => [item.courseCode, item.courseName])).entries()].map(
			([code, name]) => ({ code, name })
		)
	);

	// Sections narrow to the selected course so the filter cannot select a
	// section the course is never taught in.
	const availableSections = $derived([
		...new Set(
			professorState.courses
				.filter((item) => course === 'All' || item.courseCode === course)
				.flatMap((item) => item.sections)
		)
	]);

	$effect(() => {
		if (section !== 'All' && !availableSections.includes(section)) {
			section = 'All';
			currentPage = 1;
		}
	});

	const searchDebounced = debounce((value: string) => {
		searchQuery = value;
		currentPage = 1;
	});

	$effect(() => {
		searchDebounced(searchInput);
		return () => searchDebounced.cancel();
	});

	$effect(() => {
		const query = {
			course: course === 'All' ? undefined : course,
			section: section === 'All' ? undefined : section,
			sessionType: sessionType === 'All' ? undefined : sessionType,
			status: statusFilter === 'All' ? undefined : statusFilter,
			search: searchQuery || undefined,
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
				avgScope = result.avg_scope;
				// The service clamps out-of-range pages (e.g. filters shrank the
				// result under us); follow it so the pager never points nowhere.
				if (result.page !== currentPage) currentPage = result.page;
			} catch (e) {
				if (!cancelled)
					loadError =
						e instanceof Error && e.message
							? `Session history could not be loaded: ${e.message}`
							: 'Session history could not be loaded.';
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
	// Windowed pager: a full term can span ~100+ pages, so rendering one
	// button per page becomes a wall of buttons. Show first + last with a
	// ±2 window around the current page instead (ledger pattern).
	const visiblePages = $derived.by((): Array<number | 'gap-start' | 'gap-end'> => {
		if (pageCount <= 7)
			return Array.from({ length: pageCount }, (_, index) => index + 1);
		const window: Array<number | 'gap-start' | 'gap-end'> = [1];
		const start = Math.max(2, currentPage - 2);
		const end = Math.min(pageCount - 1, currentPage + 2);
		if (start > 2) window.push('gap-start');
		for (let page = start; page <= end; page += 1) window.push(page);
		if (end < pageCount - 1) window.push('gap-end');
		window.push(pageCount);
		return window;
	});
	const rangeText = $derived.by(() => {
		if (total === 0) return '0 of 0 sessions';
		const start = (currentPage - 1) * PAGE_SIZE + 1;
		const end = Math.min(currentPage * PAGE_SIZE, total);
		return `${start}–${end} of ${total} sessions`;
	});
	// The service averages the page in the single-query path but the whole
	// filtered set in the course-fanout path — label the scope so a 10-row
	// page never reads as the term.
	const averageText = $derived(
		avgScope === 'page'
			? `Page average: ${formatPercentage(avgCompliance * 100)} · ${rangeText}`
			: `Average: ${formatPercentage(avgCompliance * 100)} across ${totalSessions} filtered ${totalSessions === 1 ? 'session' : 'sessions'}`
	);

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
		sessionType = 'All';
		statusFilter = 'All';
		searchInput = '';
		searchQuery = '';
		from = '';
		to = '';
		currentPage = 1;
		exportWarning = null;
		exportProgress = null;
	};

	const setQuickRange = (kind: 'today' | 'week' | 'month' | 'all') => {
		const now = new Date();
		const key = (d: Date) =>
			`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
		if (kind === 'all') {
			from = '';
			to = '';
		} else if (kind === 'today') {
			from = key(now);
			to = key(now);
		} else if (kind === 'week') {
			const start = new Date(now);
			start.setDate(now.getDate() - ((now.getDay() + 6) % 7));
			const end = new Date(start);
			end.setDate(start.getDate() + 6);
			from = key(start);
			to = key(end);
		} else if (kind === 'month') {
			const start = new Date(now.getFullYear(), now.getMonth(), 1);
			const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
			from = key(start);
			to = key(end);
		}
		currentPage = 1;
	};

	const viewDetail = (id: number) => void goto(professorActiveSession(id));

	// Export page size: the history endpoint caps `size` at the server max
	// (shared/pagination.py MAX_PAGE_SIZE), so one giant page is a 422.
	// Page to exhaustion instead; the page cap bounds the whole export at
	// 10k rows (the old single-shot intent) so a huge scope can never loop
	// forever.
	const EXPORT_PAGE_SIZE = 100;
	const EXPORT_MAX_PAGES = 100;
	const EXPORT_MAX_ROWS = EXPORT_PAGE_SIZE * EXPORT_MAX_PAGES;

	const exportCsv = async () => {
		if (exporting) return;
		const token = exportToken + 1;
		exportToken = token;
		exporting = true;
		exportError = null;
		exportWarning = null;
		exportProgress = 'Starting export…';
		try {
			const all: HistoryRow[] = [];
			const totalPagesGuess = Math.max(1, Math.ceil(total / EXPORT_PAGE_SIZE));
			let page = 1;
			for (;;) {
				if (exportToken !== token) return;
				exportProgress = `Exporting page ${page} of ~${totalPagesGuess}…`;
				const result = await listSessionHistory({
					course: course === 'All' ? undefined : course,
					section: section === 'All' ? undefined : section,
					sessionType: sessionType === 'All' ? undefined : sessionType,
					status: statusFilter === 'All' ? undefined : statusFilter,
					search: searchQuery || undefined,
					from: from || undefined,
					to: to || undefined,
					sortBy,
					sortDir,
					page,
					size: EXPORT_PAGE_SIZE
				});
				if (exportToken !== token) return;
				all.push(...result.items);
				if (result.items.length === 0 || all.length >= result.total) break;
				page += 1;
				if (page > EXPORT_MAX_PAGES) break;
				if (all.length >= EXPORT_MAX_ROWS) break;
			}
			if (exportToken !== token) return;
			if (page >= EXPORT_MAX_PAGES && all.length >= EXPORT_MAX_ROWS)
				exportWarning = `Export capped at ${EXPORT_MAX_ROWS.toLocaleString()} rows — narrow the date range for the full set.`;
			exportProgress = null;
			const csv = buildCsv(
				[
					'Date',
					'Session code',
					'Type',
					'Course',
					'Section',
					'Present',
					'Late',
					'Absent',
					'Enrolled',
					'Compliance %',
					'Participation %'
				],
				all.map((row) => [
					row.created_at.slice(0, 10),
					row.session_code,
					row.session_type,
					row.course_code,
					row.section,
					row.present_count,
					row.late_count,
					row.absent_count,
					row.enrolled_count ?? '—',
					Math.round(row.compliance_rate * 100),
					Math.round(row.participation_rate * 100)
				])
			);
			downloadTextFile(csv, `session-history-${to || initialRange.to}.csv`);
		} catch (e: unknown) {
			if (exportToken === token)
				exportError = friendlyActionError(e, 'Export failed. Please try again.');
		} finally {
			if (exportToken === token || exportToken === token + 1) {
				exporting = false;
				exportProgress = null;
			}
		}
	};

	const cancelExport = () => {
		exportToken += 1;
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
				<label class="form-label" for="search">Search</label>
				<input
					id="search"
					class="form-input"
					type="search"
					placeholder="Session code…"
					bind:value={searchInput}
				/>
			</div>
			<div class="field">
				<label class="form-label" for="course">Course</label>
				<select
					id="course"
					class="form-input"
					bind:value={course}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">All courses</option>
					{#each courseOptions as option (option.code)}
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
				<label class="form-label" for="session-type">Type</label>
				<select
					id="session-type"
					class="form-input"
					bind:value={sessionType}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">Lecture + Lab</option>
					<option value="lecture">Lecture</option>
					<option value="lab">Laboratory</option>
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="status">Status</label>
				<select
					id="status"
					class="form-input"
					bind:value={statusFilter}
					onchange={() => (currentPage = 1)}
				>
					<option value="All">All statuses</option>
					<option value="scheduled">Scheduled</option>
					<option value="active">Active</option>
					<option value="closed">Closed</option>
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
			<div class="quick-filters">
				<button class="btn btn-ghost" type="button" onclick={() => setQuickRange('today')}>Today</button>
				<button class="btn btn-ghost" type="button" onclick={() => setQuickRange('week')}>This week</button>
				<button class="btn btn-ghost" type="button" onclick={() => setQuickRange('month')}>This month</button>
				<button class="btn btn-ghost" type="button" onclick={() => setQuickRange('all')}>All time</button>
			</div>
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
		<SkeletonTable rows={8} cols={6} label="Loading session history…" />
	{:else if rows.length === 0}
		<section class="card">
			<EmptyState
				icon="file"
				title="No sessions match these filters"
				hint="Try widening the date range."
			/>
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
						<th scope="col">Section</th>
						<th scope="col">Type</th>
						<th scope="col">Status</th>
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
								<td>
									<span class="type-badge" class:is-lab={row.session_type === 'lab'}>
										{row.session_type === 'lab' ? 'Lab' : 'Lecture'}
									</span>
								</td>
								<td>
									<span class="status-badge" class:is-active={row.status === 'active'} class:is-closed={row.status === 'closed'} class:is-scheduled={row.status === 'scheduled'}>
										{row.status}
									</span>
									{#if row.expires_at && new Date(row.expires_at).getTime() > new Date(row.scheduled_end_time).getTime() + 60000}
										<span class="overtime-badge">Extended</span>
									{:else if row.expires_at && new Date(row.expires_at).getTime() < new Date(row.scheduled_end_time).getTime() - 60000}
										<span class="shortened-badge">Shortened</span>
									{/if}
								</td>
								<td class="numeric">{plaText(row)}</td>
								<td>
									<span
										class="rate"
										title={rateTitle(row)}
										aria-label={`Compliance ${formatPercentage(row.compliance_rate * 100)}, participation ${formatPercentage(row.participation_rate * 100)}`}
									>
										{formatPercentage(row.compliance_rate * 100)}
									</span>
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
					{averageText}
				</p>
				<nav class="pages no-print" aria-label="History pages">
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = 1)}
						aria-label="Go to first history page"
					>
						First
					</button>
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = Math.max(1, currentPage - 1))}
						aria-label="Go to previous history page"
					>
						Previous
					</button>
					{#each visiblePages as pageNumber (pageNumber)}
						{#if typeof pageNumber === 'number'}
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
						{:else}
							<span class="gap" aria-hidden="true">…</span>
						{/if}
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
					<button
						class="page"
						type="button"
						disabled={currentPage >= pageCount}
						onclick={() => (currentPage = pageCount)}
						aria-label="Go to last history page"
					>
						Last
					</button>
					<span class="page-count" aria-live="polite">Page {currentPage} of {pageCount}</span>
				</nav>
				<div class="table-actions no-print">
					<button class="btn btn-secondary" type="button" onclick={() => (pendingExport = { run: print, title: 'Confirm Print', message: 'Are you sure you want to print this data? Your browser’s print dialog will open after you confirm.', confirmLabel: 'Confirm Print', details: [{ label: 'Format', value: 'Print' }] })}>
						<AppIcon name="file" size={18} />
						Print
					</button>
					<button
						class="btn btn-secondary"
						type="button"
						disabled={exporting || total === 0}
						onclick={() => (pendingExport = { run: exportCsv, details: [{ label: 'Format', value: 'CSV' }, { label: 'Rows', value: total ? String(total) : '0' }], onabort: cancelExport })}
					>
						<AppIcon name="file" size={18} />
						{exporting ? 'Exporting…' : 'Export CSV'}
					</button>
					{#if exporting}
						<button class="btn btn-ghost" type="button" onclick={cancelExport}>
							Cancel
						</button>
					{/if}
				</div>
				{#if exportProgress}
					<p class="muted" role="status" aria-live="polite">{exportProgress}</p>
				{/if}
				{#if exportWarning}
					<p class="warning" role="status">{exportWarning}</p>
				{/if}
				{#if exportError}
					<p class="error" role="alert">{exportError}</p>
				{/if}
			</div>
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
			onabort={pendingExport.onabort}
			onclose={() => (pendingExport = null)}
		/>
	{/if}
</div>

<style>
	.history {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
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

	.error {
		margin: 0 0 1rem;
		color: var(--danger-strong);
		font-weight: 600;
	}

	.warning {
		margin: 0;
		color: var(--warning-text);
		font-size: 0.875rem;
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
		color: var(--text-secondary);
	}

	.form-input {
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
		width: 100%;
	}

	.form-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
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
		min-width: 760px;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.75rem 1rem;
		text-align: left;
		border-bottom: 1px solid var(--divider);
		vertical-align: middle;
		color: var(--text-strong);
	}

	thead th {
		background: var(--bg-page);
		font-size: 0.75rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
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
		background: var(--bg-hover);
		color: var(--text-strong);
	}

	.sort:focus-visible,
	.mini:focus-visible,
	.btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.sort-arrow {
		color: var(--text-muted);
		font-size: 0.6875rem;
	}

	.sort-arrow.active {
		color: var(--brand);
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
		color: var(--text-muted);
	}

	.type-badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
		white-space: nowrap;
	}

	.type-badge.is-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
	}

	.status-badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: capitalize;
		white-space: nowrap;
		color: var(--text-muted);
		background: var(--bg-page);
		border: 1px solid var(--border);
	}

	.status-badge.is-active {
		color: var(--success);
		background: var(--success-bg);
		border-color: transparent;
	}

	.status-badge.is-closed {
		color: var(--text-muted);
		background: var(--bg-page);
	}

	.overtime-badge,
	.shortened-badge {
		display: inline-block;
		margin-left: 0.375rem;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		white-space: nowrap;
	}

	.overtime-badge {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-text);
	}

	.shortened-badge {
		color: var(--info-text);
		background: var(--info-bg);
		border: 1px solid var(--info-text);
	}

	.status-badge.is-scheduled {
		color: var(--brand);
		background: var(--accent-bg, var(--bg-hover));
		border-color: transparent;
	}

	.quick-filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	/* D36: compliance by default; the title/aria-label reveals participation. */
	.rate {
		display: inline-block;
		padding: 0;
		border: none;
		border-bottom: 1px dotted var(--text-muted);
		background: none;
		font: inherit;
		font-variant-numeric: tabular-nums;
		font-weight: 700;
		color: var(--brand);
		cursor: help;
	}

	.mini {
		padding: 0.375rem 0.75rem;
		border-radius: 999px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-strong);
		cursor: pointer;
	}

	.mini:hover {
		background: var(--bg-hover);
	}

	.table-foot {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		padding: 1.25rem 1.5rem;
		border-top: 1px solid var(--divider);
	}

	.average {
		margin: 0;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--text-secondary);
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
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.page:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.page:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	.page.current {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.page:disabled:not(.current) {
		color: var(--text-muted);
		background: var(--bg-page);
		border-color: var(--border);
		cursor: not-allowed;
	}

	.gap {
		padding: 0 0.125rem;
		color: var(--text-muted);
		font-weight: 700;
		user-select: none;
	}

	.page-count {
		margin-left: 0.5rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
		white-space: nowrap;
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
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
	}

	.btn-ghost {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--text-strong);
		padding: 0.5rem 0.9rem;
		font-size: 0.875rem;
	}

	.btn:disabled {
		background: var(--bg-page);
		border-color: var(--border);
		color: var(--text-muted);
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
