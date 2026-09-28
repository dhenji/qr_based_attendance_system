<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminStudentsState,
		deleteArchivedStudent,
		initAdminStudents,
		refreshAdminStudents,
		toggleStudentActive,
	} from '$lib/features/admin/store.svelte';
	import {
		createStudent,
		updateStudent,
	} from '$lib/features/admin/service';
	import {
		adminStudentCreateSchema,
		adminStudentUpdateSchema,
	} from '$lib/features/admin/schema';
	import type { AdminStudent } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';

	// Student Management (wireframe 4.2): search + status filter + sortable
	// table + pagination over GET /admin/students. Deactivate flips
	// is_active (soft); permanent delete is only offered on archived rows and
	// goes to DELETE /{id}/archive with its 409 has-records guard.

	let search = $state('');
	let statusFilter = $state<'all' | 'active' | 'archived'>('all');
	let sortBy = $state<'last_name' | 'student_id' | 'created_at'>('last_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let formOpen = $state(false);
	let editing = $state<AdminStudent | null>(null);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);
	let deleteTarget = $state<AdminStudent | null>(null);
	let deleteBusy = $state(false);

	// Form fields (strings for inputs; ids coerced by zod on submit).
	let f_student_id = $state('');
	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');
	let f_email = $state('');
	let f_program_id = $state('');
	let f_year_level_id = $state('');
	let f_section = $state('');
	let f_username = $state('');

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminStudentsState.total / adminStudentsState.size))
	);

	const load = (page = 1) =>
		initAdminStudents(
			{
				search: search.trim() || undefined,
				is_active: isActiveFilter,
				sort_by: sortBy,
				sort_dir: sortDir,
			},
			page,
			adminStudentsState.size
		);

	onMount(() => {
		load(1);
	});

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
		load(adminStudentsState.page);
	};

	const sortArrow = (column: typeof sortBy) =>
		sortBy === column ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

	const fullName = (s: AdminStudent) =>
		[s.firstName, s.middleName, s.lastName].filter(Boolean).join(' ');

	const openCreate = () => {
		editing = null;
		formError = null;
		f_student_id = '';
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		f_email = '';
		f_program_id = '';
		f_year_level_id = '';
		f_section = '';
		f_username = '';
		formOpen = true;
	};

	const openEdit = (s: AdminStudent) => {
		editing = s;
		formError = null;
		f_student_id = s.studentId;
		f_first_name = s.firstName;
		f_middle_name = s.middleName ?? '';
		f_last_name = s.lastName;
		f_email = s.email;
		f_program_id = '';
		f_year_level_id = '';
		f_section = s.section ?? '';
		f_username = '';
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			if (editing === null) {
				const parsed = adminStudentCreateSchema.safeParse({
					student_id: f_student_id,
					first_name: f_first_name,
					middle_name: f_middle_name || undefined,
					last_name: f_last_name,
					email: f_email,
					program_id: f_program_id,
					year_level_id: f_year_level_id,
					section: f_section || undefined,
					username: f_username || undefined,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				const d = parsed.data;
				await createStudent({
					student_id: d.student_id,
					first_name: d.first_name,
					middle_name: d.middle_name || undefined,
					last_name: d.last_name,
					email: d.email,
					program_id: d.program_id,
					year_level_id: d.year_level_id,
					section: d.section || undefined,
					username: d.username || undefined,
				});
			} else {
				const parsed = adminStudentUpdateSchema.safeParse({
					first_name: f_first_name || undefined,
					last_name: f_last_name || undefined,
					email: f_email || undefined,
					program_id: f_program_id || undefined,
					year_level_id: f_year_level_id || undefined,
					section: f_section || undefined,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				const d = parsed.data;
				await updateStudent(editing.id, {
					first_name: d.first_name,
					last_name: d.last_name,
					email: d.email,
					program_id: d.program_id,
					year_level_id: d.year_level_id,
					section: d.section,
				});
			}
			formOpen = false;
			await refreshAdminStudents();
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
			await deleteArchivedStudent(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Student Management</h1>
			<p class="muted">Roster records students claim at registration · {adminStudentsState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_STUDENTS_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
			<button class="btn btn-primary" data-testid="add-student" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search ID, name, email…"
			aria-label="Search students"
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

	{#if adminStudentsState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminStudentsState.error}
		<section class="card"><p class="error">Could not load students: {adminStudentsState.error}</p></section>
	{:else if adminStudentsState.items.length === 0}
		<section class="card">
			<p class="empty">No students match these filters. Import a roster or add one manually.</p>
		</section>
	{:else}
		<section class="card table-wrap">
			{#if adminStudentsState.actionError}
				<p class="error" role="alert">{adminStudentsState.actionError}</p>
			{/if}
			<table>
				<thead>
					<tr>
						<th><button class="th-btn" onclick={() => toggleSort('student_id')}>ID{sortArrow('student_id')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('last_name')}>Name{sortArrow('last_name')}</button></th>
						<th>Program</th>
						<th>Sec</th>
						<th>Year</th>
						<th>Status</th>
						<th>Face</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each adminStudentsState.items as s (s.id)}
						<tr>
							<td class="mono">{s.studentId}</td>
							<td>{fullName(s)}</td>
							<td>{s.programCode}</td>
							<td>{s.section ?? '—'}</td>
							<td>{s.yearLevelLabel}</td>
							<td>{s.isActive ? '✅' : '🚫'}</td>
							<td>{s.faceEnrolled ? '✅' : '—'}</td>
							<td class="row-actions">
								<button class="link" onclick={() => openEdit(s)}>Edit</button>
								<button
									class="link"
									onclick={() => toggleStudentActive(s).catch(() => {})}
								>
									{s.isActive ? 'Deactivate' : 'Reactivate'}
								</button>
								{#if !s.isActive}
									<button class="link danger" onclick={() => (deleteTarget = s)}>Delete</button>
								{/if}
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

{#if formOpen}
	<div class="modal-overlay" role="presentation">
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="student-form-title">
			<h2 id="student-form-title" class="modal-title">{editing ? 'Edit student' : 'Add student'}</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				{#if !editing}
					<label>Student ID<input class="input" bind:value={f_student_id} placeholder="2021-01234" /></label>
				{/if}
				<div class="grid2">
					<label>First name<input class="input" bind:value={f_first_name} /></label>
					<label>Middle name<input class="input" bind:value={f_middle_name} /></label>
				</div>
				<div class="grid2">
					<label>Last name<input class="input" bind:value={f_last_name} /></label>
					<label>Email<input class="input" type="email" bind:value={f_email} /></label>
				</div>
				{#if !editing}
					<div class="grid2">
						<label>Program ID<input class="input" inputmode="numeric" bind:value={f_program_id} placeholder="1" /></label>
						<label>Year level ID<input class="input" inputmode="numeric" bind:value={f_year_level_id} placeholder="1" /></label>
					</div>
					<div class="grid2">
						<label>Section<input class="input" bind:value={f_section} placeholder="A" /></label>
						<label>Username (claim slot)<input class="input" bind:value={f_username} placeholder="optional" /></label>
					</div>
					<p class="hint">Program and year-level IDs come from the Programs tables (Phase 3 next adds a picker).</p>
				{:else}
					<div class="grid2">
						<label>Program ID<input class="input" inputmode="numeric" bind:value={f_program_id} placeholder="unchanged" /></label>
						<label>Year level ID<input class="input" inputmode="numeric" bind:value={f_year_level_id} placeholder="unchanged" /></label>
					</div>
					<label>Section<input class="input" bind:value={f_section} /></label>
				{/if}
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-student" disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteTarget}
	<div class="modal-overlay" role="presentation">
		<div class="modal" role="dialog" aria-modal="true" aria-labelledby="delete-title">
			<h2 id="delete-title" class="modal-title">Permanently delete?</h2>
			<p class="modal-text">
				{fullName(deleteTarget)} ({deleteTarget.studentId}) is archived. This cannot be undone,
				and it fails with 409 if enrollments, scans, or excuse requests still reference them.
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

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		white-space: nowrap;
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

	.btn-danger {
		background: #dc2626;
		border: 1px solid #dc2626;
		color: white;
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

	.modal-text {
		margin: 0 0 1.5rem;
		font-size: 0.9375rem;
		color: #475569;
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
