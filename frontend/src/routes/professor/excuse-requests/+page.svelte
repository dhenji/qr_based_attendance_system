<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import {
		editExcuse,
		EXCUSE_REASON_MIN_LENGTH,
		listExcuseRequests,
		quickExcuse,
		revokeExcuse,
		reviewExcuseRequest,
		type ExcuseFilters
	} from '$lib/features/excuse/service';
	import { listSessions } from '$lib/features/session/service';
	import { isMockMode } from '$lib/api/client';
	import {
		ATTACHMENTS_MAX_FILES,
		uploadAttachments,
		validateAttachmentFiles,
	} from '$lib/features/excuse/attachments';
	import { PROFESSOR_COURSES } from '$lib/features/professor/mock';
	import {
		initProfessorCourses,
		professorState
	} from '$lib/features/professor/store.svelte';
	import type { ExcuseOriginalStatus, ExcuseRequest, ExcuseStatus } from '$lib/shared/types/excuse';
	import { formatDate } from '$lib/shared/utils/format';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

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
	let quickFiles = $state<File[]>([]);
	let quickFileErrors = $state<string[]>([]);
	let quickUploading = $state(false);
	let quickUploadStatus = $state('');
	// Object urls already uploaded in a prior attempt — kept across retries
	// so a single failed file never discards the rest.
	let quickStagedUrls = $state<string[]>([]);
	// Real sessions for the quick-excuse picker (warmed when the modal
	// opens; falls back to the course directory when the list is empty).
	let quickSessions = $state<Array<{ id: number; code: string }>>([]);
	let quickSessionId = $state<number | null>(null);

	// Detail-modal edit/revoke for professor-issued rows (quick /
	// prof_with_evidence carry integer ids; student requests 404 on edit
	// server-side, so those buttons stay hidden for them).
	let editMode = $state(false);
	let editReason = $state('');
	let editNotes = $state('');
	let editBusy = $state(false);
	let editError = $state<string | null>(null);
	let revokeAsk = $state(false);
	let revokeBusy = $state(false);
	let revokeError = $state<string | null>(null);

	const canModify = (row: QueueRow): boolean =>
		row.status === 'approved' &&
		(row.initiatedVia === 'quick' || row.initiatedVia === 'prof_with_evidence');

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
		editMode = false;
		editReason = row.reason;
		editNotes = row.reviewNotes ?? '';
		editError = null;
		revokeAsk = false;
		revokeError = null;
	};

	const closeDetail = () => {
		if (reviewBusy || editBusy || revokeBusy) return;
		selected = null;
		reviewNotes = '';
		reviewError = null;
		editMode = false;
		revokeAsk = false;
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
		quickFiles = [];
		quickFileErrors = [];
		quickStagedUrls = [];
		quickUploadStatus = '';
		// Warm real sessions so the excuse attaches to an actual session id
		// instead of a fabricated one (the submit itself stays in-memory:
		// typed numbers cannot resolve to integer ids without backend help).
		void listSessions({ size: 50 })
			.then(({ items }) => {
				if (items.length === 0) return;
				quickSessions = items.map((item) => ({ id: item.id, code: item.sessionCode }));
				if (quickSessionId === null || !quickSessions.some((s) => s.id === quickSessionId)) {
					quickSessionId = quickSessions[0].id;
				}
			})
			.catch(() => undefined);
	};

	const closeQuick = () => {
		if (quickBusy) return;
		quickOpen = false;
		quickError = null;
	};

	const onQuickFiles = (list: FileList | null) => {
		if (!list) return;
		const { valid, errors } = validateAttachmentFiles([...quickFiles, ...Array.from(list)]);
		quickFiles = valid;
		quickFileErrors = errors;
	};

	const doQuickExcuse = async () => {
		if (quickBusy) return;
		quickBusy = true;
		quickError = null;
		try {
			// Typed student numbers cannot resolve to the integer ids the live
			// per-record routes need (no professor endpoint returns them), so
			// the quick modal is mock-only. Live callers use queue-row actions
			// (quickExcuseByIds) or Excuse all absent instead.
			if (!isMockMode()) {
				throw new Error(
					'Quick excuse by student number is unavailable with a live backend — use the review queue row actions or Excuse all absent instead.'
				);
			}
			const offering = directory.find((c) => c.courseCode === quickCourse);
			const picked = quickSessions.find((s) => s.id === quickSessionId) ?? null;
			// Files upload first via the D24 presigned flow; their object urls
			// ride along so the created row mirrors them (Path B). Reason-only
			// stays Path A. Partial failures keep prior successes staged and
			// leave only failed files for retry.
			let attachmentUrls = [...quickStagedUrls];
			if (quickFiles.length > 0) {
				quickUploading = true;
				quickUploadStatus = '';
				try {
					const result = await uploadAttachments(quickFiles, {
						onProgress: (done, total) => {
							quickUploadStatus = `Uploading evidence ${done}/${total}…`;
						},
					});
					attachmentUrls = [...attachmentUrls, ...result.ok];
					if (result.failed.length > 0) {
						quickStagedUrls = attachmentUrls;
						quickFiles = result.failed.map((f) => f.file);
						quickFileErrors = result.failed.map((f) => f.message);
						quickError =
							'Some files failed to upload — retry or remove them. Already-uploaded files are kept.';
						return;
					}
					quickFiles = [];
					quickFileErrors = [];
				} finally {
					quickUploading = false;
					quickUploadStatus = '';
				}
			}
			const created = await quickExcuse({
				studentNumber: quickStudentNumber,
				studentName: quickStudentName || quickStudentNumber,
				section: offering?.section ?? '—',
				courseCode: quickCourse,
				courseName: offering?.courseName ?? quickCourse,
				sessionId: picked?.id ?? offering?.offeringId ?? 1,
				sessionCode: picked?.code ?? 'QUICK',
				originalStatus: quickOriginal,
				reason: quickReason,
				attachmentUrls
			});
			quickOpen = false;
			quickStudentNumber = '';
			quickStudentName = '';
			quickReason = '';
			quickFiles = [];
			quickFileErrors = [];
			quickStagedUrls = [];
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

	const doEditExcuse = async () => {
		if (!selected || editBusy) return;
		editBusy = true;
		editError = null;
		try {
			const updated = await editExcuse(selected, {
				reason: editReason,
				reviewNotes: editNotes
			});
			selected = updated;
			editMode = false;
			notice = `Excuse #${updated.id} updated.`;
			reloadToken += 1;
		} catch (error) {
			editError = error instanceof Error ? error.message : 'Edit failed.';
		} finally {
			editBusy = false;
		}
	};

	const doRevokeExcuse = async () => {
		if (!selected || revokeBusy) return;
		revokeBusy = true;
		revokeError = null;
		try {
			const result = await revokeExcuse(selected);
			selected = { ...selected, status: 'rejected' };
			revokeAsk = false;
			notice =
				result.revertedTo !== null
					? `Excuse #${selected.id} revoked — record reverted to ${result.revertedTo}.`
					: `Excuse #${selected.id} revoked.`;
			reloadToken += 1;
		} catch (error) {
			revokeError = error instanceof Error ? error.message : 'Revoke failed.';
		} finally {
			revokeBusy = false;
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
		<SkeletonTable rows={6} cols={6} label="Loading excuse requests…" />
	{:else if rows.length === 0}
		<section class="card">
			<EmptyState icon="file" title="No excuse requests match these filters" />
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
									{#if row.reviewedByName}
										<div class="status-sub">by {row.reviewedByName}</div>
									{/if}
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
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="excuse-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDetail }}
		>
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
									<li>
										{#if /^(https?:|mock:|file:|\/)/i.test(name)}
											<a href={name} target="_blank" rel="noopener">{name.split('/').pop() ?? name}</a>
										{:else}
											{name}
										{/if}
									</li>
								{/each}
							</ul>
						{/if}
					</dd>
				</div>
				<div>
					<dt>Status</dt>
					<dd><span class="status status-{selected.status}">{selected.status}</span></dd>
				</div>
				{#if selected.reviewedByName}
					<div>
						<dt>Reviewed by</dt>
						<dd>
							{selected.reviewedByName}
							{#if selected.reviewedAt}
								· {formatDate(selected.reviewedAt)}
							{/if}
						</dd>
					</div>
				{/if}
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
				{#if canModify(selected)}
					{#if editMode}
						<label class="form-label" for="edit-reason">Reason (min {EXCUSE_REASON_MIN_LENGTH} chars)</label>
						<textarea
							id="edit-reason"
							class="form-input area"
							rows={3}
							bind:value={editReason}
						></textarea>
						<label class="form-label" for="edit-notes">Review notes</label>
						<textarea
							id="edit-notes"
							class="form-input area"
							rows={2}
							placeholder="Optional context for the change…"
							bind:value={editNotes}
						></textarea>
						{#if editError}
							<p class="error">{editError}</p>
						{/if}
						<div class="modal-actions">
							<button
								class="btn btn-ghost"
								type="button"
								disabled={editBusy}
								onclick={() => {
									editMode = false;
									editReason = selected?.reason ?? '';
									editNotes = selected?.reviewNotes ?? '';
									editError = null;
								}}
							>
								Cancel
							</button>
							<button
								class="btn btn-primary"
								type="button"
								aria-busy={editBusy}
								disabled={editBusy}
								onclick={() => void doEditExcuse()}
							>
								{editBusy ? 'Saving…' : 'Save'}
							</button>
						</div>
					{:else if revokeAsk}
						<p class="modal-sub">
							Revoke this excuse? The attendance record reverts to its original
							status. This cannot be undone from here.
						</p>
						{#if revokeError}
							<p class="error">{revokeError}</p>
						{/if}
						<div class="modal-actions">
							<button
								class="btn btn-ghost"
								type="button"
								disabled={revokeBusy}
								onclick={() => {
									revokeAsk = false;
									revokeError = null;
								}}
							>
								Cancel
							</button>
							<button
								class="btn btn-danger"
								type="button"
								disabled={revokeBusy}
								onclick={() => void doRevokeExcuse()}
							>
								{revokeBusy ? 'Revoking…' : 'Revoke excuse'}
							</button>
						</div>
					{:else}
						{#if revokeError}
							<p class="error">{revokeError}</p>
						{/if}
						<div class="modal-actions">
							<button class="btn btn-ghost" type="button" onclick={closeDetail}>Close</button>
							<button
								class="btn btn-secondary"
								type="button"
								onclick={() => {
									editMode = true;
									editError = null;
								}}
							>
								Edit
							</button>
							<button
								class="btn btn-danger"
								type="button"
								onclick={() => {
									revokeAsk = true;
									revokeError = null;
								}}
							>
								Revoke
							</button>
						</div>
					{/if}
				{:else}
					<div class="modal-actions">
						<button class="btn btn-ghost" type="button" onclick={closeDetail}>Close</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

{#if quickOpen}
	<div class="overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="quick-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeQuick }}
		>
			<h2 id="quick-title">New quick-excuse (Path A)</h2>
			<p class="modal-sub">Approves immediately — for direct-knowledge cases. Min {EXCUSE_REASON_MIN_LENGTH}-char reason.</p>
			{#if !isMockMode()}
				<p class="modal-sub" role="note">
					Live mode: typed numbers cannot resolve to roster records, so this submit is
					kept locally as a demo — use Excuse all absent or the review queue for real records.
				</p>
			{/if}
			<div class="quick-grid">
				<div class="field">
					<label class="form-label" for="quick-number">Student number</label>
					<input
						id="quick-number"
						class="form-input"
						placeholder="ID number as printed on the student card"
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
			{#if quickSessions.length > 0}
				<div class="field">
					<label class="form-label" for="quick-session">Session</label>
					<select
						id="quick-session"
						class="form-input"
						bind:value={quickSessionId}
					>
						{#each quickSessions as session (session.id)}
							<option value={session.id}>#{session.id} · {session.code}</option>
						{/each}
					</select>
				</div>
			{/if}
			<div class="field">
				<label class="form-label" for="quick-original">Original status</label>
					<select id="quick-original" class="form-input" bind:value={quickOriginal}>
						{#each originalOptions as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
				</div>
			</div>
			<label class="form-label" for="quick-reason">Reason (min {EXCUSE_REASON_MIN_LENGTH} chars)</label>
			<textarea
				id="quick-reason"
				class="form-input area"
				rows={3}
				placeholder="e.g. Student informed me after class…"
				bind:value={quickReason}
			></textarea>
			<label class="form-label" for="quick-files">Evidence (optional — with files this files as with-evidence)</label>
			<input
				id="quick-files"
				class="form-input"
				type="file"
				multiple
				accept=".pdf,.jpg,.jpeg,.png,.heic"
				disabled={quickBusy}
				onchange={(e) => onQuickFiles(e.currentTarget.files)}
			/>
			{#if quickFiles.length > 0}
				<ul class="files">
					{#each quickFiles as file, i (file.name + file.size)}
						<li>
							<span>{file.name} · {(file.size / 1024).toFixed(0)} KB</span>
							<button
								class="link-btn"
								type="button"
								disabled={quickBusy}
								onclick={() => (quickFiles = quickFiles.filter((_, j) => j !== i))}
							>
								Remove
							</button>
						</li>
					{/each}
				</ul>
			{/if}
			{#each quickFileErrors as message (message)}
				<p class="error">{message}</p>
			{/each}
			{#if quickStagedUrls.length > 0 && quickFiles.length > 0}
				<p class="modal-sub" role="status">{quickStagedUrls.length} file{quickStagedUrls.length === 1 ? '' : 's'} uploaded — retry the remaining.</p>
			{/if}
			{#if quickUploading}
				<p class="modal-sub" role="status">{quickUploadStatus || 'Uploading evidence…'}</p>
			{/if}
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
					aria-busy={quickBusy}
					disabled={quickBusy}
					onclick={() => void doQuickExcuse()}
				>
					{quickBusy ? 'Saving…' : 'Excuse now'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.excuses {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		max-width: 1000px;
		margin: 0 auto;
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
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.notice {
		margin: 0;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
		color: var(--success);
		font-size: 0.875rem;
		font-weight: 600;
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
		margin: 0.75rem 0 0;
		color: var(--danger-strong);
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
		color: var(--text-secondary);
	}

	.form-input {
		padding: 0.625rem 0.75rem;
		border: 1.5px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
		outline: none;
	}

	.form-input:focus {
		border-color: var(--accent);
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
		background: var(--accent);
		color: var(--on-brand);
		border-color: var(--accent);
		white-space: nowrap;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.btn-ghost {
		background: var(--bg-card);
		border-color: var(--border-strong);
		color: var(--brand);
	}

	.btn-ghost:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.btn-secondary {
		background: var(--bg-muted);
		color: var(--text-secondary);
		border-color: var(--border);
	}

	.btn-danger {
		background: var(--danger);
		color: var(--on-brand);
		border-color: var(--danger);
	}

	.btn-danger:hover:not(:disabled) {
		background: var(--danger-strong);
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
		background: var(--bg-page);
		border-bottom: 1px solid var(--border);
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
	}

	td {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--divider);
		font-size: 0.9375rem;
		color: var(--text);
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
		color: var(--text-muted);
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
		color: var(--warning-text);
		background: var(--warning-bg);
		border: 1px solid var(--warning-bg);
	}

	.status-approved {
		color: var(--success);
		background: var(--success-bg);
		border: 1px solid var(--success-bg);
	}

	.status-rejected {
		color: var(--danger-strong);
		background: var(--danger-bg);
		border: 1px solid var(--danger-bg);
	}

	.mini {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 6px;
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
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
		background: var(--overlay);
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
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.5rem;
	}

	.modal h2 {
		margin: 0 0 0.25rem;
		font-size: 1.125rem;
		color: var(--text);
	}

	.modal-sub {
		margin: 0 0 1rem;
		font-size: 0.875rem;
		color: var(--text-muted);
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
		color: var(--text-muted);
	}

	.detail dd {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text);
	}

	.files {
		margin: 0;
		padding-left: 1.25rem;
	}

	.files li {
		margin-bottom: 0.25rem;
	}

	.link-btn {
		border: 0;
		background: none;
		padding: 0;
		margin-left: 0.5rem;
		color: var(--accent);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		text-decoration: underline;
	}

	.link-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
