<script lang="ts">
	import { onMount } from 'svelte';
	import { APIError } from '$lib/api/client';
	import {
		getSessionHistory,
		type StudentHistoryStatus,
	} from '$lib/features/student/service';
	import { buildCsv } from '$lib/features/report/service';
	import { flushQueue, queue, type QueuedScan } from '$lib/features/sync/service';
	import { formatDate, formatTime } from '$lib/shared/utils/format';

	type Status = StudentHistoryStatus;
	type Row = {
		id: number;
		date: string;
		course: string;
		courseName: string;
		status: Status;
		time: string;
		scannedAt: string;
	};
	type SortKey = 'date' | 'course' | 'status' | 'time';

	let rows: Row[] = $state([]);
	let loading = $state(true);
	let loadError: string | null = $state(null);
	let total = $state(0);
	let summary: {
		compliance_rate: number;
		participation_rate: number;
		counts: Record<Status, number> | Record<string, number>;
	} | null = $state(null);

	const courseOptions = $derived([...new Set(rows.map((r) => r.course))]);
	const STATUSES: Status[] = ['present', 'late', 'absent', 'excused', 'pending', 'rejected'];

	let sortKey: SortKey = $state('date');
	let sortAsc = $state(false);
	let filterCourse = $state('All');
	let filterStatus = $state('All');
	let search = $state('');
	let page = $state(1);

	const PER_PAGE = 5;

	const toRow = (item: {
		id: number;
		courseCode: string;
		courseName: string;
		status: Status;
		scannedAt: string;
	}): Row => ({
		id: item.id,
		date: formatDate(item.scannedAt),
		course: item.courseCode,
		courseName: item.courseName,
		status: item.status,
		time: formatTime(item.scannedAt),
		scannedAt: item.scannedAt,
	});

	const load = async () => {
		loading = true;
		loadError = null;
		try {
			const res = await getSessionHistory({
				status: filterStatus !== 'All' ? (filterStatus.toLowerCase() as Status) : undefined,
				sortBy: sortKey,
				sortDir: sortAsc ? 'asc' : 'desc',
				page,
				size: PER_PAGE,
			});
			rows = res.items.map(toRow);
			total = res.total;
			summary = res.summary;
		} catch (e) {
			loadError =
				e instanceof APIError
					? e.message
					: e instanceof Error
						? e.message
						: 'Unable to load attendance history';
			rows = [];
		} finally {
			loading = false;
		}
	};

	// Offline queue strip: actionable local scans (pending/syncing/rejected)
	// render above the server table and never merge into it, so the server
	// total, pagination, and summary math stay exact. Synced rows are
	// excluded — the server history picks them up after the flush.
	type QueueRow = {
		id: string;
		sessionCode: string;
		date: string;
		time: string;
		status: 'pending' | 'rejected';
		reason: string | null;
	};

	let queueRows = $state<QueueRow[]>([]);
	let queueBusy = $state(false);

	const toQueueRow = (item: QueuedScan): QueueRow => ({
		id: item.id,
		sessionCode: item.payload.sessionCode,
		date: formatDate(item.payload.scannedAt),
		time: formatTime(item.payload.scannedAt),
		status: item.status === 'rejected' ? 'rejected' : 'pending',
		reason: item.lastError
	});

	const refreshQueue = async () => {
		try {
			const [pending, rejected] = await Promise.all([queue.getPending(), queue.getRejected()]);
			queueRows = [...pending, ...rejected].map(toQueueRow);
		} catch {
			queueRows = [];
		}
	};

	const syncNow = async () => {
		if (queueBusy) return;
		queueBusy = true;
		try {
			await flushQueue();
		} finally {
			await refreshQueue();
			queueBusy = false;
		}
	};

	const retryQueued = async (id: string) => {
		await queue.updateStatus(id, 'pending').catch(() => undefined);
		await syncNow();
	};

	const discardQueued = async (id: string) => {
		await queue.remove(id).catch(() => undefined);
		await refreshQueue();
	};

	onMount(() => {
		void load();
		void refreshQueue();
		const handleVisible = () => {
			if (document.visibilityState === 'visible') void refreshQueue();
		};
		document.addEventListener('visibilitychange', handleVisible);
		return () => {
			document.removeEventListener('visibilitychange', handleVisible);
		};
	});

	// Reload server page when the server-side controls change. rows/total/
	// loading are written by load() but never read here, so no reload loop.
	$effect(() => {
		const key = sortKey;
		const asc = sortAsc;
		const status = filterStatus;
		const p = page;
		void (async () => {
			loading = true;
			loadError = null;
			try {
				const res = await getSessionHistory({
					status: status !== 'All' ? (status.toLowerCase() as Status) : undefined,
					sortBy: key,
					sortDir: asc ? 'asc' : 'desc',
					page: p,
					size: PER_PAGE,
				});
				rows = res.items.map(toRow);
				total = res.total;
				summary = res.summary;
			} catch (e) {
				loadError =
					e instanceof APIError
						? e.message
						: e instanceof Error
							? e.message
							: 'Unable to load attendance history';
				rows = [];
			} finally {
				loading = false;
			}
		})();
	});

	const reload = () => {
		void load();
	};

	const handleSort = (key: SortKey) => {
		if (sortKey === key) {
			sortAsc = !sortAsc;
		} else {
			sortKey = key;
			sortAsc = true;
		}
	};

	const sortGlyph = (key: SortKey): string =>
		sortKey === key ? (sortAsc ? '▲' : '▼') : '⇅';

	const badgeLabel = (status: Status): string =>
		status.charAt(0).toUpperCase() + status.slice(1);

	// Server owns status/sort/page; course + search filter the fetched rows
	// client-side (course_id mapping needs a schedule that has no backend yet).
	const matchesFilters = (r: Row): boolean => {
		if (filterCourse !== 'All' && r.course !== filterCourse) return false;
		if (
			search &&
			!r.course.toLowerCase().includes(search.toLowerCase()) &&
			!r.date.toLowerCase().includes(search.toLowerCase()) &&
			!r.courseName.toLowerCase().includes(search.toLowerCase())
		) {
			return false;
		}
		return true;
	};

	const filtered = $derived(rows.filter(matchesFilters));

	const pages = $derived(Math.max(1, Math.ceil(total / PER_PAGE)));
	const paged = $derived(filtered);

	let exporting = $state(false);
	let exportError: string | null = $state(null);

	// Full filtered-set export: the table shows one server page at a time, so
	// the export pages through every server page itself (cap 2000 rows) and
	// re-applies the client-side course + search filter to the complete set.
	const EXPORT_PAGE_SIZE = 100;
	const EXPORT_MAX_ROWS = 2000;

	const exportCsv = async () => {
		if (exporting) return;
		exporting = true;
		exportError = null;
		try {
			const status = filterStatus !== 'All' ? (filterStatus.toLowerCase() as Status) : undefined;
			const all: Row[] = [];
			let exportPage = 1;
			let exportTotal = Number.POSITIVE_INFINITY;
			while (all.length < exportTotal && all.length < EXPORT_MAX_ROWS) {
				const res = await getSessionHistory({
					status,
					sortBy: sortKey,
					sortDir: sortAsc ? 'asc' : 'desc',
					page: exportPage,
					size: EXPORT_PAGE_SIZE
				});
				exportTotal = res.total;
				const items = res.items ?? [];
				if (items.length === 0) break;
				all.push(...items.map(toRow));
				exportPage += 1;
			}
			const records = all.filter(matchesFilters);
			if (records.length === 0) {
				exportError = 'No records to export.';
				return;
			}
			const header = ['Date', 'Course code', 'Course name', 'Status', 'Time', 'Scanned at'];
			const body = records.map((r) => [r.date, r.course, r.courseName, r.status, r.time, r.scannedAt]);
			const blob = new Blob([buildCsv(header, body)], { type: 'text/csv;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const stamp = new Date().toISOString().slice(0, 10);
			const scope = filterStatus !== 'All' ? filterStatus.toLowerCase() : 'all';
			a.download = `attendance-history-${scope}-${stamp}.csv`.replace(/[^a-z0-9._-]+/gi, '-');
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(url);
		} catch (e) {
			exportError = e instanceof Error ? e.message : 'Export failed. Please try again.';
		} finally {
			exporting = false;
		}
	};

	const doPrint = () => {
		window.print();
	};
</script>

<div class="page">
	<header class="header">
		<h1>Attendance History</h1>
		<p class="subtitle">
			{#if summary}
				Compliance {Math.round(summary.compliance_rate * 100)}% · Participation
				{Math.round(summary.participation_rate * 100)}% · {total} records
			{:else}
				Semester: 1st Sem 2026
			{/if}
		</p>
	</header>

	<div class="card filters">
		<div class="search-wrap">
			<input
				class="form-input search-input"
				placeholder="Search..."
				value={search}
				oninput={(e) => {
					search = (e.target as HTMLInputElement).value;
				}}
			/>
		</div>

		<select
			class="form-input select-input"
			value={filterCourse}
			onchange={(e) => {
				filterCourse = (e.target as HTMLSelectElement).value;
				page = 1;
			}}
		>
			<option value="All">All Courses</option>
			{#each courseOptions as course}
				<option value={course}>{course}</option>
			{/each}
		</select>

		<select
			class="form-input select-input"
			value={filterStatus}
			onchange={(e) => {
				filterStatus = (e.target as HTMLSelectElement).value;
				page = 1;
			}}
		>
			<option value="All">All Statuses</option>
			{#each STATUSES as status}
				<option value={status}>{badgeLabel(status)}</option>
			{/each}
		</select>

		<div class="actions">
			<button class="btn-ghost" onclick={doPrint}>Print</button>
			<button class="btn-ghost" onclick={exportCsv} disabled={exporting}>
				{exporting ? 'Exporting…' : 'Export CSV'}
			</button>
		</div>
		{#if exportError}
			<p class="export-error" role="status">{exportError}</p>
		{/if}
	</div>

	{#if queueRows.length > 0}
		<section class="card queue-card" aria-label="Pending sync">
			<div class="queue-head">
				<h2 class="section-title">Pending sync ({queueRows.length})</h2>
				<button class="btn-ghost" disabled={queueBusy} onclick={() => void syncNow()}>
					{queueBusy ? 'Syncing…' : 'Sync now'}
				</button>
			</div>
			<p class="muted">These scans live on this device only — they are not attendance records yet.</p>
			<ul class="queue-list">
				{#each queueRows as item (item.id)}
					<li class="queue-row">
						<span
							class="badge"
							class:pending={item.status === 'pending'}
							class:rejected={item.status === 'rejected'}
							title={item.reason ?? undefined}
						>
							{item.status === 'pending' ? 'Queued' : 'Rejected'}
						</span>
						<span class="mono">{item.date}</span>
						<span class="mono">{item.time}</span>
						<span class="course" title={item.reason ?? 'Session scan awaiting upload'}>
							Session {item.sessionCode}
						</span>
						{#if item.status === 'rejected'}
							<span class="queue-actions">
								<button class="btn-ghost btn-small" onclick={() => void retryQueued(item.id)}>Retry</button>
								<button class="btn-ghost btn-small" onclick={() => void discardQueued(item.id)}>Discard</button>
							</span>
						{/if}
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	<div class="card table-card">
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th><button class="th-btn" onclick={() => handleSort('date')}>Date<span class="sort-glyph">{sortGlyph('date')}</span></button></th>
						<th><button class="th-btn" onclick={() => handleSort('course')}>Course<span class="sort-glyph">{sortGlyph('course')}</span></button></th>
						<th><button class="th-btn" onclick={() => handleSort('status')}>Status<span class="sort-glyph">{sortGlyph('status')}</span></button></th>
						<th><button class="th-btn" onclick={() => handleSort('time')}>Time<span class="sort-glyph">{sortGlyph('time')}</span></button></th>
					</tr>
				</thead>
				<tbody>
					{#if loading}
						<tr>
							<td class="empty-row" colspan="4">Loading attendance history…</td>
						</tr>
					{:else if loadError}
						<tr>
							<td class="empty-row" colspan="4">
								{loadError}
								<button class="btn-ghost retry-btn" onclick={reload}>Retry</button>
							</td>
						</tr>
					{:else if filtered.length === 0}
						<tr>
							<td class="empty-row" colspan="4">No matching records</td>
						</tr>
					{:else}
						{#each paged as r (r.id)}
							<tr>
								<td class="mono">{r.date}</td>
								<td><span class="course" title={r.courseName}>{r.course}</span></td>
								<td>
									<span
										class="badge"
										class:present={r.status === 'present'}
										class:late={r.status === 'late'}
										class:absent={r.status === 'absent'}
										class:excused={r.status === 'excused'}
										class:pending={r.status === 'pending'}
										class:rejected={r.status === 'rejected'}
									>
										{badgeLabel(r.status)}
									</span>
								</td>
								<td class="mono">{r.time}</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>

		<div class="pagination">
			<button
				class="page-btn"
				onclick={() => (page = Math.max(1, page - 1))}
				disabled={page === 1}
				aria-label="Previous page"
			>
				‹
			</button>
			{#each Array.from({ length: pages }, (_, i) => i + 1) as p (p)}
				<button class="page-btn" class:active={p === page} onclick={() => (page = p)} aria-current={p === page ? 'page' : undefined}>
					{p}
				</button>
			{/each}
			<button
				class="page-btn"
				onclick={() => (page = Math.min(pages, page + 1))}
				disabled={page === pages}
				aria-label="Next page"
			>
				›
			</button>
		</div>
	</div>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		font-family: system-ui, sans-serif;
		width: 100%;
		min-width: 0;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.subtitle {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
		min-width: 0;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		padding: 1rem 1.25rem;
		min-width: 0;
	}

	.search-wrap {
		flex: 0 0 auto;
		max-width: 100%;
	}

	.search-input {
		width: 200px;
	}

	.select-input {
		width: auto;
	}

	.filters .select-input {
		min-width: 0;
	}

	.form-input {
		padding: 0.625rem 0.875rem;
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		outline: none;
		transition: border-color 0.15s;
		background: var(--bg-card);
	}

	.form-input:focus {
		border-color: var(--accent);
	}

	.actions {
		display: flex;
		gap: 0.5rem;
		margin-left: auto;
	}

	.btn-ghost {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
	}

	.table-card {
		overflow: hidden;
		min-width: 0;
	}

	.scroll {
		overflow-x: auto;
		max-width: 100%;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 480px;
	}

	th {
		text-align: left;
		padding: 0;
		border-bottom: 1px solid var(--border);
		background: var(--bg-page);
	}

	.th-btn {
		display: inline-flex;
		align-items: center;
		padding: 0.75rem 1rem;
		width: 100%;
		border: none;
		background: none;
		font-family: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
		cursor: pointer;
	}

	.th-btn:hover {
		color: var(--brand);
	}

	.sort-glyph {
		margin-left: 4px;
	}

	td {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--divider);
		font-size: 0.9375rem;
		color: var(--text);
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8125rem;
	}

	.course {
		font-weight: 600;
	}

	.badge {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.badge.present {
		color: var(--success);
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
	}

	.badge.absent {
		color: var(--danger-strong);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
	}

	.badge.pending {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.badge.late {
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.badge.excused {
		color: var(--accent-hover);
		background: var(--info-bg);
		border: 1px solid var(--info-bg);
	}

	.badge.rejected {
		color: #6b7280;
		background: #f3f4f6;
		border: 1px solid #e5e7eb;
	}

	.retry-btn {
		margin-left: 0.75rem;
	}

	.export-error {
		flex-basis: 100%;
		margin: 0;
		color: #b91c1c;
		font-size: 0.875rem;
	}

	.queue-card {
		padding: 1rem 1.25rem;
	}

	.queue-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.section-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0;
	}

	.muted {
		color: #64748b;
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}

	.queue-list {
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.queue-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		padding: 0.625rem 0.875rem;
		border: 1px solid #f1f5f9;
		border-radius: 8px;
		background: #f8fafc;
		font-size: 0.9375rem;
		color: #1e293b;
	}

	.queue-actions {
		display: flex;
		gap: 0.375rem;
		margin-left: auto;
	}

	.btn-small {
		padding: 0.25rem 0.625rem;
		font-size: 0.8125rem;
	}

	.empty-row {
		text-align: center;
		color: var(--text-muted);
		padding: 2rem 1rem;
	}

	.pagination {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--border);
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.page-btn {
		background: none;
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.25rem 0.625rem;
		font-family: inherit;
		font-size: 0.875rem;
		color: var(--brand);
		cursor: pointer;
	}

	.page-btn:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.page-btn.active {
		background: var(--brand);
		color: var(--on-brand);
		font-weight: 700;
		border-color: var(--brand);
	}

	.page-btn:disabled {
		color: #94a3b8;
		cursor: not-allowed;
	}

	:global(.page :is(button, input, select):focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	@media (max-width: 640px) {
		.select-input {
			width: 100%;
		}

		.search-input {
			width: 100%;
		}

		.search-wrap {
			flex: 1 1 100%;
		}

		.actions {
			margin-left: 0;
			width: 100%;
		}

		.btn-ghost {
			flex: 1;
		}
	}
</style>