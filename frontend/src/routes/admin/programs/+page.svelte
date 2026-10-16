<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminProgramsState,
		deleteArchivedProgram,
		initAdminPrograms,
		refreshAdminPrograms,
		toggleProgramActive,
		type ProgramSortColumn,
	} from '$lib/features/admin/programs/store.svelte';
	import { createProgram } from '$lib/features/admin/programs/service';
	import { programCreateSchema } from '$lib/features/admin/programs/schema';
	import type { Program } from '$lib/shared/types';
	import { Routes, adminProgram } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Program Management list (wireframe 4.5a): search + status filter over
	// GET /admin/programs. Aggregates (Years/Terms/Courses) are derived
	// per-request server-side and rendered as-is. The list endpoint takes no
	// sort params, so the Code/Name headers sort client-side over the loaded
	// page. Deactivate/Reactivate PATCHes is_active; Delete permanently
	// removes an archived program (DELETE /admin/programs/{id}, blocked with
	// 409 while offerings or students still reference it).

	// Keystrokes pause this long before a live-search request goes out.
	const SEARCH_DEBOUNCE_MS = 250;

	let search = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');

	let formOpen = $state(false);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);

	let deleteTarget = $state<Program | null>(null);
	let deleteBusy = $state(false);

	// Deactivate confirm (Deactivate flips to archived; Reactivate stays
	// immediate since it only restores).
	let deactivateTarget = $state<Program | null>(null);
	let deactivateBusy = $state(false);

	let f_code = $state('');
	let f_name = $state('');
	let f_description = $state('');
	let f_total_years = $state('');

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminProgramsState.total / adminProgramsState.size))
	);

	// Client-side sort over the loaded page (no server sort params exist).
	const sortedItems = $derived.by(() => {
		const items = [...adminProgramsState.items];
		const dir = adminProgramsState.sortDir === 'asc' ? 1 : -1;
		const key =
			adminProgramsState.sortBy === 'code'
				? (p: Program) => p.code
				: (p: Program) => p.name;
		items.sort((a, b) => key(a).localeCompare(key(b)) * dir);
		return items;
	});

	const load = (page = 1, term?: string) => {
		searchAbort?.abort();
		searchAbort = new AbortController();
		return initAdminPrograms(
			{
				search: (term ?? search.trim()) || undefined,
				is_active: isActiveFilter,
			},
			page,
			adminProgramsState.size,
			{ signal: searchAbort.signal }
		);
	};

	let searchAbort: AbortController | null = null;
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		searchAbort?.abort();
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!adminProgramsState.loading) void refreshAdminPrograms();
	};

	// No fetch-on-mount here: the live-search effect below fires on mount.
	// Subscriptions still mount once — own-entity events and tab-focus
	// refresh the visible page (stored filters/page preserved).
	onMount(() => {
		autoRefreshStops.push(
			subscribeEntity('programs', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	// Live search: refetch as the user types, debounced so a burst of keystrokes
	// only costs one request. The effect body reads `search` (that is what makes
	// it re-run) and `isActiveFilter` is read inside the timeout, so switching the
	// status filter does not double up with applyFilters.
	$effect(() => {
		const term = search.trim();
		const timer = setTimeout(() => load(1, term), SEARCH_DEBOUNCE_MS);
		return () => clearTimeout(timer);
	});

	const applyFilters = () => {
		load(1);
	};

	const toggleSort = (column: ProgramSortColumn) => {
		if (adminProgramsState.sortBy === column) {
			adminProgramsState.sortDir =
				adminProgramsState.sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			adminProgramsState.sortBy = column;
			adminProgramsState.sortDir = 'asc';
		}
	};

	const sortArrow = (column: ProgramSortColumn) =>
		adminProgramsState.sortBy === column
			? adminProgramsState.sortDir === 'asc'
				? ' ▲'
				: ' ▼'
			: '';

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte). Sort lives on the shared store here.
	const sortLabel = (column: ProgramSortColumn, label: string): string => {
		if (adminProgramsState.sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${adminProgramsState.sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: ProgramSortColumn): 'ascending' | 'descending' | 'none' =>
		adminProgramsState.sortBy === column
			? adminProgramsState.sortDir === 'asc'
				? 'ascending'
				: 'descending'
			: 'none';

	const openCreate = () => {
		formError = null;
		f_code = '';
		f_name = '';
		f_description = '';
		f_total_years = '';
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			const parsed = programCreateSchema.safeParse({
				code: f_code,
				name: f_name,
				description: f_description || undefined,
				total_years: f_total_years,
			});
			if (!parsed.success) {
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await createProgram({
				code: parsed.data.code,
				name: parsed.data.name,
				description: parsed.data.description || undefined,
				total_years: parsed.data.total_years,
			});
			formOpen = false;
			await refreshAdminPrograms();
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedProgram(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const closeDelete = () => {
		adminProgramsState.actionError = null;
		deleteTarget = null;
	};

	const confirmDeactivate = async () => {
		if (!deactivateTarget || deactivateBusy) return;
		deactivateBusy = true;
		try {
			await toggleProgramActive(deactivateTarget);
			deactivateTarget = null;
		} finally {
			deactivateBusy = false;
		}
	};

	const closeDeactivate = () => {
		adminProgramsState.actionError = null;
		deactivateTarget = null;
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Program Management</h1>
			<p class="muted">Programs own year levels; courses attach via offerings · {adminProgramsState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_PROGRAMS_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
			<button class="btn btn-primary" data-testid="add-program" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add Program
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search code or name…"
			aria-label="Search programs"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<select class="input" aria-label="Status filter" bind:value={statusFilter} onchange={applyFilters}>
			<option value="all">All statuses</option>
			<option value="active">Active</option>
			<option value="inactive">Inactive</option>
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminProgramsState.loading && adminProgramsState.items.length === 0}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminProgramsState.error}
		<section class="card"><p class="error">Could not load programs: {adminProgramsState.error}</p></section>
	{:else if sortedItems.length === 0}
		<section class="card">
			<p class="empty">No programs yet. Add the first one — year levels and terms come next on its detail page.</p>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminProgramsState.loading}>
			{#if adminProgramsState.actionError && !deleteTarget && !deactivateTarget}
				<p class="error" role="alert">{adminProgramsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col" aria-sort={ariaSort('code')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('code')} aria-label={sortLabel('code', 'Code')}>
								Code<span aria-hidden="true">{sortArrow('code')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('name')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('name')} aria-label={sortLabel('name', 'Name')}>
								Name<span aria-hidden="true">{sortArrow('name')}</span>
							</button>
						</th>
						<th>Years</th>
						<th>Terms</th>
						<th>Courses</th>
						<th>Status</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each sortedItems as p (p.id)}
						<tr>
							<td><button class="link strong" onclick={() => goto(adminProgram(p.id))}>{p.code}</button></td>
							<td>{p.name}</td>
							<td>{p.yearLevelCount}</td>
							<td>{p.termsCount}</td>
							<td>{p.courseCount}</td>
							<td>
								<span class="badge" class:inactive={!p.isActive}>
									{p.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="row-actions">
								<button class="link" onclick={() => goto(adminProgram(p.id))}>Open</button>
								{#if p.isActive}
									<button
										class="link"
										onclick={() => { adminProgramsState.actionError = null; deactivateTarget = p; }}
									>
										Deactivate
									</button>
								{:else}
									<button
										class="link"
										onclick={() => void toggleProgramActive(p)}
									>
										Reactivate
									</button>
								{/if}
								{#if !p.isActive}
									<button
										class="link danger"
										onclick={() => { adminProgramsState.actionError = null; deleteTarget = p; }}
									>
										Delete
									</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminProgramsState.page <= 1}
					onclick={() => load(adminProgramsState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminProgramsState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminProgramsState.page >= totalPages}
					onclick={() => load(adminProgramsState.page + 1)}
				>
					Next ›
				</button>
			</div>
		</section>
	{/if}
</div>

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="program-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formBusy ? undefined : (formOpen = false)) }}
		>
			<h2 id="program-form-title" class="modal-title">Add program</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Code<input class="input" bind:value={f_code} placeholder="BSCS" /></label>
					<label>Total years<input class="input" inputmode="numeric" bind:value={f_total_years} placeholder="4" /></label>
				</div>
				<label>Name<input class="input" bind:value={f_name} placeholder="BS Computer Science" /></label>
				<label>Description (optional)<input class="input" bind:value={f_description} /></label>
				<p class="hint">Year levels and term structures are added next, on the program detail page.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-program" disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="deactivate-program-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDeactivate }}
		>
			<h2 id="deactivate-program-title" class="modal-title">Deactivate {deactivateTarget.code}?</h2>
			<p class="modal-text">
				{deactivateTarget.name} will be flipped to archived. Year levels stay,
				offerings and students keep working, and you can reactivate it anytime.
			</p>
			{#if adminProgramsState.actionError}
				<p class="error" role="alert">{adminProgramsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={closeDeactivate}>Cancel</button>
				<button class="btn btn-danger" disabled={deactivateBusy} onclick={confirmDeactivate}>
					{deactivateBusy ? 'Deactivating…' : 'Deactivate'}
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
			aria-labelledby="delete-program-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDelete }}
		>
			<h2 id="delete-program-title" class="modal-title">Permanently delete {deleteTarget.code}?</h2>
			<p class="modal-text">
				{deleteTarget.name} will be removed for good, along with its year levels.
				If course offerings or students still use it, deletion will be blocked
				and the program stays archived.
			</p>
			{#if adminProgramsState.actionError}
				<p class="error" role="alert">{adminProgramsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={closeDelete}>Cancel</button>
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

	.header-actions {
		display: flex;
		gap: 0.75rem;
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
		vertical-align: middle;
	}

	th {
		color: var(--text-muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	/* Status pill in the Active/Inactive column. */
	.badge {
		display: inline-block;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.inactive {
		color: var(--text-muted);
		background: var(--divider);
	}

	.th-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		color: inherit;
		cursor: pointer;
		white-space: nowrap;
	}

	.th-btn:hover {
		color: var(--text-strong);
	}

	.th-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: 4px;
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

	.link.strong {
		font-size: 0.875rem;
		font-weight: 700;
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

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.btn-ghost {
		background: var(--divider);
		border: 1px solid transparent;
		color: var(--text-secondary);
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
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: var(--bg-card);
		border-radius: 12px;
		box-shadow: var(--shadow-lg);
		padding: 1.75rem 1.5rem;
		font-family: system-ui, sans-serif;
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

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
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

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
