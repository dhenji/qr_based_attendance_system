<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listAdminExcuses,
		type AdminExcuseStatus
	} from '$lib/features/admin/excuses/service';
	import { formatLocalDateTime } from '$lib/shared/utils/format';

	// Admin excuse workload (api-contracts §Excuses Admin View): read-only
	// queue across courses. Review actions live on the professor excuse queue;
	// this page surfaces pending load and status without duplicating them.

	let status = $state<AdminExcuseStatus>('pending');
	let items = $state<Awaited<ReturnType<typeof listAdminExcuses>>['items']>([]);
	let total = $state(0);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const humanizeInitiatedVia = (value: string): string => {
		if (value === 'quick') return 'Quick excuse';
		if (value === 'prof_with_evidence') return 'With evidence';
		if (value === 'request') return 'Student request';
		return value ? value.replace(/_/g, ' ') : '—';
	};

	const load = async () => {
		loading = true;
		error = null;
		try {
			const response = await listAdminExcuses({ status, page: 1, size: 20 });
			items = response.items ?? [];
			total = response.total ?? items.length;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not load excuse requests.';
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		void load();
	});
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Excuse Requests</h1>
			<p class="muted">
				{total} {status} · read-only workload view — approvals happen on the professor queue.
			</p>
		</div>
	</header>

	<section class="card filters" aria-label="Excuse filters">
		<select
			class="input"
			aria-label="Status filter"
			bind:value={status}
			onchange={() => void load()}
		>
			<option value="pending">Pending</option>
			<option value="approved">Approved</option>
			<option value="rejected">Rejected</option>
		</select>
		<button class="btn btn-secondary" type="button" onclick={() => void load()}>Refresh</button>
	</section>

	{#if loading}
		<section class="card"><p class="muted">Loading excuse requests…</p></section>
	{:else if error}
		<section class="card">
			<p class="error">{error}</p>
			<button class="btn btn-secondary" type="button" onclick={() => void load()}>Retry</button>
		</section>
	{:else if items.length === 0}
		<section class="card"><p class="empty">No {status} excuse requests. New ones appear here as students and professors submit them.</p></section>
	{:else}
		<section class="card table-wrap">
			<table>
				<thead>
					<tr>
						<th>Student</th>
						<th>Class</th>
						<th>Reason</th>
						<th>Requested</th>
						<th>Reviewed</th>
					</tr>
				</thead>
				<tbody>
					{#each items as row (row.id)}
						<tr>
							<td>
								<span class="strong">{row.student_name}</span>
								<div class="muted small">
									{row.student_number}
									{row.student_section ? ` · Section ${row.student_section}` : ''}
									· {humanizeInitiatedVia(row.initiated_via)} · {row.status}
								</div>
							</td>
							<td>
								<div class="strong">{row.course_code} · {row.course_name}</div>
								<div class="muted small">Session {row.session_code}</div>
							</td>
							<td class="reason">{row.reason}</td>
							<td>{formatLocalDateTime(row.requested_at)}</td>
							<td>
								{#if row.reviewed_by_name}
									<div class="strong">{row.reviewed_by_name}</div>
									<div class="muted small">
										{row.reviewed_at ? formatLocalDateTime(row.reviewed_at) : ''}
									</div>
								{:else}
									<span class="muted">—</span>
								{/if}
							</td>
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

	.table-wrap {
		overflow-x: auto;
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
		vertical-align: top;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.strong {
		font-weight: 700;
	}

	.reason {
		max-width: 28rem;
	}

	.empty {
		color: var(--text-muted);
		margin: 0;
	}

	.error {
		color: var(--danger);
		margin: 0;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.625rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}
</style>
