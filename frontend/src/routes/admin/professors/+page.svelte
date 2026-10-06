<script lang="ts">
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TempPasswordModal from '$lib/components/TempPasswordModal.svelte';
	import {
		adminProfessorsState,
		deleteArchivedProfessor,
		initAdminProfessors,
		refreshAdminProfessors,
		toggleProfessorActive,
	} from '$lib/features/admin/store.svelte';
	import {
		createProfessor,
		listOfferings,
		offeringLabel,
		resetProfessorPassword,
		updateProfessor,
	} from '$lib/features/admin/service';
	import {
		adminProfessorCreateSchema,
		adminProfessorUpdateSchema,
	} from '$lib/features/admin/schema';
	import type { AdminOffering, AdminProfessor } from '$lib/shared/types';
	import { goto } from '$app/navigation';
	import { adminProfessor, Routes } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Professor Management (wireframe 4.4): same CRUD pattern as students, but
	// the roster seeds the records professors claim at registration. Columns:
	// Name, Email, Department, Courses, Claim, Status.

	let search = $state('');
	let department = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');
	let sortBy = $state<'last_name' | 'email' | 'created_at'>('last_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let formOpen = $state(false);
	let editing = $state<AdminProfessor | null>(null);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);
	let deleteTarget = $state<AdminProfessor | null>(null);
	let deleteBusy = $state(false);
	// Credential reset; see the students page for why the modal is shared.
	let resetTarget = $state<AdminProfessor | null>(null);

	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');
	let f_email = $state('');
	let f_department = $state('');
	let f_username = $state('');
	let f_courses = $state<number[]>([]);
	let offeringOptions = $state<AdminOffering[]>([]);
	let offeringsLoading = $state(false);
	let offeringsError = $state<string | null>(null);

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminProfessorsState.total / adminProfessorsState.size))
	);

	const load = (page = 1) =>
		initAdminProfessors(
			{
				search: search.trim() || undefined,
				department: department.trim() || undefined,
				is_active: isActiveFilter,
				sort_by: sortBy,
				sort_dir: sortDir,
			},
			page,
			adminProfessorsState.size
		);

	const loadOfferings = async () => {
		offeringsLoading = true;
		offeringsError = null;
		try {
			const result = await listOfferings({ is_active: true, page: 1, size: 50 });
			offeringOptions = result.items;
		} catch (e: unknown) {
			offeringsError = e instanceof Error && e.message ? e.message : 'Could not load offerings';
		} finally {
			offeringsLoading = false;
		}
	};

	onMount(() => {
		load(1);
		loadOfferings();
	});

	const toggleCourse = (id: number) => {
		f_courses = f_courses.includes(id)
			? f_courses.filter((v) => v !== id)
			: [...f_courses, id];
	};

	const applyFilters = () => {
		load(1);
	};

	const toggleSort = (column: typeof sortBy) => {
		if (sortBy === column) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortDir = 'asc';
		}
		load(adminProfessorsState.page);
	};

	const sortArrow = (column: typeof sortBy) =>
		sortBy === column ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte).
	const sortLabel = (column: typeof sortBy, label: string): string => {
		if (sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: typeof sortBy): 'ascending' | 'descending' | 'none' =>
		sortBy === column ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none';

	const fullName = (p: AdminProfessor) =>
		[p.firstName, p.middleName, p.lastName].filter(Boolean).join(' ');

	const openCreate = () => {
		editing = null;
		formError = null;
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		f_email = '';
		f_department = '';
		f_username = '';
		f_courses = [];
		if (offeringOptions.length === 0) loadOfferings();
		formOpen = true;
	};

	const openEdit = (p: AdminProfessor) => {
		editing = p;
		formError = null;
		f_first_name = p.firstName;
		f_middle_name = p.middleName ?? '';
		f_last_name = p.lastName;
		f_email = p.email;
		f_department = p.department ?? '';
		f_username = '';
		f_courses = (p.assigned_courses ?? []).map((c) => c.offering_id);
		if (offeringOptions.length === 0) loadOfferings();
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			if (editing === null) {
				const parsed = adminProfessorCreateSchema.safeParse({
					first_name: f_first_name,
					middle_name: f_middle_name || undefined,
					last_name: f_last_name,
					email: f_email,
					department: f_department || undefined,
					username: f_username || undefined,
					courses: f_courses,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				const d = parsed.data;
				await createProfessor({
					first_name: d.first_name,
					middle_name: d.middle_name || undefined,
					last_name: d.last_name,
					email: d.email,
					department: d.department || undefined,
					username: d.username || undefined,
					courses: d.courses.length > 0 ? d.courses : undefined,
				});
			} else {
				const parsed = adminProfessorUpdateSchema.safeParse({
					first_name: f_first_name || undefined,
					last_name: f_last_name || undefined,
					email: f_email || undefined,
					department: f_department || undefined,
					courses: f_courses,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				const d = parsed.data;
				await updateProfessor(editing.id, {
					first_name: d.first_name,
					last_name: d.last_name,
					email: d.email,
					department: d.department,
					courses: d.courses,
				});
			}
			formOpen = false;
			await refreshAdminProfessors();
		} catch (e: unknown) {
			formError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			formBusy = false;
		}
	};

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
			<h1>Professor Management</h1>
			<p class="muted">Seeded records professors claim at registration · {adminProfessorsState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_PROFESSORS_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
			<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_PROFESSORS_ARCHIVE)}>
				Archive
			</button>
			<button class="btn btn-primary" data-testid="add-professor" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search name, email…"
			aria-label="Search professors"
			bind:value={search}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<input
			class="input"
			type="text"
			placeholder="Department"
			aria-label="Department filter"
			bind:value={department}
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

	{#if adminProfessorsState.loading && adminProfessorsState.items.length === 0}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminProfessorsState.error}
		<section class="card"><p class="error">Could not load professors: {adminProfessorsState.error}</p></section>
	{:else if adminProfessorsState.items.length === 0}
		<section class="card">
			<p class="empty">No professors match these filters. Add the first record to seed the roster.</p>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminProfessorsState.loading}>
			{#if adminProfessorsState.actionError}
				<p class="error" role="alert">{adminProfessorsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th scope="col" aria-sort={ariaSort('last_name')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('last_name')} aria-label={sortLabel('last_name', 'Name')}>
								Name<span aria-hidden="true">{sortArrow('last_name')}</span>
							</button>
						</th>
						<th scope="col" aria-sort={ariaSort('email')}>
							<button class="th-btn" type="button" onclick={() => toggleSort('email')} aria-label={sortLabel('email', 'Email')}>
								Email<span aria-hidden="true">{sortArrow('email')}</span>
							</button>
						</th>
						<th>Department</th>
						<th>Courses</th>
						<th>Claim</th>
						<th>Status</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminProfessorsState.items as p (p.id)}
						<tr>
							<td>{fullName(p)}</td>
							<td>
								<button
									class="link mono"
									data-testid={`professor-email-${p.id}`}
									aria-label={`View ${fullName(p)} profile`}
									onclick={() => goto(adminProfessor(p.id))}
								>
									{p.email}
								</button>
							</td>
							<td>{p.department ?? '—'}</td>
							<td>{p.assigned_courses.length}</td>
							<td>{p.claimStatus}</td>
							<td>
								<span class={p.isActive ? 'status-active' : 'status-inactive'}>
									{p.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="row-actions">
								<button class="link" onclick={() => openEdit(p)}>Edit</button>
								<button
									class="link"
									onclick={() => toggleProfessorActive(p).catch(() => {})}
								>
									{p.isActive ? 'Deactivate' : 'Reactivate'}
								</button>
{#if !p.isActive}
								<button class="link danger" onclick={() => (deleteTarget = p)}>Delete</button>
							{/if}
							<button class="link" onclick={() => (resetTarget = p)}>Reset password</button>
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

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="professor-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formOpen = false) }}
		>
			<h2 id="professor-form-title" class="modal-title">{editing ? 'Edit professor' : 'Add professor'}</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>First name<input class="input" bind:value={f_first_name} /></label>
					<label>Middle name<input class="input" bind:value={f_middle_name} /></label>
				</div>
				<div class="grid2">
					<label>Last name<input class="input" bind:value={f_last_name} /></label>
					<label>Email<input class="input" type="email" bind:value={f_email} /></label>
				</div>
				<div class="grid2">
					<label>Department<input class="input" bind:value={f_department} placeholder="Computer Science" /></label>
					{#if !editing}
						<label>Username (claim slot)<input class="input" bind:value={f_username} placeholder="optional" /></label>
					{/if}
				</div>
				<fieldset class="courses">
					<legend>Course assignments (offerings)</legend>
					{#if offeringsLoading}
						<p class="hint">Loading offerings…</p>
					{:else if offeringsError}
						<p class="error" role="alert">{offeringsError}</p>
					{:else if offeringOptions.length === 0}
						<p class="hint">No active offerings found.</p>
					{:else}
						{#each offeringOptions as o (o.id)}
							<label class="check">
								<input
									type="checkbox"
									checked={f_courses.includes(o.id)}
									onchange={() => toggleCourse(o.id)}
								/>
								<span>{offeringLabel(o)}</span>
							</label>
						{/each}
					{/if}
				</fieldset>
				<p class="hint">Assignments are saved with the professor (replaces the set on edit); no user row is created until the professor self-registers.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-professor" disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
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
				{fullName(deleteTarget)} is inactive. This cannot be undone, and it fails
				with 409 if sessions still reference them.
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

{#if resetTarget}
	<TempPasswordModal
		subject={fullName(resetTarget) || resetTarget.email}
		subjectKind="professor"
		onconfirm={() => resetProfessorPassword(resetTarget!.id)}
		onclose={() => (resetTarget = null)}
	/>
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

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 500;
	}

	.status-active,
	.status-inactive {
		display: inline-block;
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
	}

	.status-active {
		background: var(--success-bg);
		color: var(--success);
	}

	.status-inactive {
		background: var(--danger-bg);
		color: var(--danger);
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

	.courses {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.75rem 0.875rem;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.courses legend {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		padding: 0 0.375rem;
	}

	.courses .check {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
		font-weight: 500;
		cursor: pointer;
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
