<script lang="ts">
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
	// Records whose face_match_score fell in the review band stay actionable
	// only while pending; resolving via the buttons below approves (restores
	// present/late) or rejects them, and writes an audit row.
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
	let reviewNote = $state('');

	// alive-guard: if the route unmounts while the first load is in flight,
	// destroy has already run and the focus revalidate must not attach.
	let pageAlive = true;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		pageAlive = false;
		for (const stop of autoRefreshStops) stop();
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

	// Aggregate page: no entity subscriptions — the queue is a point-in-time
	// read. Tab focus re-runs it with the current status filter.
	const refreshVisible = () => {
		if (liveLoading) return;
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
			await resolveLivenessReview(id, decision, reviewNote);
			reviewNote = '';
			await loadLiveness();
		} catch (e) {
			liveError = e instanceof Error ? e.message : 'Could not resolve this record.';
		} finally {
			resolvingId = null;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Attendance Review</h1>
			<p class="muted">Flagged scans (GPS / face review band) · {liveTotal} {liveStatus}</p>
		</div>
	</header>

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
							<td>{formatLocalDateTime(row.scanned_at)}</td>
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
