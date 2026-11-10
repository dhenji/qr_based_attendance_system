<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminCoursesState,
		deleteArchivedCourse,
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
	import { adminCourse, Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { APIError } from '$lib/api/client';
import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Course template list: standalone reusable templates (D44) — no program,
	// scheduling, or classroom columns (those live on offerings). The list
	// endpoint takes no search/sort params, so the search box and Code/Name
	// header toggles filter/sort client-side over the loaded page while the
	// status filter goes to the server (?is_active). Deactivate/Reactivate
	// PATCHes is_active; Delete permanently removes an archived course
	// (DELETE /admin/courses/{id}, blocked with 409 while offerings still
	// reference it).

	let search = $state('');
	let statusFilter = $state<'all' | 'active' | 'inactive'>('all');

	let formOpen = $state(false);
	let editing = $state<AdminCourse | null>(null);
	let formError = $state<string | null>(null);
	let fieldErrors = $state<Record<string, string>>({});
	let formBusy = $state(false);

	let deleteTarget = $state<AdminCourse | null>(null);
	let deleteBusy = $state(false);

	// Deactivate confirm (Deactivate flips to inactive; Reactivate stays
	// immediate since it only restores).
	let deactivateTarget = $state<AdminCourse | null>(null);
	let deactivateBusy = $state(false);
	let reactivateTarget = $state<AdminCourse | null>(null);
	let reactivateBusy = $state(false);

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
		fieldErrors = {};
		f_code = '';
		f_name = '';
		f_units = '';
		f_duration = '';
		formOpen = true;
	};

	const openEdit = (c: AdminCourse) => {
		editing = c;
		formError = null;
		fieldErrors = {};
		f_code = c.courseCode;
		f_name = c.courseName;
		f_units = String(c.units);
		f_duration = String(c.sessionDurationHours);
		formOpen = true;
	};

	const clearFieldError = (field: string) => {
		if (fieldErrors[field]) fieldErrors = { ...fieldErrors, [field]: '' };
	};

	const submitForm = async () => {
		formError = null;
		fieldErrors = {};
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
					const fe: Record<string, string> = {};
					for (const issue of parsed.error.issues) {
						const key = String(issue.path[0] ?? '');
						if (key && !fe[key]) fe[key] = issue.message;
					}
					fieldErrors = fe;
					formError =
						Object.keys(fe).length > 0
							? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
							: (parsed.error.issues[0]?.message ?? 'Check the form and try again.');
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
					const fe: Record<string, string> = {};
					for (const issue of parsed.error.issues) {
						const key = String(issue.path[0] ?? '');
						if (key && !fe[key]) fe[key] = issue.message;
					}
					fieldErrors = fe;
					formError =
						Object.keys(fe).length > 0
							? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
							: (parsed.error.issues[0]?.message ?? 'Check the form and try again.');
					return;
				}
				await createCourse({
					course_code: parsed.data.course_code,
					course_name: parsed.data.course_name,
					units: parsed.data.units,
					session_duration_hours: parsed.data.session_duration_hours,
				});
			}
			fieldErrors = {};
			formOpen = false;
			await refreshAdminCourses();
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			if (e instanceof APIError && e.code === 'validation_error') {
				formError =
					'Some information needs your attention. Review the highlighted fields and correct the indicated errors.';
			} else {
				formError = friendlyActionError(
					e,
					'We couldn’t save the course due to an unexpected error. Please try again.'
				);
			}
		} finally {
			formBusy = false;
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteArchivedCourse(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const closeDelete = () => {
		adminCoursesState.actionError = null;
		deleteTarget = null;
	};

	const confirmDeactivate = async () => {
		if (!deactivateTarget || deactivateBusy) return;
		deactivateBusy = true;
		try {
			await toggleCourseActive(deactivateTarget);
			deactivateTarget = null;
		} finally {
			deactivateBusy = false;
		}
	};

	const closeDeactivate = () => {
		adminCoursesState.actionError = null;
		deactivateTarget = null;
	};

	const confirmReactivate = async () => {
		if (!reactivateTarget || reactivateBusy) return;
		reactivateBusy = true;
		try {
			await toggleCourseActive(reactivateTarget);
			if (!adminCoursesState.actionError) reactivateTarget = null;
		} finally {
			reactivateBusy = false;
		}
	};

	const closeReactivate = () => {
		adminCoursesState.actionError = null;
		reactivateTarget = null;
	};
</script>

<div class="page page-enter">
	<header class="header">
		<div>
			<h1>Course Management</h1>
			<p class="muted">Reusable templates — scheduling lives on offerings · {adminCoursesState.total} total</p>
		</div>
		<div class="header-actions">
			<button class="btn btn-secondary" data-testid="import" onclick={() => goto(Routes.ADMIN_COURSES_IMPORT)}>
				<AppIcon name="file" size={18} />
				Import
			</button>
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
		<SkeletonTable rows={8} cols={6} label="Loading courses…" />
	{:else if adminCoursesState.error}
		<section class="card"><p class="error">Could not load courses: {adminCoursesState.error}</p></section>
	{:else if visibleItems.length === 0}
		<section class="card">
			<EmptyState
				icon="file"
				title="No courses yet"
				hint="Add the first template — offerings attach it to a program and year."
			/>
		</section>
	{:else}
		<section class="card table-wrap" aria-busy={adminCoursesState.loading}>
			{#if adminCoursesState.actionError && !deleteTarget && !deactivateTarget}
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
						<th scope="col">Units</th>
						<th scope="col">Default session (h)</th>
						<th scope="col">Status</th>
						<th scope="col"><span class="sr">Actions</span></th>
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
							<td>
								<div class="row-actions">
									<button class="link" onclick={() => goto(adminCourse(c.id))}>Open</button>
									<button class="link" onclick={() => openEdit(c)}>Edit</button>
									{#if c.isActive}
										<button
											class="link"
											onclick={() => { adminCoursesState.actionError = null; deactivateTarget = c; }}
										>
											Deactivate
										</button>
									{:else}
										<button
											class="link success"
											onclick={() => { adminCoursesState.actionError = null; reactivateTarget = c; }}
										>
											Reactivate
										</button>
									{/if}
									{#if !c.isActive}
										<button
											class="link danger"
											onclick={() => { adminCoursesState.actionError = null; deleteTarget = c; }}
										>
											Delete
										</button>
									{/if}
								</div>
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
			use:trapFocus={{ onEscape: () => (formBusy ? undefined : (formOpen = false)) }}
		>
			<h2 id="course-form-title" class="modal-title">{editing ? 'Edit course' : 'Add course'}</h2>
			{#if formError}
				<p class="error form-error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<section class="form-section">
					<h3 class="form-section-title">Course details</h3>
					<div class="grid2">
						<label>
							Course code *
							<input
								class="input"
								class:invalid={!!fieldErrors.course_code}
								bind:value={f_code}
								placeholder="CS101"
								maxlength="20"
								aria-required="true"
								aria-invalid={!!fieldErrors.course_code}
								aria-describedby="course-code-help"
								oninput={() => clearFieldError('course_code')}
							/>
							{#if fieldErrors.course_code}
								<p class="field-error" role="alert">{fieldErrors.course_code}</p>
							{:else}
								<p class="hint" id="course-code-help">2–20 characters. Stored in uppercase.</p>
							{/if}
						</label>
						<label>
							Units *
							<input
								class="input"
								class:invalid={!!fieldErrors.units}
								type="text"
								inputmode="numeric"
								bind:value={f_units}
								placeholder="3"
								min="1"
								step="1"
								aria-required="true"
								aria-invalid={!!fieldErrors.units}
								aria-describedby="course-units-help"
								oninput={() => clearFieldError('units')}
							/>
							{#if fieldErrors.units}
								<p class="field-error" role="alert">{fieldErrors.units}</p>
							{:else}
								<p class="hint" id="course-units-help">Whole number of credit units (1 or more). Example: 3 units = 3 hours of scheduled class time per week.</p>
							{/if}
						</label>
					</div>
					<label>
						Course name *
						<input
							class="input"
							class:invalid={!!fieldErrors.course_name}
							bind:value={f_name}
							placeholder="Software Engineering 1"
							maxlength="100"
							aria-required="true"
							aria-invalid={!!fieldErrors.course_name}
							aria-describedby="course-name-help"
							oninput={() => clearFieldError('course_name')}
						/>
						{#if fieldErrors.course_name}
							<p class="field-error" role="alert">{fieldErrors.course_name}</p>
						{:else}
							<p class="hint" id="course-name-help">Up to 100 characters.</p>
						{/if}
					</label>
				</section>
				<section class="form-section">
					<h3 class="form-section-title">Credit &amp; session defaults</h3>
					<label>
						Default session length (hours) *
						<input
							class="input"
							class:invalid={!!fieldErrors.session_duration_hours}
							inputmode="decimal"
							bind:value={f_duration}
							placeholder="1.5"
							min="0.5"
							max="8"
							step="0.5"
							aria-required="true"
							aria-invalid={!!fieldErrors.session_duration_hours}
							aria-describedby="course-duration-help"
							oninput={() => clearFieldError('session_duration_hours')}
						/>
						{#if fieldErrors.session_duration_hours}
							<p class="field-error" role="alert">{fieldErrors.session_duration_hours}</p>
						{:else}
							<p class="hint" id="course-duration-help">Typical length of one class session (0.5–8 hours). Used for attendance windows and fallback session expiry.</p>
						{/if}
					</label>
					<p class="hint">Attendance window budget and fallback session length — actual meeting lengths are set per offering meeting and must total within the units requirement per week. Program, schedule, and classroom attach later via offerings. Lecture/laboratory sessions are scheduled per offering, so one course can mix both.</p>
				</section>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={formBusy} onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-course" aria-busy={formBusy} disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if reactivateTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="reactivate-course-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reactivateBusy ? undefined : (reactivateTarget = null)) }}
		>
			<h2 id="reactivate-course-title" class="modal-title">Reactivate {reactivateTarget.courseCode}?</h2>
			<p class="modal-text">
				{reactivateTarget.courseName} will be restored to the active list.
			</p>
			{#if adminCoursesState.actionError}
				<p class="error" role="alert">{adminCoursesState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={reactivateBusy} onclick={closeReactivate}>Cancel</button>
				<button class="btn btn-success" disabled={reactivateBusy} onclick={confirmReactivate}>
					{reactivateBusy ? 'Reactivating…' : 'Reactivate'}
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
			aria-labelledby="deactivate-course-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDeactivate }}
		>
			<h2 id="deactivate-course-title" class="modal-title">Deactivate {deactivateTarget.courseCode}?</h2>
			<p class="modal-text">
				{deactivateTarget.courseName} will be flipped to inactive. Its offerings
				keep working, and you can reactivate it anytime.
			</p>
			{#if adminCoursesState.actionError}
				<p class="error" role="alert">{adminCoursesState.actionError}</p>
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
			aria-labelledby="delete-course-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeDelete }}
		>
			<h2 id="delete-course-title" class="modal-title">Permanently delete {deleteTarget.courseCode}?</h2>
			<p class="modal-text">
				{deleteTarget.courseName} will be removed for good.
				If offerings still use it, deletion will be blocked
				and the course stays archived.
			</p>
			{#if adminCoursesState.actionError}
				<p class="error" role="alert">{adminCoursesState.actionError}</p>
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

	.link.success {
		color: var(--success);
	}

	.btn-success {
		background: var(--success);
		border: 1px solid var(--success);
		color: var(--on-brand);
	}

	.btn-success:hover:not(:disabled) {
		filter: brightness(1.05);
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

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.form-error {
		margin-bottom: 0.5rem;
	}

	.form-section {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
	}

	.form-section-title {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.input.invalid {
		border-color: var(--danger);
	}

	.field-error {
		color: var(--danger);
		font-size: 0.75rem;
		margin: 0;
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
