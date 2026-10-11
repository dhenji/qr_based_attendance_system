<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminCoursesState,
		initAdminCourses,
		refreshAdminCourses,
		toggleCourseActive,
		type CourseSortColumn,
	} from '$lib/features/admin/courses/store.svelte';
	import {
		createCourse,
		updateCourse,
	} from '$lib/features/admin/courses/service';
	import {
		courseCreateSchema,
		courseUpdateSchema,
	} from '$lib/features/admin/courses/schema';
	import type { AdminCourse } from '$lib/shared/types';
	import { adminCourse } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Course template list: standalone reusable templates (D44) — no program,
	// scheduling, or classroom columns (those live on offerings). The list
	// endpoint takes no search/sort params, so the search box and Code/Name
	// header toggles filter/sort client-side over the loaded page while the
	// status filter goes to the server (?is_active). Deactivate/Reactivate
	// PATCHes is_active; archiving (DELETE, same soft effect) lives on the
	// course detail page.

	let search = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');

	let formOpen = $state(false);
	let editing = $state<AdminCourse | null>(null);
	let formError = $state<string | null>(null);
	let formBusy = $state(false);

	let f_code = $state('');
	let f_name = $state('');
	let f_units = $state('');
	let f_duration = $state('');

	const isActiveFilter = $derived(
		statusFilter === 'all' ? undefined : statusFilter === 'active'
	);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminCoursesState.total / adminCoursesState.size))
	);

	// Client-side search + sort over the loaded page (no server params exist).
	const visibleItems = $derived.by(() => {
		const term = search.trim().toLowerCase();
		let items = term
			? adminCoursesState.items.filter((c) =>
					`${c.courseCode} ${c.courseName}`.toLowerCase().includes(term)
				)
			: [...adminCoursesState.items];
		const dir = adminCoursesState.sortDir === 'asc' ? 1 : -1;
		const key =
			adminCoursesState.sortBy === 'code'
				? (c: AdminCourse) => c.courseCode
				: (c: AdminCourse) => c.courseName;
		items.sort((a, b) => key(a).localeCompare(key(b)) * dir);
		return items;
	});

	const load = (page = 1) =>
		initAdminCourses({ is_active: isActiveFilter }, page, adminCoursesState.size);

	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!adminCoursesState.loading) void refreshAdminCourses();
	};

	onMount(() => {
		load(1);
		autoRefreshStops.push(
			subscribeEntity('courses', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	const applyFilters = () => {
		load(1);
	};

	const toggleSort = (column: CourseSortColumn) => {
		if (adminCoursesState.sortBy === column) {
			adminCoursesState.sortDir =
				adminCoursesState.sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			adminCoursesState.sortBy = column;
			adminCoursesState.sortDir = 'asc';
		}
	};

	const sortArrow = (column: CourseSortColumn) =>
		adminCoursesState.sortBy === column
			? adminCoursesState.sortDir === 'asc'
				? ' ▲'
				: ' ▼'
			: '';

	// Sort state for assistive tech, mirroring the professor ledger pattern
	// (professor/attendance/+page.svelte). Sort lives on the shared store here.
	const sortLabel = (column: CourseSortColumn, label: string): string => {
		if (adminCoursesState.sortBy !== column) return `Sort by ${label.toLowerCase()} ascending`;
		return `Sort by ${label.toLowerCase()} ${adminCoursesState.sortDir === 'asc' ? 'descending' : 'ascending'}`;
	};

	const ariaSort = (column: CourseSortColumn): 'ascending' | 'descending' | 'none' =>
		adminCoursesState.sortBy === column
			? adminCoursesState.sortDir === 'asc'
				? 'ascending'
				: 'descending'
			: 'none';

	const openCreate = () => {
		editing = null;
		formError = null;
		f_code = '';
		f_name = '';
		f_units = '';
		f_duration = '';
		formOpen = true;
	};

	const openEdit = (c: AdminCourse) => {
		editing = c;
		formError = null;
		f_code = c.courseCode;
		f_name = c.courseName;
		f_units = String(c.units);
		f_duration = String(c.sessionDurationHours);
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		formBusy = true;
		try {
			if (editing) {
				const parsed = courseUpdateSchema.safeParse({
					course_code: f_code,
					course_name: f_name,
					units: f_units,
					session_duration_hours: f_duration,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				await updateCourse(editing.id, {
					course_code: parsed.data.course_code,
					course_name: parsed.data.course_name,
					units: parsed.data.units,
					session_duration_hours: parsed.data.session_duration_hours,
				});
			} else {
				const parsed = courseCreateSchema.safeParse({
					course_code: f_code,
					course_name: f_name,
					units: f_units,
					session_duration_hours: f_duration,
				});
				if (!parsed.success) {
					formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
					return;
				}
				await createCourse({
					course_code: parsed.data.course_code,
					course_name: parsed.data.course_name,
					units: parsed.data.units,
					session_duration_hours: parsed.data.session_duration_hours,
				});
			}
			formOpen = false;
			await refreshAdminCourses();
			notifyEntityChanged('courses');
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
			<h1>Course Management</h1>
			<p class="muted">Reusable templates — scheduling lives on offerings · {adminCoursesState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-primary" data-testid="add-course" onclick={openCreate}>
				<AppIcon name="plus" size={18} />
				Add Course
			</button>
		</div>
	</header>

	<section class="card filters">
		<input
			class="input search"
			type="search"
			placeholder="Search code or name…"
			aria-label="Search courses"
			bind:value={search}
		/>
		<select class="input" aria-label="Status filter" bind:value={statusFilter} onchange={applyFilters}>
			<option value="all">All statuses</option>
			<option value="active">Active</option>
			<option value="inactive">Inactive</option>
		</select>
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminCoursesState.loading && adminCoursesState.items.length === 0}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminCoursesState.error}
		<section class="card"><p class="error">Could not load courses: {adminCoursesState.error}</p></section>
	{:else if visibleItems.length === 0}
		<section class="card">
			<p class="empty">No courses yet. Add the first template — offerings attach it to a program and year.</p>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminCoursesState.loading}>
			{#if adminCoursesState.actionError}
				<p class="error" role="alert">{adminCoursesState.actionError}</p>
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
						<th>Units</th>
						<th>Duration (h)</th>
						<th>Status</th>
						<th><span class="sr">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					{#each visibleItems as c (c.id)}
						<tr>
							<td><button class="link strong" onclick={() => goto(adminCourse(c.id))}>{c.courseCode}</button></td>
							<td>{c.courseName}</td>
							<td>{c.units}</td>
							<td>{c.sessionDurationHours}</td>
							<td>
								<span class="badge" class:inactive={!c.isActive}>
									{c.isActive ? 'Active' : 'Inactive'}
								</span>
							</td>
							<td class="row-actions">
								<button class="link" onclick={() => goto(adminCourse(c.id))}>Open</button>
								<button class="link" onclick={() => openEdit(c)}>Edit</button>
								<button
									class="link"
									onclick={() => void toggleCourseActive(c)}
								>
									{c.isActive ? 'Deactivate' : 'Reactivate'}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="pager">
				<button
					class="btn btn-secondary"
					disabled={adminCoursesState.page <= 1}
					onclick={() => load(adminCoursesState.page - 1)}
				>
					‹ Prev
				</button>
				<span class="muted">Page {adminCoursesState.page} of {totalPages}</span>
				<button
					class="btn btn-secondary"
					disabled={adminCoursesState.page >= totalPages}
					onclick={() => load(adminCoursesState.page + 1)}
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
			aria-labelledby="course-form-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (formOpen = false) }}
		>
			<h2 id="course-form-title" class="modal-title">{editing ? 'Edit course' : 'Add course'}</h2>
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Code<input class="input" bind:value={f_code} placeholder="CS101" /></label>
					<label>Units (1–6)<input class="input" inputmode="numeric" bind:value={f_units} placeholder="3" /></label>
				</div>
				<label>Name<input class="input" bind:value={f_name} placeholder="Software Engineering 1" /></label>
				<label>Session duration, hours (0.5–8)<input class="input" inputmode="decimal" bind:value={f_duration} placeholder="1.5" /></label>
				<p class="hint">Program, schedule, and classroom attach later via offerings.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-course" disabled={formBusy} onclick={submitForm}>
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
