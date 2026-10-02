<script lang="ts">
	import {
		listExcuseRequests,
		quickExcuse,
		reviewExcuseRequest,
		type ExcuseFilters
	} from '$lib/features/excuse/service';
	import { isMockMode } from '$lib/api/client';
	import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import type { ExcuseOriginalStatus, ExcuseRequest, ExcuseStatus } from '$lib/shared/types/excuse';
	import { formatDate } from '$lib/shared/utils/format';

	type QueueRow = ExcuseRequest;

	const PAGE_SIZE = 10;

	const statusOptions: Array<'All' | ExcuseStatus> = ['All', 'pending', 'approved', 'rejected'];
	const originalOptions: ExcuseOriginalStatus[] = ['absent', 'late', 'rejected'];

	// Course directory: mock fixtures until the live assignments warm it. The
	// queue rows already join live course identity in excuse/service.ts, so the
	// filter options and quick-excuse lookup read the same source — a
	// professor whose real courses differ from the fixtures gets working
	// filters instead of options that match nothing.
	type DirectoryEntry = {
		courseCode: string;
		courseName: string;
		section: string;
		offeringId: number;
	};

	let directory = $state<DirectoryEntry[]>(PROFESSOR_COURSES);
	const courseOptions = $derived([...new Set(directory.map((c) => c.courseCode))].sort());

	$effect(() => {
		let cancelled = false;
		if (isMockMode()) return;
		void initProfessorCourses().then(() => {
			if (cancelled || professorState.coursesError) return;
			const warmed: DirectoryEntry[] = professorState.courses.map((c) => ({
				courseCode: c.courseCode,
				courseName: c.courseName,
				section: c.sections.length > 0 ? c.sections.join(', ') : '—',
				offeringId: c.offeringId
			}));
			if (warmed.length > 0) directory = warmed;
		});
		return () => {
			cancelled = true;
		};
	});

	let search = $state('');
	let course = $state('All');
	let status = $state<'All' | ExcuseStatus>('pending');
	let from = $state('');
	let to = $state('');
	let currentPage = $state(1);
	let rows = $state<QueueRow[]>([]);
	let total = $state(0);
	let counts = $state({ pending: 0, approved: 0, rejected: 0 });
	let isLoading = $state(true);
	let loadError = $state<string | null>(null);
	let reloadToken = $state(0);

	let selected = $state<QueueRow | null>(null);
	let reviewNotes = $state('');
	let reviewBusy = $state(false);
	let reviewError = $state<string | null>(null);

	let quickOpen = $state(false);
	let quickStudentNumber = $state('');
	let quickStudentName = $state('');
	let quickCourse = $state('CS101');
	let quickOriginal = $state<ExcuseOriginalStatus>('absent');
	let quickReason = $state('');
	let quickBusy = $state(false);
	let quickError = $state<string | null>(null);

	let notice = $state<string | null>(null);

	// Reset selections the warmed directory invalidates (same convention as
	// the reports page filters).
	$effect(() => {
		if (course !== 'All' && !courseOptions.includes(course)) course = 'All';
		if (!courseOptions.includes(quickCourse)) quickCourse = courseOptions[0] ?? 'CS101';
	});

	const buildFilters = (): ExcuseFilters => {
		let start = from || undefined;
		let end = to || undefined;
		if (start && end && start > end) [start, end] = [end, start];
		return {
			status: status === 'All' ? undefined : status,
			course: course === 'All' ? undefined : course,
			search: search || undefined,
			from: start,
			to: end,
			page: currentPage,
			size: PAGE_SIZE
		};
	};

	$effect(() => {
		const query = buildFilters();
		reloadToken;

		let cancelled = false;
		isLoading = true;
		loadError = null;

		const load = async () => {
			try {
				const result = await listExcuseRequests(query);
				if (cancelled) return;
				rows = result.items;
				total = result.total;
				counts = result.counts;
				if (result.page !== currentPage) currentPage = result.page;
			} catch {
				if (!cancelled) loadError = 'Excuse requests could not be loaded.';
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
		if (total === 0) return '0 of 0 requests';
		const start = (currentPage - 1) * PAGE_SIZE + 1;
		const end = Math.min(currentPage * PAGE_SIZE, total);
		return `${start}–${end} of ${total} requests`;
	});

	const summaryText = $derived(
		`Pending ${counts.pending} · Approved ${counts.approved} · Rejected ${counts.rejected}`
	);

	const resetFilters = () => {
		search = '';
		course = 'All';
		status = 'pending';
		from = '';
		to = '';
		currentPage = 1;
	};

	const openDetail = (row: QueueRow) => {
		selected = row;
		reviewNotes = '';
		reviewError = null;
	};

	const closeDetail = () => {
		if (reviewBusy) return;
		selected = null;
		reviewNotes = '';
		reviewError = null;
	};

	const doReview = async (decision: 'approved' | 'rejected') => {
		if (!selected || reviewBusy) return;
		reviewBusy = true;
		reviewError = null;
		try {
			const updated = await reviewExcuseRequest(selected.id, {
				status: decision,
				review_notes: reviewNotes || undefined
			});
			selected = updated;
			notice =
				decision === 'approved'
					? `Approved — ${updated.studentName} is now excused (was ${originalLabel(updated.originalStatus)}).`
					: `Rejected — ${updated.studentName} keeps ${originalLabel(updated.originalStatus)} status.`;
			reloadToken += 1;
		} catch (error) {
			reviewError = error instanceof Error ? error.message : 'Review failed.';
		} finally {
			reviewBusy = false;
		}
	};

	const openQuick = () => {
		quickOpen = true;
		quickError = null;
	};

	const closeQuick = () => {
		if (quickBusy) return;
		quickOpen = false;
		quickError = null;
	};

	const doQuickExcuse = async () => {
		if (quickBusy) return;
		quickBusy = true;
		quickError = null;
		try {
			const offering = directory.find((c) => c.courseCode === quickCourse);
			const created = await quickExcuse({
				studentNumber: quickStudentNumber,
				studentName: quickStudentName || quickStudentNumber,
				section: offering?.section ?? '—',
				courseCode: quickCourse,
				courseName: offering?.courseName ?? quickCourse,
				sessionId: offering?.offeringId ?? 1,
				sessionCode: 'QUICK',
				originalStatus: quickOriginal,
				reason: quickReason
			});
			quickOpen = false;
			quickStudentNumber = '';
			quickStudentName = '';
			quickReason = '';
			notice = `Quick-excused ${created.studentName} (${created.studentNumber}) — approved immediately.`;
			status = 'approved';
			currentPage = 1;
			reloadToken += 1;
		} catch (error) {
			quickError = error instanceof Error ? error.message : 'Quick-excuse failed.';
		} finally {
			quickBusy = false;
		}
	};

	const typeLabel = (row: QueueRow): string =>
		row.initiatedVia === 'quick'
			? 'Quick'
			: row.initiatedVia === 'prof_with_evidence'
				? 'With evidence'
				: 'Student request';

	// Live rows carry no pre-excuse status (no professor-visible source), so
	// they read `unknown` — render an em dash rather than a guessed value.
	const originalLabel = (value: ExcuseOriginalStatus): string =>
		value === 'unknown' ? '—' : value;

	const truncated = (value: string, max = 64): string =>
		value.length > max ? `${value.slice(0, max - 1)}…` : value;
</script>

<div class="excuses">
	<header class="header">
		<div>
			<h1>Excuse Requests</h1>
			<p class="muted">Review queue for your courses · {rangeText}</p>
			<p class="muted">Student requests need your review — quick-excuses approve immediately (D21).</p>
		</div>
		<button class="btn btn-primary" type="button" onclick={openQuick}>New excuse</button>
	</header>

	{#if notice}
		<p class="notice" role="status">{notice}</p>
	{/if}

	<section class="card filters" aria-label="Excuse filters">
		<div class="filter-grid">
			<div class="field">
				<label class="form-label" for="search">Search</label>
				<input
					id="search"
					class="form-input"
					type="search"
					placeholder="Student, number, code…"
					bind:value={search}
					oninput={() => (currentPage = 1)}
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
					{#each courseOptions as option (option)}
						<option value={option}>{option}</option>
					{/each}
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
			<p class="muted">Loading excuse requests…</p>
		</section>
	{:else if rows.length === 0}
		<section class="card">
			<p class="empty">No excuse requests match these filters.</p>
		</section>
	{:else}
		<section class="card table-card" aria-label="Excuse requests table">
			<div class="table-wrap" role="region" aria-label="Excuse requests">
				<table>
					<thead>
						<tr>
							<th scope="col">Student</th>
							<th scope="col">Course</th>
							<th scope="col">Session</th>
							<th scope="col">Type</th>
							<th scope="col">Reason</th>
							<th scope="col">Status</th>
							<th scope="col"><span class="sr-only">Action</span></th>
						</tr>
					</thead>
					<tbody>
						{#each rows as row (row.id)}
							<tr>
								<td>
									<div class="student-name">{row.studentName}</div>
									<div class="student-sub">{row.studentNumber} · Section {row.section}</div>
								</td>
								<td>
									<div class="course-name">{row.courseCode}</div>
									<div class="course-sub">{row.courseName}</div>
								</td>
								<td>
									<div class="mono">{row.sessionCode}</div>
									<div class="course-sub">{formatDate(row.sessionDate)}</div>
								</td>
								<td>{typeLabel(row)}</td>
								<td class="reason">{truncated(row.reason)}</td>
								<td>
									<span class="status status-{row.status}">{row.status}</span>
									<div class="status-sub">was {originalLabel(row.originalStatus)}</div>
								</td>
								<td>
									<button
										class="mini"
										type="button"
										onclick={() => openDetail(row)}
										aria-label={`Review excuse ${row.id} for ${row.studentName}`}
									>
										Review
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<div class="table-foot">
				<p class="average">{summaryText}</p>
				<nav class="pages no-print" aria-label="Excuse pages">
					<button
						class="page"
						type="button"
						disabled={currentPage <= 1}
						onclick={() => (currentPage = Math.max(1, currentPage - 1))}
						aria-label="Go to previous excuse page"
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
							aria-label={`Go to excuse page ${pageNumber}`}
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
						aria-label="Go to next excuse page"
					>
						Next
					</button>
				</nav>
			</div>
		</section>
	{/if}
</div>

{#if selected}
	<div class="overlay" role="presentation">
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="excuse-title">
			<h2 id="excuse-title">Excuse #{selected.id} — {selected.studentName}</h2>
			<p class="modal-sub">
				{selected.studentNumber} · {selected.courseCode} · Session {selected.sessionCode} ·
				{formatDate(selected.sessionDate)}
			</p>
			<dl class="detail">
				<div>
					<dt>Type</dt>
					<dd>{typeLabel(selected)} (initiated via {selected.initiatedVia})</dd>
				</div>
				<div>
					<dt>Original status</dt>
					<dd>{originalLabel(selected.originalStatus)} → excused on approve (D22)</dd>
				</div>
				<div>
					<dt>Reason</dt>
					<dd>{selected.reason}</dd>
				</div>
				<div>
					<dt>Evidence</dt>
					<dd>
						{#if selected.attachmentNames.length === 0}
							None attached
						{:else}
							<ul class="files">
								{#each selected.attachmentNames as name (name)}
										<li>{name} (S3 presigned flow lands with D24)</li>
								{/each}
							</ul>
						{/if}
					</dd>
				</div>
				<div>
					<dt>Status</dt>
					<dd><span class="status status-{selected.status}">{selected.status}</span></dd>
				</div>
				{#if selected.reviewNotes}
					<div>
						<dt>Review notes</dt>
						<dd>{selected.reviewNotes}</dd>
					</div>
				{/if}
			</dl>

			{#if selected.status === 'pending'}
				<label class="form-label" for="review-notes">Review notes (required to reject)</label>
				<textarea
					id="review-notes"
					class="form-input area"
					rows={3}
					placeholder="e.g. Legitimate medical reason / Insufficient evidence…"
					bind:value={reviewNotes}
				></textarea>
				{#if reviewError}
					<p class="error">{reviewError}</p>
				{/if}
				<div class="modal-actions">
					<button class="btn btn-ghost" type="button" disabled={reviewBusy} onclick={closeDetail}>
						Close
					</button>
					<button
						class="btn btn-danger"
						type="button"
						disabled={reviewBusy}
						onclick={() => void doReview('rejected')}
					>
						{reviewBusy ? 'Working…' : 'Reject'}
					</button>
					<button
						class="btn btn-primary"
						type="button"
						disabled={reviewBusy}
						onclick={() => void doReview('approved')}
					>
						{reviewBusy ? 'Working…' : 'Approve'}
					</button>
				</div>
			{:else}
				<div class="modal-actions">
					<button class="btn btn-ghost" type="button" onclick={closeDetail}>Close</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

{#if quickOpen}
	<div class="overlay" role="presentation">
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="quick-title">
			<h2 id="quick-title">New quick-excuse (Path A)</h2>
			<p class="modal-sub">Approves immediately — for direct-knowledge cases. Min 10-char reason.</p>
			<div class="quick-grid">
				<div class="field">
					<label class="form-label" for="quick-number">Student number</label>
					<input
						id="quick-number"
						class="form-input"
						placeholder="24-0001"
						bind:value={quickStudentNumber}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="quick-name">Student name</label>
					<input
						id="quick-name"
						class="form-input"
						placeholder="Full name"
						bind:value={quickStudentName}
					/>
				</div>
				<div class="field">
					<label class="form-label" for="quick-course">Course</label>
					<select id="quick-course" class="form-input" bind:value={quickCourse}>
						{#each courseOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label class="form-label" for="quick-original">Original status</label>
					<select id="quick-original" class="form-input" bind:value={quickOriginal}>
						{#each originalOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
			</div>
			<label class="form-label" for="quick-reason">Reason (min 10 chars)</label>
			<textarea
				id="quick-reason"
				class="form-input area"
				rows={3}
				placeholder="e.g. Student informed me after class…"
				bind:value={quickReason}
			></textarea>
			{#if quickError}
				<p class="error">{quickError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" type="button" disabled={quickBusy} onclick={closeQuick}>
					Cancel
				</button>
				<button
					class="btn btn-primary"
					type="button"
					disabled={quickBusy}
					onclick={() => void doQuickExcuse()}
				>
					{quickBusy ? 'Saving…' : 'Excuse now'}
				</button>
			</div>
		</div>
	</div>
{/if}

<svelte:window
	onkeydown={(e) => {
		if (e.key !== 'Escape') return;
		if (quickOpen) closeQuick();
		else if (selected) closeDetail();
	}}
/>

<style>
	.excuses {
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

	.notice {
		margin: 0;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		background: #f0fdf4;
		border: 1px solid #bbf7d0;
		color: #15803d;
		font-size: 0.875rem;
		font-weight: 600;
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
		margin: 0.75rem 0 0;
		color: #b91c1c;
		font-weight: 600;
		font-size: 0.875rem;
	}

	.filter-grid {
		display: grid;
		gap: 1rem;
		grid-template-columns: repeat(5, minmax(0, 1fr));
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
		border: 1.5px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #0f172a;
		background: white;
		outline: none;
	}

	.form-input:focus {
		border-color: #2563eb;
	}

	.area {
		width: 100%;
		resize: vertical;
		margin-top: 0.5rem;
	}

	.filter-actions {
		margin-top: 1rem;
		display: flex;
		justify-content: flex-end;
	}

	.btn {
		padding: 0.625rem 1.25rem;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		border: 1px solid transparent;
		transition: background 0.15s ease;
	}

	.btn-primary {
		background: #2563eb;
		color: white;
		border-color: #2563eb;
		white-space: nowrap;
	}

	.btn-primary:hover:not(:disabled) {
		background: #1d4ed8;
	}

	.btn-ghost {
		background: white;
		border-color: #cbd5e1;
		color: #1e3a5f;
	}

	.btn-ghost:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.btn-secondary {
		background: #f1f5f9;
		color: #334155;
		border-color: #e2e8f0;
	}

	.btn-danger {
		background: #dc2626;
		color: white;
		border-color: #dc2626;
	}

	.btn-danger:hover:not(:disabled) {
		background: #b91c1c;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.table-card {
		padding: 0;
		overflow: hidden;
	}

	.table-wrap {
		overflow-x: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 760px;
	}

	th {
		text-align: left;
		padding: 0.75rem 1rem;
		background: #f8fafc;
		border-bottom: 1px solid #e2e8f0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: #64748b;
	}

	td {
		padding: 0.75rem 1rem;
		border-top: 1px solid #f1f5f9;
		font-size: 0.9375rem;
		color: #1e293b;
		vertical-align: top;
	}

	tbody tr:first-child td {
		border-top: none;
	}

	.student-name,
	.course-name {
		font-weight: 600;
	}

	.student-sub,
	.course-sub,
	.status-sub {
		font-size: 0.8125rem;
		color: #64748b;
	}

	.mono {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8125rem;
	}

	.reason {
		max-width: 220px;
	}

	.status {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
		text-transform: capitalize;
	}

	.status-pending {
		color: #b45309;
		background: #fffbeb;
		border: 1px solid #fde68a;
	}

	.status-approved {
		color: #15803d;
		background: #f0fdf4;
		border: 1px solid #bbf7d0;
	}

	.status-rejected {
		color: #b91c1c;
		background: #fef2f2;
		border: 1px solid #fecaca;
	}

	.mini {
		background: white;
		border: 1px solid #cbd5e1;
		border-radius: 6px;
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		color: #1e3a5f;
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

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
	}

	.overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: rgba(15, 23, 42, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal {
		width: 100%;
		max-width: 560px;
		max-height: 90vh;
		overflow-y: auto;
		background: white;
		border-radius: 12px;
		box-shadow: 0 20px 40px rgba(15, 23, 42, 0.25);
		padding: 1.5rem;
		font-family: system-ui, sans-serif;
	}

	.modal h2 {
		margin: 0 0 0.25rem;
		font-size: 1.125rem;
		color: #1e293b;
	}

	.modal-sub {
		margin: 0 0 1rem;
		font-size: 0.875rem;
		color: #64748b;
	}

	.detail {
		margin: 0 0 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.detail div {
		display: grid;
		grid-template-columns: 140px 1fr;
		gap: 0.75rem;
	}

	.detail dt {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #64748b;
	}

	.detail dd {
		margin: 0;
		font-size: 0.9375rem;
		color: #1e293b;
	}

	.files {
		margin: 0;
		padding-left: 1.25rem;
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1rem;
		flex-wrap: wrap;
	}

	.quick-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
		margin-bottom: 1rem;
	}

	@media (max-width: 900px) {
		.filter-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 640px) {
		.header {
			flex-direction: column;
		}

		.filter-grid,
		.quick-grid {
			grid-template-columns: 1fr;
		}

		.detail div {
			grid-template-columns: 1fr;
		}
	}
</style>
