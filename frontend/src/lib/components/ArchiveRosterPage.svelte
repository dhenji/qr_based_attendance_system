<script lang="ts" generics="T extends ArchiveRosterItem">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import {
		archiveRosterFullName,
		type ArchiveRosterConfig,
		type ArchiveRosterItem,
		type ArchiveRosterState
	} from '$lib/components/archive-roster';

	// Shared archive roster (wireframe 4.10): inactive rows only. Restore
	// flips is_active back on; Delete permanently removes the row (the
	// backend returns 409 when history still references it). No new backend —
	// the list endpoint's is_active filter does the work.
	// Auto-refresh (issue #221): own-entity events and tab focus re-run the
	// archived query; restores/deletes emit via the store.
	let {
		config,
		roster,
		onLoad,
		onRefresh,
		onDelete,
		onToggle,
		onClearActionError
	}: {
		config: ArchiveRosterConfig<T>;
		roster: ArchiveRosterState<T>;
		onLoad: (page: number, search: string) => void | Promise<unknown>;
		onRefresh: () => void | Promise<unknown>;
		onDelete: (id: number) => Promise<unknown>;
		onToggle: (item: T) => Promise<unknown>;
		onClearActionError: () => void;
	} = $props();

	let search = $state('');
	let deleteTarget = $state<T | null>(null);
	let deleteBusy = $state(false);
	let toggleTarget = $state<T | null>(null);
	let toggleBusy = $state(false);
	const autoRefreshStops: (() => void)[] = [];

	const totalPages = $derived(Math.max(1, Math.ceil(roster.total / roster.size)));

	const applyFilters = () => {
		void onLoad(1, search);
	};

	const refreshVisible = () => {
		if (!roster.loading) void onRefresh();
	};

	onMount(() => {
		void onLoad(1, search);
		autoRefreshStops.push(
			subscribeEntity(config.entity, refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const openRestore = (item: T) => {
		onClearActionError();
		toggleTarget = item;
	};

	const openDelete = (item: T) => {
		onClearActionError();
		deleteTarget = item;
	};

	const confirmDelete = async () => {
		if (!deleteTarget || deleteBusy) return;
		deleteBusy = true;
		try {
			await onDelete(deleteTarget.id);
			deleteTarget = null;
		} catch {
			// The store surfaces the failure through `roster.actionError`; keep
			// the modal open so the admin can read it.
		} finally {
			deleteBusy = false;
		}
	};

	const confirmToggle = async () => {
		if (!toggleTarget || toggleBusy) return;
		toggleBusy = true;
		try {
			await onToggle(toggleTarget);
			if (!roster.actionError) toggleTarget = null;
		} finally {
			toggleBusy = false;
		}
	};
</script>

<div class="page">
	<button class="btn btn-secondary back" data-testid={config.backTestId} onclick={() => goto(config.backRoute)}>
		‹ {config.backLabel}
	</button>
	<header class="header">
		<div>
			<h1>{config.heading}</h1>
			<p class="muted">Inactive roster rows · {roster.total} total</p>
		</div>
	</header>

	<section class="card filters">
		<input
			class="form-input search"
			type="search"
			placeholder="Search name, email…"
			aria-label={config.searchAriaLabel}
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<button class="btn btn-secondary" onclick={applyFilters}>Apply</button>
	</section>

	{#if roster.loading}
		<SkeletonTable rows={6} cols={4} label={config.loadingLabel} />
	{:else if roster.error}
		<section class="card"><p class="error">Could not load archive: {roster.error}</p></section>
	{:else if roster.items.length === 0}
		<section class="card">
			<EmptyState icon="file" title="Archive is empty" hint={config.emptyHint} />
		</section>
	{:else}
		<section class="card table-wrap">
			{#if roster.actionError}
				<p class="error" role="alert">{roster.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col">Name</th>
						<th scope="col">Email</th>
						<th scope="col">{config.detailColumnLabel}</th>
						<th scope="col"><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each roster.items as item (item.id)}
						<tr>
							<td>{archiveRosterFullName(item)}</td>
							<td class="mono">{item.email}</td>
							<td>{config.detailValue(item)}</td>
							<td>
								<div class="row-actions">
									<button class="link success" onclick={() => openRestore(item)}>
										Restore
									</button>
									<button class="link danger" onclick={() => openDelete(item)}>Delete</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<Pagination
				variant="compact"
				page={roster.page}
				totalPages={totalPages}
				onPageChange={(next) => void onLoad(next, search)}
				ariaLabel="Archive pages"
			/>
		</section>
	{/if}
</div>

{#if toggleTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="restore-archived-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (toggleBusy ? undefined : (toggleTarget = null)) }}
		>
			<h2 id="restore-archived-title" class="modal-title">{config.restoreTitle}</h2>
			<p class="modal-text">
				{config.restoreDescription(toggleTarget)}
			</p>
			{#if roster.actionError}
				<p class="error" role="alert">{roster.actionError}</p>
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
			aria-labelledby="delete-archived-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteBusy ? undefined : (deleteTarget = null)) }}
		>
			<h2 id="delete-archived-title" class="modal-title">Permanently delete?</h2>
			<p class="modal-text">
				{config.deleteDescription(deleteTarget)}
			</p>
			{#if roster.actionError}
				<p class="error" role="alert">{roster.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={deleteBusy} onclick={() => (deleteTarget = null)}>Cancel</button>
				<button class="btn btn-danger" aria-busy={deleteBusy} disabled={deleteBusy} onclick={confirmDelete}>
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

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
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
