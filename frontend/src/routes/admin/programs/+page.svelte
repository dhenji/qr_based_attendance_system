<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminProgramsState,
		archiveProgramRow,
		initAdminPrograms,
		refreshAdminPrograms,
		toggleProgramActive,
		type ProgramSortColumn,
	} from '$lib/features/admin/programs/store.svelte';
	import { createProgram } from '$lib/features/admin/programs/service';
	import { programCreateSchema } from '$lib/features/admin/programs/schema';
	import type { Program } from '$lib/shared/types';
	import { Routes, adminProgram } from '$lib/shared/constants/routes';

	// Program Management list (wireframe 4.5a): search + status filter over
	// GET /admin/programs. Aggregates (Years/Terms/Courses) are derived
	// per-request server-side and rendered as-is. The list endpoint takes no
	// sort params, so the Code/Name headers sort client-side over the loaded
	// page. Archive flips is_active only — no cascade (ADR-058).

	let search = $state('');
	let statusFilter = $state<'all' | 'active' | 'archived'>('all');

	let formOpen = $state(false);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);

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

	const load = (page = 1) =>
		initAdminPrograms(
			{
				search: search.trim() || undefined,
				is_active: isActiveFilter,
			},
			page,
			adminProgramsState.size
		);

	onMount(() => {
		load(1);
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
		} catch (e: unknown) {
			formError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			formBusy = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Program Management</h1>
			<p class="muted">Programs own year levels; courses attach via offerings · {adminProgramsState.total} total</p>
		</div>
		<div class="header-actions">
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
			<option value="archived">Archived</option>
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminProgramsState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminProgramsState.error}
		<section class="card"><p class="error">Could not load programs: {adminProgramsState.error}</p></section>
	{:else if sortedItems.length === 0}
		<section class="card">
			<p class="empty">No programs yet. Add the first one — year levels and terms come next on its detail page.</p>
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminProgramsState.actionError}
				<p class="error" role="alert">{adminProgramsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th><button class="th-btn" onclick={() => toggleSort('code')}>Code{sortArrow('code')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('name')}>Name{sortArrow('name')}</button></th>
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
							<td>{p.isActive ? '✅' : '🚫'}</td>
							<td class="row-actions">
								<button class="link" onclick={() => goto(adminProgram(p.id))}>Open</button>
								<button
									class="link"
									onclick={() => toggleProgramActive(p).catch(() => {})}
								>
									{p.isActive ? 'Deactivate' : 'Reactivate'}
								</button>
								{#if p.isActive}
									<button class="link danger" onclick={() => archiveProgramRow(p.id).catch(() => {})}>Archive</button>
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
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="program-form-title">
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
		color: #1e293b;
		margin: 0 0 0.25rem;
	}

	.muted {
		color: #64748b;
		font-size: 0.875rem;
		margin: 0;
	}

	.header-actions {
		display: flex;
		gap: 0.75rem;
	}

	.card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
	}

	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid #cbd5e1;
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: #0f172a;
		background: white;
	}

	.input:focus {
		outline: 2px solid #2563eb;
		outline-offset: 1px;
		border-color: #2563eb;
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
		border-bottom: 1px solid #f1f5f9;
		vertical-align: middle;
	}

	th {
		color: #64748b;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
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
		color: #0f172a;
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
		color: #2563eb;
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
	}

	.link:hover {
		text-decoration: underline;
	}

	.link.strong {
		font-size: 0.875rem;
		font-weight: 700;
	}

	.link.danger {
		color: #dc2626;
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
		color: #64748b;
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: #dc2626;
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
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: #1e3a5f;
		border: 1px solid #1e3a5f;
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: #16324f;
	}

	.btn-secondary {
		background: white;
		border: 1px solid #cbd5e1;
		color: #0f172a;
	}

	.btn-secondary:hover:not(:disabled) {
		background: #f1f5f9;
	}

	.btn-ghost {
		background: #f1f5f9;
		border: 1px solid transparent;
		color: #334155;
	}

	.modal-overlay {
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
		max-width: 520px;
		max-height: 90vh;
		overflow-y: auto;
		background: white;
		border-radius: 12px;
		box-shadow: 0 20px 40px rgba(15, 23, 42, 0.25);
		padding: 1.75rem 1.5rem;
		font-family: system-ui, sans-serif;
	}

	.modal-title {
		margin: 0 0 1rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: #1e293b;
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
		color: #334155;
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
	}

	.hint {
		font-size: 0.75rem;
		color: #94a3b8;
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
