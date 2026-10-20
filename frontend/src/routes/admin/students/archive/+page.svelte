<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		adminStudentsState,
		deleteArchivedStudent,
		initAdminStudents,
		refreshAdminStudents,
		toggleStudentActive,
	} from '$lib/features/admin/store.svelte';
	import type { AdminStudent } from '$lib/shared/types';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { Routes } from '$lib/shared/constants/routes';

	// Students archive (wireframe 4.10): inactive roster rows only.
	// Restore flips is_active back on; Delete permanently removes the row
	// (backend allows it only with no enrollments/attendance/excuse records,
	// else 409). No new backend — the list endpoint's is_active filter.
	// Auto-refresh (issue #221): own-entity events (list-page edits) and tab
	// focus re-run the archived query; restores/deletes emit via the store.

	let search = $state('');
	let deleteTarget = $state<AdminStudent | null>(null);
	let deleteBusy = $state(false);
	let toggleTarget = $state<AdminStudent | null>(null);
	let toggleBusy = $state(false);
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminStudentsState.total / adminStudentsState.size))
	);

	const load = (page = 1) =>
		initAdminStudents(
			{ search: search.trim() || undefined, is_active: false },
			page,
			adminStudentsState.size
		);

	const refreshVisible = () => {
		if (!adminStudentsState.loading) void refreshAdminStudents();
	};

	onMount(() => {
		load(1);
		autoRefreshStops.push(
			subscribeEntity('students', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	const applyFilters = () => {
		load(1);
	};

	const fullName = (s: AdminStudent) =>
		[s.firstName, s.middleName, s.lastName].filter(Boolean).join(' ');

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedStudent(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const confirmToggle = async () => {
		if (!toggleTarget || toggleBusy) return;
		toggleBusy = true;
		try {
			await toggleStudentActive(toggleTarget);
			if (!adminStudentsState.actionError) toggleTarget = null;
		} finally {
			toggleBusy = false;
		}
	};
</script>

<div class="page">
	<button class="btn btn-secondary back" data-testid="back-to-students" onclick={() => goto(Routes.ADMIN_STUDENTS)}>
		‹ Back to students
	</button>
	<header class="header">
		<div>
			<h1>Archived Students</h1>
			<p class="muted">Inactive roster rows · {adminStudentsState.total} total</p>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search name, email…"
			aria-label="Search archived students"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<button class="btn btn-secondary" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminStudentsState.loading}
		<SkeletonTable rows={6} cols={4} label="Loading archived students…" />
	{:else if adminStudentsState.error}
		<section class="card"><p class="error">Could not load archive: {adminStudentsState.error}</p></section>
	{:else if adminStudentsState.items.length === 0}
		<section class="card">
			<EmptyState icon="file" title="Archive is empty" hint="Deactivated students appear here." />
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th>Name</th>
						<th>Email</th>
						<th>Program</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminStudentsState.items as s (s.id)}
						<tr>
							<td>{fullName(s)}</td>
							<td class="mono">{s.email}</td>
							<td>{s.programCode}</td>
							<td>
								<div class="row-actions">
									<button
										class="link success"
										onclick={() => {
											adminStudentsState.actionError = null;
											toggleTarget = s;
										}}
									>
										Restore
									</button>
									<button class="link danger" onclick={() => { adminStudentsState.actionError = null; deleteTarget = s; }}>Delete</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminStudentsState.page <= 1}
					onclick={() => load(adminStudentsState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminStudentsState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminStudentsState.page >= totalPages}
					onclick={() => load(adminStudentsState.page + 1)}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if toggleTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="restore-student-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (toggleBusy ? undefined : (toggleTarget = null)) }}
		>
			<h2 id="restore-student-title" class="modal-title">Reactivate student?</h2>
			<p class="modal-text">
				{fullName(toggleTarget)} will return to the active roster and regain login access. Face enrollment will need to be re-enrolled.
			</p>
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={toggleBusy} onclick={() => (toggleTarget = null)}>Cancel</button>
				<button class="btn btn-success" aria-busy={toggleBusy} disabled={toggleBusy} onclick={() => void confirmToggle()}>
					{toggleBusy ? 'Saving…' : 'Restore'}
				</button>
			</div>
		</div>
	</div>
{/if}

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
				{fullName(deleteTarget)} will be removed for good. If enrollment, attendance, or
				excuse history is still linked, deletion will be blocked and the record stays archived.
			</p>
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
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
	}

	.back {
		align-self: flex-start;
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

	.link.success {
		color: var(--success);
	}

	.btn-success {
		background: var(--success);
		border: 1px solid var(--success);
		color: var(--on-brand);
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

	.btn-secondary:hover {
		background: var(--divider);
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
