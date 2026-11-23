<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import {
		listLivenessReview,
		resolveLivenessReview,
		type LivenessStatus,
	} from '$lib/features/admin/liveness/service';
	import type { LivenessReviewItemResponse } from '$lib/api/endpoints';
	import { formatLocalDateTime } from '$lib/shared/utils/format';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';

	// Attendance Review (wireframe 4.12): the flagged-scan decision queue.
	// Borderline scans (face review band 0.65-0.70, or geofence uncertainty)
	// stay actionable only while pending; resolving via the buttons below
	// approves (confirms present/late) or rejects them, and writes an audit row.
	//
	// The per-course attendance snapshot that used to share this route now
	// lives in Analytics & Reports (the "Attendance" tab); this page owns the
	// review workflow only.

	let liveStatus = $state<LivenessStatus>('pending');
	let liveItems = $state<LivenessReviewItemResponse[]>([]);
	let liveTotal = $state(0);
	let liveLoading = $state(false);
	let liveError = $state<string | null>(null);
	let resolvingId = $state<number | null>(null);
	let loadToken = $state(0);
	let confirmTarget = $state<{ id: number; decision: 'approve' | 'reject' } | null>(null);
	// Per-row review notes (the previous single global input leaked a note
	// typed for one row into the decision for a different row).
	let reviewNotes = $state<Record<number, string>>({});

	// Pagination
	let livePage = $state(1);
	let liveSize = $state(20);
	const totalPages = $derived(Math.max(1, Math.ceil(liveTotal / liveSize)));

	// Client-side filters (backend review endpoint only accepts status/page/size)
	let filterCourse = $state('All');
	let filterDateFrom = $state('');
	let filterDateTo = $state('');

	const courseOptions = $derived.by(() => {
		const codes = new Set<string>();
		for (const r of liveItems) if (r.course_code) codes.add(r.course_code);
		return [...codes].sort();
	});

	const filteredItems = $derived.by(() => {
		return liveItems.filter((row) => {
			if (filterCourse !== 'All' && row.course_code !== filterCourse) return false;
			const day = row.scanned_at ? row.scanned_at.slice(0, 10) : '';
			if (filterDateFrom && day < filterDateFrom) return false;
			if (filterDateTo && day > filterDateTo) return false;
			return true;
		});
	});

	const confirmRow = $derived(
		confirmTarget ? (liveItems.find((r) => r.id === confirmTarget!.id) ?? null) : null
	);

	// alive-guard: if the route unmounts while the first load is in flight,
	// destroy has already run and the focus revalidate must not attach.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		for (const stop of autoRefreshStops) stop();
	});

	const loadLiveness = async () => {
		const token = ++loadToken;
		liveLoading = true;
		liveError = null;
		try {
			const response = await listLivenessReview({ status: liveStatus, page: livePage, size: liveSize });
			if (token !== loadToken) return;
			liveItems = response.items ?? [];
			liveTotal = response.total ?? liveItems.length;
		} catch (e) {
			if (token !== loadToken) return;
			liveError = e instanceof Error ? e.message : 'Could not load the review queue.';
		} finally {
			if (token === loadToken) liveLoading = false;
		}
	};

	// Aggregate page: no entity subscriptions — the queue is a point-in-time
	// read. Tab focus re-runs it with the current status filter.
	const refreshVisible = () => {
		if (liveLoading || resolvingId !== null) return;
		void loadLiveness();
	};

	onMount(async () => {
		await loadLiveness();
		if (!pageAlive) return;
		autoRefreshStops.push(onFocusRevalidate(refreshVisible));
	});

	const resolveRow = async (id: number, decision: 'approve' | 'reject') => {
		if (resolvingId !== null) return;
		resolvingId = id;
		liveError = null;
		try {
			await resolveLivenessReview(id, decision, reviewNotes[id] ?? '');
			reviewNotes[id] = '';
		} catch (e) {
			liveError = e instanceof Error ? e.message : 'Could not resolve this record.';
		} finally {
			resolvingId = null;
		}
		confirmTarget = null;
		await loadLiveness();
	};

	const goToPage = (p: number) => {
		const next = Math.min(Math.max(1, p), totalPages);
		if (next === livePage) return;
		livePage = next;
		void loadLiveness();
	};

	// Per-row expand state for the evidence bundle. Stored as a reactive
	// record (not a Set) so property assignment triggers re-render.
	let expanded = $state<Record<number, boolean>>({});
	const toggleEvidence = (id: number) => {
		expanded[id] = !expanded[id];
	};

	// Safe accessors for the free-form evidence dict (backend shape is
	// LivenessEvidence + accuracy/review/review_note, but we never trust it).
	const asRecord = (v: unknown): Record<string, unknown> =>
		v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
	const asBool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);
	const asNum = (v: unknown): number | null =>
		typeof v === 'number' && Number.isFinite(v) ? v : null;
	const asStr = (v: unknown): string | null => (typeof v === 'string' ? v : null);
	const asNums = (v: unknown): number[] =>
		Array.isArray(v) ? v.filter((x): x is number => typeof x === 'number' && Number.isFinite(x)) : [];

	const evidenceOf = (row: LivenessReviewItemResponse) => asRecord(row.evidence);
	const earStats = (samples: number[]) => {
		if (samples.length === 0) return null;
		const min = Math.min(...samples);
		const max = Math.max(...samples);
		const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
		return { min, max, mean };
	};
	const fmtNum = (v: number | null, digits = 2) => (v === null ? '—' : v.toFixed(digits));
	const fmtBool = (v: boolean | null) => (v === null ? '—' : v ? 'Yes' : 'No');
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Attendance Review</h1>
			<p class="muted">Flagged scans (borderline face match or GPS uncertainty) · {liveTotal} {liveStatus}</p>
		</div>
	</header>

	<section class="card filters" aria-label="Review filters">
		<select
			class="input"
			aria-label="Review status"
			bind:value={liveStatus}
			onchange={() => { livePage = 1; void loadLiveness(); }}
		>
			<option value="pending">Pending</option>
			<option value="approved">Approved</option>
			<option value="rejected">Rejected</option>
		</select>
		<select
			class="input"
			aria-label="Filter by course"
			bind:value={filterCourse}
		>
			<option value="All">All courses</option>
			{#each courseOptions as code (code)}
				<option value={code}>{code}</option>
			{/each}
		</select>
		<input
			class="input"
			type="date"
			aria-label="Scanned from"
			bind:value={filterDateFrom}
		/>
		<input
			class="input"
			type="date"
			aria-label="Scanned to"
			bind:value={filterDateTo}
		/>
		<button class="btn btn-secondary" onclick={() => void loadLiveness()}>Refresh</button>
	</section>

	{#if liveLoading && liveItems.length === 0}
		<SkeletonTable rows={6} cols={6} label="Loading review queue…" />
	{:else if liveError}
		<section class="card"><p class="error">{liveError}</p></section>
	{:else if liveItems.length === 0}
		<section class="card">
			<EmptyState
				icon="check"
				title={`No ${liveStatus} records in the review queue`}
			/>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={liveLoading}>
			<table>
				<thead>
					<tr>
						<th scope="col">Student</th>
						<th scope="col">Session</th>
						<th scope="col">Score</th>
						<th scope="col">Evidence</th>
						<th scope="col">Scanned</th>
						{#if liveStatus === 'pending'}<th scope="col">Decision</th>{/if}
					</tr>
				</thead>
				<tbody>
					{#if filteredItems.length === 0}
						<tr><td colspan="6" class="muted">No rows match the current filters.</td></tr>
					{/if}
					{#each filteredItems as row (row.id)}
						<tr>
							<td>
								<span class="strong">{row.student_name}</span>
								<div class="muted small">{row.student_number} · {row.course_code}</div>
							</td>
							<td>{row.session_code}</td>
							<td>{row.face_match_score == null ? '—' : row.face_match_score.toFixed(2)}</td>
							<td>
								<button
									class="btn btn-secondary btn-sm"
									type="button"
									aria-expanded={expanded[row.id] ? 'true' : 'false'}
									aria-controls={`evidence-${row.id}`}
									onclick={() => toggleEvidence(row.id)}
								>
									{expanded[row.id] ? 'Hide' : 'View'}
								</button>
							</td>
							<td>{formatLocalDateTime(row.scanned_at)}</td>
							{#if liveStatus === 'pending'}
								<td>
									<div class="row-actions">
										<input
											class="input input-sm"
											type="text"
											placeholder="Note (optional)"
											aria-label={`Review note for ${row.student_number}`}
											maxlength={1000}
											bind:value={reviewNotes[row.id]}
										/>
										<button
											class="btn btn-secondary"
											type="button"
											disabled={resolvingId !== null}
											onclick={() => (confirmTarget = { id: row.id, decision: 'approve' })}
										>
											Approve
										</button>
										<button
											class="btn btn-secondary"
											type="button"
											disabled={resolvingId !== null}
											onclick={() => (confirmTarget = { id: row.id, decision: 'reject' })}
										>
											Reject
										</button>
									</div>
								</td>
							{/if}
						</tr>
						{#if expanded[row.id]}
							{@const ev = evidenceOf(row)}
							{@const samples = asNums(ev.ear_samples)}
							{@const stats = earStats(samples)}
							{@const pnp = asRecord(ev.pnp_evidence)}
							<tr class="evidence-row" id={`evidence-${row.id}`}>
								<td colspan="6">
									<div class="evidence-panel">
										<div class="evidence-group">
											<h3 class="evidence-title">Challenge</h3>
											<dl class="evidence-dl">
												<div><dt>Blink detected</dt><dd class:ok={asBool(ev.blink_detected) === true} class:bad={asBool(ev.blink_detected) === false}>{fmtBool(asBool(ev.blink_detected))}</dd></div>
												<div><dt>Head turn left</dt><dd class:ok={asBool(ev.head_turn_left) === true} class:bad={asBool(ev.head_turn_left) === false}>{fmtBool(asBool(ev.head_turn_left))}</dd></div>
												<div><dt>Head turn right</dt><dd class:ok={asBool(ev.head_turn_right) === true} class:bad={asBool(ev.head_turn_right) === false}>{fmtBool(asBool(ev.head_turn_right))}</dd></div>
												<div><dt>Face count</dt><dd>{fmtNum(asNum(ev.face_count), 0)}</dd></div>
											</dl>
										</div>
										<div class="evidence-group">
											<h3 class="evidence-title">Eye aspect ratio</h3>
											<dl class="evidence-dl">
												<div><dt>Samples</dt><dd>{samples.length}</dd></div>
												{#if stats}
													<div><dt>Mean</dt><dd>{stats.mean.toFixed(3)}</dd></div>
													<div><dt>Min / Max</dt><dd>{stats.min.toFixed(3)} / {stats.max.toFixed(3)}</dd></div>
												{:else}
													<div><dt>Mean</dt><dd>—</dd></div>
												{/if}
											</dl>
										</div>
										<div class="evidence-group">
											<h3 class="evidence-title">Head pose (PnP)</h3>
											<dl class="evidence-dl">
												<div><dt>Source</dt><dd>{asStr(pnp.source) ?? '—'}</dd></div>
												<div><dt>Baseline yaw</dt><dd>{fmtNum(asNum(pnp.baseline_yaw), 1)}°</dd></div>
												<div><dt>Yaw</dt><dd>{fmtNum(asNum(pnp.yaw), 1)}°</dd></div>
												<div><dt>Peak left</dt><dd>{fmtNum(asNum(pnp.peak_left_yaw), 1)}°</dd></div>
												<div><dt>Peak right</dt><dd>{fmtNum(asNum(pnp.peak_right_yaw), 1)}°</dd></div>
												<div><dt>Yaw samples</dt><dd>{asNums(pnp.yaw_samples).length}</dd></div>
											</dl>
										</div>
										{#if asStr(evidenceOf(row).review_reason)?.includes('geofence_uncertainty')}
										{@const g = asRecord(evidenceOf(row).geofence)}
										<div class="evidence-group">
											<h3 class="evidence-title">Geofence</h3>
											<dl class="evidence-dl">
												<div><dt>Distance</dt><dd>{asNum(g.distance_meters) === null ? '—' : `${asNum(g.distance_meters)!.toFixed(1)} m`}</dd></div>
												<div><dt>Radius</dt><dd>{asNum(g.radius_meters) === null ? '—' : `${asNum(g.radius_meters)} m`}</dd></div>
												<div><dt>GPS accuracy</dt><dd>{asNum(g.accuracy_meters) === null ? '—' : `${asNum(g.accuracy_meters)!.toFixed(1)} m`}</dd></div>
												<div><dt>Uncertainty</dt><dd>{asNum(g.uncertainty_meters) === null ? '—' : `${asNum(g.uncertainty_meters)!.toFixed(1)} m`}</dd></div>
												<div><dt>Classroom</dt><dd>{asNum(g.classroom_lat) === null ? '—' : `${asNum(g.classroom_lat)}, ${asNum(g.classroom_lng)}`}</dd></div>
											</dl>
										</div>
										{/if}
										<div class="evidence-group">
											<h3 class="evidence-title">Context</h3>
											<dl class="evidence-dl">
												<div><dt>GPS accuracy</dt><dd>{asNum(ev.accuracy) === null ? '—' : `${asNum(ev.accuracy)!.toFixed(1)} m`}</dd></div>
												<div><dt>Review band</dt><dd>{asBool(ev.review) ? 'Yes' : 'No'}</dd></div>
<div><dt>Review reason</dt><dd>{asStr(ev.review_reason) ?? '—'}</dd></div>
												{#if asStr(ev.review_note)}
													<div><dt>Review note</dt><dd>{asStr(ev.review_note)}</dd></div>
												{/if}
											</dl>
										</div>
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<span class="muted small">
					Showing {filteredItems.length} of {liveItems.length} on this page · {liveTotal} total
				</span>
				<div class="row-actions">
					<button class="btn btn-secondary" type="button" disabled={livePage <= 1 || liveLoading} onclick={() => goToPage(livePage - 1)}>Prev</button>
					<span class="muted small">Page {livePage} of {totalPages}</span>
					<button class="btn btn-secondary" type="button" disabled={livePage >= totalPages || liveLoading} onclick={() => goToPage(livePage + 1)}>Next</button>
				</div>
			</div>
		</section>
	{/if}

	{#if confirmTarget && confirmRow}
		<Modal
			title={confirmTarget.decision === 'approve' ? 'Confirm Approval' : 'Confirm Rejection'}
			onclose={() => (confirmTarget = null)}
			closeOnBackdrop={false}
		>
			<p class="confirm-message">
				{confirmTarget.decision === 'approve'
					? 'Approve this flagged scan and confirm it as present/late?'
					: 'Reject this flagged scan and mark it as rejected?'}
			</p>
			<dl class="confirm-details">
				<div class="confirm-row"><dt>Student</dt><dd>{confirmRow.student_name} ({confirmRow.student_number})</dd></div>
				<div class="confirm-row"><dt>Session</dt><dd>{confirmRow.session_code}</dd></div>
				<div class="confirm-row"><dt>Course</dt><dd>{confirmRow.course_code}</dd></div>
				<div class="confirm-row"><dt>Score</dt><dd>{confirmRow.face_match_score == null ? '—' : confirmRow.face_match_score.toFixed(2)}</dd></div>
				{#if (reviewNotes[confirmRow.id] ?? '').trim()}
					<div class="confirm-row"><dt>Note</dt><dd>{reviewNotes[confirmRow.id]}</dd></div>
				{/if}
			</dl>
			{#snippet footer()}
				<button
					class="btn btn-ghost"
					type="button"
					disabled={resolvingId !== null}
					onclick={() => (confirmTarget = null)}
				>
					Cancel
				</button>
				<button
					class="btn btn-primary"
					type="button"
					disabled={resolvingId !== null}
					aria-busy={resolvingId !== null}
					onclick={() => void resolveRow(confirmTarget!.id, confirmTarget!.decision)}
				>
					{resolvingId !== null
						? 'Processing…'
						: confirmTarget!.decision === 'approve'
							? 'Approve'
							: 'Reject'}
				</button>
			{/snippet}
		</Modal>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
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

	.row-actions {
		display: flex;
		gap: 0.5rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
	}

	.table-wrap {
		overflow-x: auto;
	}

	.btn-sm {
		padding: 0.375rem 0.625rem;
		font-size: 0.75rem;
	}

	.input-sm {
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		min-width: 8rem;
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--divider);
	}

	.evidence-row td {
		background: var(--bg-subtle, var(--divider));
		padding: 0.75rem;
	}

	.evidence-panel {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
		gap: 1rem;
	}

	.evidence-group {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.75rem 1rem;
	}

	.evidence-title {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
		margin: 0 0 0.5rem;
	}

	.evidence-dl {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.25rem;
		margin: 0;
	}

	.evidence-dl > div {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.8125rem;
	}

	.evidence-dl dt {
		color: var(--text-muted);
	}

	.evidence-dl dd {
		margin: 0;
		font-weight: 600;
		color: var(--text-strong);
	}

	.evidence-dl dd.ok {
		color: var(--success, #16a34a);
	}

	.evidence-dl dd.bad {
		color: var(--danger);
	}

	/* Intentional transparent toolbar variant. */
	.btn-ghost {
		background: transparent;
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-ghost:hover:not(:disabled) {
		background: var(--divider);
	}

	.confirm-message {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-muted);
	}

	.confirm-details {
		margin: 0;
		display: grid;
		gap: 0.375rem;
		padding: 0.75rem;
		border-radius: 8px;
		background: var(--bg-subtle, var(--divider));
		border: 1px solid var(--border);
	}

	.confirm-row {
		display: flex;
		gap: 0.75rem;
		font-size: 0.875rem;
	}

	.confirm-row dt {
		font-weight: 600;
		color: var(--text);
		min-width: 5rem;
	}

	.confirm-row dd {
		margin: 0;
		color: var(--text-strong);
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
