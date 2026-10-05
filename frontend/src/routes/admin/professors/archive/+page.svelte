<script lang="ts">
	import { onMount } from 'svelte';
	import {
		adminProfessorsState,
		deleteArchivedProfessor,
		initAdminProfessors,
		toggleProfessorActive,
	} from '$lib/features/admin/store.svelte';
	import type { AdminProfessor } from '$lib/shared/types';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Professors archive (wireframe 4.10): inactive roster rows only.
	// Restore flips is_active back on; Delete permanently removes the row
	// (backend allows it only with no sessions referencing them, else 409).
	// No new backend — the list endpoint's is_active filter.

	let search = $state('');
	let deleteTarget = $state<AdminProfessor | null>(null);
	let deleteBusy = $state(false);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminProfessorsState.total / adminProfessorsState.size))
	);

	const load = (page = 1) =>
		initAdminProfessors(
			{ search: search.trim() || undefined, is_active: false },
			page,
			adminProfessorsState.size
		);

	onMount(() => {
		load(1);
	});

	const applyFilters = () => {
		load(1);
	};

	const fullName = (p: AdminProfessor) =>
		[p.firstName, p.middleName, p.lastName].filter(Boolean).join(' ');

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedProfessor(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Archived Professors</h1>
			<p class="muted">Inactive roster rows · {adminProfessorsState.total} total</p>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search name, email…"
			aria-label="Search archived professors"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<button class="btn btn-secondary" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminProfessorsState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminProfessorsState.error}
		<section class="card"><p class="error">Could not load archive: {adminProfessorsState.error}</p></section>
	{:else if adminProfessorsState.items.length === 0}
		<section class="card">
			<p class="empty">Archive is empty. Deactivated professors appear here.</p>
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminProfessorsState.actionError}
				<p class="error" role="alert">{adminProfessorsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th>Name</th>
						<th>Email</th>
						<th>Department</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminProfessorsState.items as p (p.id)}
						<tr>
							<td>{fullName(p)}</td>
							<td class="mono">{p.email}</td>
							<td>{p.department ?? '—'}</td>
							<td class="row-actions">
								<button class="link" onclick={() => toggleProfessorActive(p).catch(() => {})}>
									Restore
								</button>
								<button class="link danger" onclick={() => (deleteTarget = p)}>Delete</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminProfessorsState.page <= 1}
					onclick={() => load(adminProfessorsState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminProfessorsState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminProfessorsState.page >= totalPages}
					onclick={() => load(adminProfessorsState.page + 1)}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if deleteTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteTarget = null) }}
		>
			<h2 id="delete-title" class="modal-title">Permanently delete?</h2>
			<p class="modal-text">
				{fullName(deleteTarget)} will be removed for good. This fails with 409 if
				sessions still reference them.
			</p>
			{#if adminProfessorsState.actionError}
				<p class="error" role="alert">{adminProfessorsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDelete}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
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
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
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

	.search {
		flex: 1 1 240px;
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
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 500;
	}

	.row-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.link {
		background: none;
		border: none;
		padding: 0;
		color: var(--accent);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
	}

	.link.danger {
		color: var(--danger);
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
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

	.btn-ghost {
		background: var(--divider);
		border: 1px solid transparent;
		color: var(--text-secondary);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.modal-overlay {
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
		max-width: 480px;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	.table-wrap {
		overflow-x: auto;
	}
</style>
