<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
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
	import type { AdminStudent, Program, YearLevel } from '$lib/shared/types';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { Routes } from '$lib/shared/constants/routes';

	// Student Management (wireframe 4.2): search + status filter + sortable
	// table + pagination over GET /admin/students. Deactivate flips
	// is_active (soft); permanent delete is only offered on inactive rows and
	// goes to DELETE /{id}/archive with its 409 has-records guard.

	let search = $state('');
	let sectionFilter = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');
	let programFilter = $state('');
	// Year filter is label-based (1st-6th Year) so it works with AND without
	// a program picked: year_level_ids are per-program, so with no program
	// there is no single id to send and the label narrows the page locally.
	let yearLabel = $state('');
	const YEAR_LABELS = ['1st Year', '2nd Year', '3rd Year', '4th Year', '5th Year', '6th Year'];
	let programOptions = $state<Program[]>([]);
	let yearOptions = $state<YearLevel[]>([]);
	let sortBy = $state<
		'last_name' | 'student_id' | 'created_at' | 'program_code' | 'section' | 'year_level_label'
	>('last_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	// Columns the backend list endpoint cannot sort (its sort_by Literal only
	// covers last_name/student_id/created_at) are sorted client-side within the
	// loaded page instead of sending a value the API would reject with 422.
	// "Course" here is the Program column (students carry program_code, not a course).
	const CLIENT_SORTS = ['program_code', 'section', 'year_level_label'] as const;
	type ClientSort = (typeof CLIENT_SORTS)[number];
	const isClientSort = (column: typeof sortBy): column is ClientSort =>
		(CLIENT_SORTS as readonly string[]).includes(column);
	const CLIENT_SORT_KEY = {
		program_code: 'programCode',
		section: 'section',
		year_level_label: 'yearLevelLabel',
	} as const;

	// The year_level_id the server can scope to, if any: only when a program
	// is picked AND that program actually has a year with the chosen label.
	const yearIdForServer = $derived(
		programFilter && yearLabel
			? yearOptions.find((y) => y.label === yearLabel)?.id
			: undefined
	);

	// Rows as rendered: server order for backend sorts, local order for the
	// client-side columns above, plus the standalone year-label filter (used
	// whenever the label isn't server-scoped to one year_level_id — i.e. no
	// program picked, or the picked program has no such year).
	const visibleStudents = $derived.by(() => {
		let items = adminStudentsState.items;
		if (isClientSort(sortBy)) {
			const key = CLIENT_SORT_KEY[sortBy];
			const dir = sortDir === 'desc' ? -1 : 1;
			items = [...items].sort(
				(a, b) =>
					(String(a[key] ?? '').localeCompare(String(b[key] ?? '')) ||
						a.lastName.localeCompare(b.lastName) ||
						a.firstName.localeCompare(b.firstName)) * dir
			);
		}
		if (yearLabel && yearIdForServer === undefined) {
			items = items.filter((s) => s.yearLevelLabel === yearLabel);
		}
		return items;
	});

	// In label-only mode the server total covers unfiltered rows, so count
	// what's shown and keep the pager on the single local page.
	const clientYearFiltered = $derived(yearLabel !== '' && yearIdForServer === undefined);
	const displayTotal = $derived(
		clientYearFiltered ? visibleStudents.length : adminStudentsState.total
	);
	let searchTimer: ReturnType<typeof setTimeout> | null = null;

	onDestroy(() => {
		if (searchTimer) clearTimeout(searchTimer);
	});

	const onSearchInput = () => {
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => load(1), 300);
	};

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

	// Fixed page size: the admin store is shared with the dashboard (which
	// loads it with size=1 for KPI counts), so never inherit size from it —
	// that leak is what shrank this table to one row per page.
	const PAGE_SIZE = 10;

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(displayTotal / PAGE_SIZE))
	);

	const load = (page = 1) =>
		initAdminStudents(
			{
				search: search.trim() || undefined,
				section: sectionFilter.trim() || undefined,
				program_id: programFilter ? Number(programFilter) : undefined,
				year_level_id: yearIdForServer,
				is_active: isActiveFilter,
				// Client-side columns sort locally (see visibleStudents), so
				// leave the request unsorted rather than sending sort_by the
				// backend rejects.
				sort_by: isClientSort(sortBy) ? undefined : sortBy,
				sort_dir: isClientSort(sortBy) ? undefined : sortDir,
			},
			page,
			PAGE_SIZE
		);

	onMount(async () => {
		try {
			programOptions = (await listPrograms({ page: 1, size: 50 })).items;
		} catch {
			programOptions = [];
		}
		load(1);
	});

	const changeProgram = async () => {
		yearLabel = '';
		yearOptions = [];
		if (programFilter) {
			try {
				yearOptions = await listYearLevels(Number(programFilter));
			} catch {
				yearOptions = [];
			}
		}
		load(1);
	};

	const applyFilters = () => {
		if (searchTimer) {
			clearTimeout(searchTimer);
			searchTimer = null;
		}
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
		sortBy === column ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ↕';

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
				if ((f_program_id && !f_year_level_id) || (!f_program_id && f_year_level_id)) {
					formError = 'Enter both Program ID and Year level ID, or leave both unchanged.';
					return;
				}
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
		} catch {
			// deleteArchivedStudent already put the reason in actionError —
			// keep the modal open so it stays visible.
		} finally {
			deleteBusy = false;
		}
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Student Management</h1>
			<p class="muted">Roster records students claim at registration · {displayTotal} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_STUDENTS_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
			<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_STUDENTS_ARCHIVE)}>
				Archive
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
			oninput={onSearchInput}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<input
			class="input section"
			type="text"
			placeholder="Section (e.g. A)"
			aria-label="Section filter"
			bind:value={sectionFilter}
			oninput={onSearchInput}
			onkeydown={(e) => {
				if (e.key === 'Enter') applyFilters();
			}}
		/>
		<select class="input" aria-label="Status filter" bind:value={statusFilter} onchange={applyFilters}>
			<option value="all">All statuses</option>
			<option value="active">Active</option>
			<option value="inactive">Inactive</option>
		</select>
		<select class="input" aria-label="Program filter" bind:value={programFilter} onchange={changeProgram}>
			<option value="">All programs</option>
			{#each programOptions as p (p.id)}
				<option value={String(p.id)}>{p.code} — {p.name}</option>
			{/each}
		</select>
		<select class="input" aria-label="Year level filter" bind:value={yearLabel} onchange={applyFilters}>
			<option value="">All years</option>
			{#each YEAR_LABELS as label (label)}
				<option value={label}>{label}</option>
			{/each}
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminStudentsState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminStudentsState.error}
		<section class="card">
			<p class="error">Could not load students: {adminStudentsState.error}</p>
			<button class="btn btn-secondary" onclick={() => load(adminStudentsState.page)}>Retry</button>
		</section>
	{:else if visibleStudents.length === 0}
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
						<th><button class="th-btn" onclick={() => toggleSort('program_code')}>Program{sortArrow('program_code')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('section')}>Sec{sortArrow('section')}</button></th>
						<th><button class="th-btn" onclick={() => toggleSort('year_level_label')}>Year{sortArrow('year_level_label')}</button></th>
						<th>Status</th>
						<th>Face</th>
						<th><button class="th-btn" onclick={() => toggleSort('created_at')}>Added{sortArrow('created_at')}</button></th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each visibleStudents as s (s.id)}
						<tr>
							<td class="mono">{s.studentId}</td>
							<td>{fullName(s)}</td>
							<td>{s.programCode}</td>
							<td>{s.section ?? '—'}</td>
							<td>{s.yearLevelLabel}</td>
							<td><span class={s.isActive ? 'status-active' : 'status-inactive'}>{s.isActive ? 'Active' : 'Inactive'}</span></td>
							<td>{s.faceEnrolled ? 'Yes' : '—'}</td>
							<td class="mono">{new Date(s.createdAt).toLocaleDateString()}</td>
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
					disabled={adminStudentsState.loading || clientYearFiltered || adminStudentsState.page <= 1}
					onclick={() => load(Math.max(1, adminStudentsState.page - 1))}
				>
					‹ Prev
				</button>
				<span class="muted"
					>Page {Math.min(adminStudentsState.page, totalPages)} of {totalPages} · {displayTotal}
					total</span
				>
				<button
					class="btn btn-secondary"
					disabled={adminStudentsState.loading || clientYearFiltered || adminStudentsState.page >= totalPages}
					onclick={() => load(Math.min(totalPages, adminStudentsState.page + 1))}
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
					<label>Student ID<input class="input" bind:value={f_student_id} placeholder="ID number as printed on the student card" /></label>
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
				{fullName(deleteTarget)} ({deleteTarget.studentId}) is inactive. This cannot be undone,
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

	.section {
		flex: 0 1 140px;
		min-width: 120px;
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

	.mono {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		white-space: nowrap;
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
		background: var(--divider);
		color: var(--text-muted);
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
