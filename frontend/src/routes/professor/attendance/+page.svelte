<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		listRecords,
		type AttendanceLedgerSortBy,
		type AttendanceLedgerSortDir,
		type ProfessorAttendanceStatus
	} from '$lib/features/attendance/service';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import {
		buildCsv,
		defaultReportRange
	} from '$lib/features/report/service';
	import { professorActiveSession } from '$lib/shared/constants/routes';
	import { formatDate, formatTime } from '$lib/shared/utils/format';

	type LedgerRow = Awaited<ReturnType<typeof listRecords>>['items'][number];

	const PAGE_SIZE = 10;
	const EXPORT_PAGE_SIZE = 100;
	const EXPORT_MAX_PAGES = 100;
	const EXPORT_MAX_ROWS = EXPORT_PAGE_SIZE * EXPORT_MAX_PAGES;

	const initialRange = defaultReportRange();

	onMount(() => {
		initProfessorCourses();
	});

	const statusOptions: Array<'All' | ProfessorAttendanceStatus> = [
		'All',
		'present',
		'late',
		'absent',
		'excused',
		'pending',
		'rejected'
	];

	let course = $state('');
	let section = $state('');
	let status = $state<'All' | ProfessorAttendanceStatus>('All');
	let sessionType = $state<'All' | 'lecture' | 'lab'>('All');
	let from = $state(initialRange.from);
	let to = $state(initialRange.to);
	let sortBy = $state<AttendanceLedgerSortBy>('date');
	let sortDir = $state<AttendanceLedgerSortDir>('desc');
	let currentPage = $state(1);
	let rows = $state<LedgerRow[]>([]);
	let total = $state(0);
	let totalSessions = $state(0);
	let counts = $state({ present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 });
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);
	let exporting = $state(false);
	let exportError = $state<string | null>(null);
	let exportWarning = $state<string | null>(null);
	let exportProgress = $state<string | null>(null);
	let exportCapped = $state(false);
	let exportToken = $state(0);
	let directoryIncomplete = $state(false);
	let missingCount = $state(0);

	// Course options deduped by code, sections joined from the live courses
	// store. The ledger only queries once both are picked.
	const courseOptions = $derived(
		[...new Map(professorState.courses.map((item) => [item.courseCode, item.courseName])).entries()].map(
			([code, name]) => ({ code, name })
		)
	);

	// Course → section cascade: sections narrow to the chosen course, and the
	// ledger only queries once both are picked. Dates + status reveal after.
	const availableSections = $derived(
		course === ''
			? []
			: [
					...new Set(
						professorState.courses
							.filter((item) => item.courseCode === course)
							.flatMap((item) => item.sections)
					)
				]
	);

	const canQuery = $derived(course !== '' && section !== '');

	// Picking a new course clears the section until one is chosen.
	$effect(() => {
		course;
		section = '';
		currentPage = 1;
	});

	$effect(() => {
		if (!canQuery) {
			rows = [];
			total = 0;
			totalSessions = 0;
			counts = { present: 0, late: 0, absent: 0, excused: 0, pending: 0, rejected: 0 };
			directoryIncomplete = false;
			missingCount = 0;
			isLoading = false;
			loadError = null;
			return;
		}

		const query = {
			course: course || undefined,
			section: section || undefined,
			status: status === 'All' ? undefined : status,
			sessionType: sessionType === 'All' ? undefined : sessionType,
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
				const result = await listRecords(query);
				if (cancelled) return;
				rows = result.items;
				total = result.total;
				totalSessions = result.total_sessions;
				counts = result.counts;
				directoryIncomplete = result.directoryIncomplete;
				missingCount = result.missingCount;
				// The service clamps out-of-range pages (e.g. filters shrank the
				// result under us); follow it so the pager never points nowhere.
				if (result.page !== currentPage) currentPage = result.page;
			} catch (e) {
				if (!cancelled)
					loadError =
						e instanceof Error && e.message
							? `Attendance records could not be loaded: ${e.message}`
							: 'Attendance records could not be loaded.';
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
	// Windowed pager: the ledger can span ~100+ pages, so rendering one
	// button per page (the history-page pattern) becomes a wall of buttons.
	// Show first + last with a ±2 window around the current page instead.
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
		if (total === 0) return '0 of 0 records';
		const start = (currentPage - 1) * PAGE_SIZE + 1;
		const end = Math.min(currentPage * PAGE_SIZE, total);
		return `${start}–${end} of ${total} records`;
	});

	const summaryText = $derived(
		`This page: Present ${counts.present} · Late ${counts.late} · Excused ${counts.excused} · Absent ${counts.absent} across ${totalSessions} ${totalSessions === 1 ? 'session' : 'sessions'}`
	);

	const directoryWarning = $derived(
		directoryIncomplete
			? `${missingCount} ${missingCount === 1 ? 'row shows' : 'rows show'} scanned time because ${missingCount === 1 ? 'its' : 'their'} session is outside the warmed window — narrow the date range for exact session dates.`
			: null
	);

	const setSort = (key: AttendanceLedgerSortBy) => {
		if (sortBy === key) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		else {
			sortBy = key;
			// Dates read newest-first; everything else reads A-to-Z / low-to-high.
			sortDir = key === 'date' ? 'desc' : 'asc';
		}
		currentPage = 1;
	};

	const sortArrow = (key: AttendanceLedgerSortBy): string => {
		if (sortBy !== key) return '↕';
		return sortDir === 'asc' ? '▲' : '▼';
	};

	const sortLabel = (key: AttendanceLedgerSortBy, label: string): string => {
		if (sortBy !== key) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (key: AttendanceLedgerSortBy): 'ascending' | 'descending' | 'none' => {
		if (sortBy !== key) return 'none';
		return sortDir === 'asc' ? 'ascending' : 'descending';
	};

	const resetFilters = () => {
		course = '';
		section = '';
		status = 'All';
		sessionType = 'All';
		from = initialRange.from;
		to = initialRange.to;
		currentPage = 1;
		exportWarning = null;
		exportProgress = null;
		exportCapped = false;
	};

	const viewDetail = (sessionId: number) => void goto(professorActiveSession(sessionId));

	const scannedText = (row: LedgerRow): string =>
		row.scanned_at ? formatTime(row.scanned_at) : '—';

	const scannedSub = (row: LedgerRow): string | null => {
		if (!row.scanned_at) return null;
		const via = row.scanned_via ? row.scanned_via.toUpperCase() : null;
		const score =
			row.face_match_score === undefined ? null : `${Math.round(row.face_match_score)}%`;
		return [via, score].filter(Boolean).join(' · ') || null;
	};

	const excuseSub = (row: LedgerRow): string | null => {
		if (row.status !== 'excused') return null;
		const was = row.original_status ? `was ${row.original_status}` : null;
		return [row.excuse_reason, was].filter(Boolean).join(' · ') || null;
	};

	const exportCsv = async () => {
		if (exporting || !canQuery) return;
		const token = exportToken + 1;
		exportToken = token;
		exporting = true;
		exportError = null;
		exportWarning = null;
		exportCapped = false;
		exportProgress = 'Starting export…';
		try {
			const baseQuery = {
				course: course || undefined,
				section: section || undefined,
				status: status === 'All' ? undefined : status,
				sessionType: sessionType === 'All' ? undefined : sessionType,
				from: from || undefined,
				to: to || undefined,
				sortBy,
				sortDir
			};
			// Walk pages to export the full filtered set. The cap bounds the
			// whole export at 10k rows (the history-page pattern) so a huge
			// scope can never loop forever; progress + cancel keep a large
			// export interruptible instead of hanging the tab.
			const first = await listRecords({ ...baseQuery, page: 1, size: EXPORT_PAGE_SIZE });
			if (exportToken !== token) return;
			const all = [...first.items];
			let unknownRows = first.missingCount;
			const totalPages = Math.max(1, Math.ceil(first.total / EXPORT_PAGE_SIZE));
			const cappedPages = Math.min(totalPages, EXPORT_MAX_PAGES);
			exportProgress = `Exporting page 1 of ~${totalPages}…`;
			for (let page = 2; page <= cappedPages; page += 1) {
				if (exportToken !== token) return;
				exportProgress = `Exporting page ${page} of ~${totalPages}…`;
				const next = await listRecords({ ...baseQuery, page, size: EXPORT_PAGE_SIZE });
				if (exportToken !== token) return;
				all.push(...next.items);
				unknownRows += next.missingCount;
				if (all.length >= EXPORT_MAX_ROWS) break;
			}
			if (exportToken !== token) return;
			exportCapped = totalPages > EXPORT_MAX_PAGES;
			const warnings: string[] = [];
			if (exportCapped)
				warnings.push(
					`Export capped at ${EXPORT_MAX_ROWS.toLocaleString()} rows — narrow the date range for the full set.`
				);
			if (unknownRows > 0)
				warnings.push(
					`${unknownRows} ${unknownRows === 1 ? 'row uses' : 'rows use'} scanned time because ${unknownRows === 1 ? 'its' : 'their'} session is outside the warmed window.`
				);
			exportWarning = warnings.length > 0 ? warnings.join(' ') : null;
			exportProgress = null;
			const csv = buildCsv(
				[
					'Date',
					'Session code',
					'Type',
					'Course',
					'Section',
					'Student number',
					'Student name',
					'Status',
					'Original status',
					'Scanned at',
					'Via',
					'Face score',
					'Excuse reason'
				],
				all.map((row) => [
					row.created_at.slice(0, 10),
					row.session_code,
					row.session_type,
					row.course_code,
					row.section,
					row.student_number,
					row.student_name,
					row.status,
					row.original_status ?? '',
					row.scanned_at ?? '',
					row.scanned_via ?? '',
					row.face_match_score ?? '',
					row.excuse_reason ?? ''
				])
			);
			const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = `attendance-${to || initialRange.to}.csv`;
			document.body.appendChild(anchor);
			anchor.click();
			anchor.remove();
			setTimeout(() => URL.revokeObjectURL(url), 60_000);
		} catch (e: unknown) {
			if (exportToken === token)
				exportError = e instanceof Error && e.message ? e.message : 'Export failed. Please try again.';
		} finally {
			if (exportToken === token) {
				exporting = false;
				exportProgress = null;
			}
		}
	};

	const cancelExport = () => {
		exportToken += 1;
	};

	const print = () => window.print();
</script>

<div class="attendance">
	<header class="header">
		<div>
			<h1>Attendance</h1>
			{#if canQuery}
				<p class="muted">Cross-session roster across your courses · {rangeText}</p>
			{:else}
				<p class="muted">Select a course and section to begin.</p>
			{/if}
			<p class="muted">Read-only ledger — excuse actions live on the session page.</p>
		</div>
	</header>

	<section class="card filters no-print" aria-label="Attendance filters">
		<div class="filter-grid steps">
			<div class="field">
				<label class="form-label" for="course">1 · Course</label>
				<select
					id="course"
					class="form-input"
					bind:value={course}
					onchange={() => (currentPage = 1)}
				>
					<option value="">Select a course…</option>
					{#each courseOptions as option (option.code)}
						<option value={option.code}>{option.code} — {option.name}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label class="form-label" for="section">2 · Section</label>
				<select
					id="section"
					class="form-input"
					bind:value={section}
					disabled={!course}
					onchange={() => (currentPage = 1)}
				>
					<option value="">{course ? 'Select a section…' : 'Pick a course first'}</option>
					{#each availableSections as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</div>
		</div>
		{#if canQuery}
			<div class="filter-grid refine">
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
						bind:value={status}
						onchange={() => (currentPage = 1)}
					>
						{#each statusOptions as option (option)}
							<option value={option}>{option === 'All' ? 'All statuses' : option}</option>
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
		{/if}
		<div class="filter-actions">
			<button class="btn btn-ghost" type="button" onclick={resetFilters}>Reset filters</button>
		</div>
	</section>

	{#if !canQuery}
		<section class="card">
			<p class="empty">Select a course and a section above to view attendance records.</p>
		</section>
	{:else if loadError}
		<section class="card">
			<p class="error">{loadError}</p>
			<button class="btn btn-secondary" type="button" onclick={() => (reloadToken += 1)}>
				Try again
			</button>
		</section>
	{:else if isLoading && rows.length === 0}
		<section class="card">
			<p class="muted">Loading attendance records…</p>
		</section>
	{:else if rows.length === 0}
		<section class="card">
			<p class="empty">No attendance records match these filters. Try widening the date range.</p>
		</section>
	{:else}
		<section class="card table-card" aria-label="Attendance ledger table">
			<div class="table-wrap" role="region" aria-label="Attendance ledger">
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
							<th scope="col" aria-sort={ariaSort('student')}>
								<button
									class="sort"
									type="button"
									onclick={() => setSort('student')}
									aria-label={sortLabel('student', 'Student')}
								>
									<span>Student</span>
									<span class="sort-arrow" class:active={sortBy === 'student'} aria-hidden="true">
										{sortArrow('student')}
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
									<span>Course</span>
									<span class="sort-arrow" class:active={sortBy === 'section'} aria-hidden="true">
										{sortArrow('section')}
									</span>
								</button>
							</th>
							<th scope="col">Session</th>
							<th scope="col">Type</th>
							<th scope="col" aria-sort={ariaSort('status')}>
								<button
									class="sort"
									type="button"
									onclick={() => setSort('status')}
									aria-label={sortLabel('status', 'Status')}
								>
									<span>Status</span>
									<span class="sort-arrow" class:active={sortBy === 'status'} aria-hidden="true">
										{sortArrow('status')}
									</span>
								</button>
							</th>
							<th scope="col" aria-sort={ariaSort('time')}>
								<button
									class="sort"
									type="button"
									onclick={() => setSort('time')}
									aria-label={sortLabel('time', 'Time')}
								>
									<span>Scanned</span>
									<span class="sort-arrow" class:active={sortBy === 'time'} aria-hidden="true">
										{sortArrow('time')}
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
								<td>
									<div class="student-name">{row.student_name}</div>
									<div class="student-sub">{row.student_number} · Section {row.section}</div>
								</td>
								<td>
									<div class="course-name">{row.course_code}</div>
									<div class="course-sub">{row.course_name}</div>
								</td>
								<td class="mono">{row.session_code}</td>
								<td>
									<span class="type-badge" class:is-lab={row.session_type === 'lab'}>
										{row.session_type === 'lab' ? 'Lab' : 'Lecture'}
									</span>
								</td>
								<td>
									<span class="status status-{row.status}">{row.status}</span>
									{#if excuseSub(row)}
										<div class="status-sub">{excuseSub(row)}</div>
									{/if}
								</td>
								<td>
									<div class="numeric">{scannedText(row)}</div>
									{#if scannedSub(row)}
										<div class="course-sub">{scannedSub(row)}</div>
									{/if}
								</td>
								<td>
									<button
										class="mini"
										type="button"
										onclick={() => viewDetail(row.session_id)}
										aria-label={`View session ${row.session_code} for ${row.student_name}`}
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
				<p class="average">{summaryText}</p>
				{#if directoryWarning}
					<p class="warning" role="status">{directoryWarning}</p>
				{/if}
				<nav class="pages no-print" aria-label="Attendance pages">
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = 1)}
						aria-label="Go to first attendance page"
					>
						First
					</button>
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = Math.max(1, currentPage - 1))}
						aria-label="Go to previous attendance page"
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
								aria-label={`Go to attendance page ${pageNumber}`}
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
						aria-label="Go to next attendance page"
					>
						Next
					</button>
					<button
						class="page"
						type="button"
						disabled={currentPage >= pageCount}
						onclick={() => (currentPage = pageCount)}
						aria-label="Go to last attendance page"
					>
						Last
					</button>
					<span class="page-count" aria-live="polite">Page {currentPage} of {pageCount}</span>
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
</div>

<style>
	.attendance {
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

	.empty {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9375rem;
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
		gap: 1rem;
	}

	.steps {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.refine {
		grid-template-columns: repeat(3, minmax(0, 1fr));
		margin-top: 1rem;
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
		color: #94a3b8;
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

	.student-name,
	.course-name {
		font-weight: 600;
	}

	.student-sub,
	.course-sub,
	.status-sub {
		font-size: 0.8125rem;
		color: var(--text-muted);
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

	.status-present { background: var(--success-bg); color: var(--success); }
	.status-late { background: var(--warning-bg); color: var(--warning-text); }
	.status-excused { background: var(--info-bg); color: #6d28d9; }
	.status-pending { background: var(--bg-muted); color: var(--text-muted); }
	.status-absent { background: var(--danger-bg); color: var(--danger-strong); }
	.status-rejected { background: var(--danger-bg); color: #7f1d1d; }

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
		color: #92400e;
		background: #fef3c7;
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
		color: #94a3b8;
		background: var(--bg-page);
		border-color: var(--border);
		cursor: not-allowed;
	}

	.gap {
		padding: 0 0.125rem;
		color: #94a3b8;
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

		.attendance {
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
