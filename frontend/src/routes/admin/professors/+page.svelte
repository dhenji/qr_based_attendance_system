<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TempPasswordModal from '$lib/components/TempPasswordModal.svelte';
	import {
		adminProfessorsState,
		deleteArchivedProfessor,
		initAdminProfessors,
		refreshAdminProfessors,
		toggleProfessorActive,
	} from '$lib/features/admin/store.svelte';
	import { createProfessor, resetProfessorPassword, updateProfessor } from '$lib/features/admin/service';
	import {
		enrichOfferings,
		listOfferings,
		offeringTitle,
	} from '$lib/features/admin/offerings/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import {
		adminProfessorCreateSchema,
		adminProfessorUpdateSchema,
	} from '$lib/features/admin/schema';
	import type { AdminOffering, AdminProfessor, Program } from '$lib/shared/types';
	import { goto } from '$app/navigation';
	import { adminProfessor, Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Professor Management (wireframe 4.4): same CRUD pattern as students, but
	// the roster seeds the records professors claim at registration. Columns:
	// Name, Email, Department, Courses, Claim. (Status lives in the Archive.)

	let search = $state('');
	let department = $state('');
	let sortBy = $state<'last_name' | 'email' | 'created_at'>('last_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let formOpen = $state(false);
	let editing = $state<AdminProfessor | null>(null);
	let formError = $state<string | null>(null);
	let fieldErrors = $state<Record<string, string>>({});
	let formBusy = $state(false);
	let deleteTarget = $state<AdminProfessor | null>(null);
	let deleteBusy = $state(false);
	let toggleTarget = $state<AdminProfessor | null>(null);
	let toggleBusy = $state(false);
	// Credential reset; see the students page for why the modal is shared.
	let resetTarget = $state<AdminProfessor | null>(null);

	let f_first_name = $state('');
	let f_middle_name = $state('');
	let f_last_name = $state('');
	let f_email = $state('');
	let f_department = $state('');
	let f_courses = $state<number[]>([]);
	let offeringOptions = $state<AdminOffering[]>([]);
	let offeringSearch = $state('');
	let programOptions = $state<Program[]>([]);
	let offeringsLoading = $state(false);
	let offeringsError = $state<string | null>(null);

	const totalPages = $derived(
		Math.max(1, Math.ceil(adminProfessorsState.total / adminProfessorsState.size))
	);

	const load = (page = 1) =>
		initAdminProfessors(
			{
				search: search.trim() || undefined,
				department: department.trim() || undefined,
				is_active: true,
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
			const [offeringPage, coursePage, programPage] = await Promise.all([
				listOfferings({ is_active: true, page: 1, size: 50 }),
				listCourses({ page: 1, size: 100 }).catch(() => ({ items: [] })),
				listPrograms({ page: 1, size: 50 }).catch(() => ({ items: [] })),
			]);
			const programIds = [...new Set(offeringPage.items.map((o) => o.programId))];
			const yearsNested = await Promise.all(
				programIds.map((pid) => listYearLevels(pid).catch(() => []))
			);
			programOptions = programPage.items ?? [];
			offeringOptions = enrichOfferings(
				offeringPage.items,
				coursePage.items ?? [],
				programPage.items ?? [],
				yearsNested.flat()
			);
		} catch (e: unknown) {
			offeringsError = e instanceof Error && e.message ? e.message : 'Could not load offerings';
		} finally {
			offeringsLoading = false;
		}
	};

	const filteredOfferings = $derived.by(() => {
		const term = offeringSearch.trim().toLowerCase();
		if (!term) return offeringOptions;
		return offeringOptions.filter((o) =>
			`${o.courseCode ?? ''} ${o.courseName ?? ''} ${o.programCode ?? ''} ${o.semester ?? ''}`
				.toLowerCase()
				.includes(term)
		);
	});

	const offeringPrimary = (o: AdminOffering): string =>
		o.courseCode && o.courseName
			? `${o.courseCode} — ${o.courseName}`
			: (o.courseCode ?? `Course ${o.courseId}`);

	const offeringSecondary = (o: AdminOffering): string => {
		const cohort = [o.programCode ?? `Program ${o.programId}`, o.yearLevelLabel].filter(Boolean).join(' · ');
		const term = `${o.semester} ${o.academicYear}`;
		const schedule = `${o.scheduleDays} ${o.scheduleStartTime.slice(0, 5)}–${o.scheduleEndTime.slice(0, 5)}`;
		return [cohort, term, schedule, o.classroomName].filter(Boolean).join(' · ');
	};

	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!adminProfessorsState.loading) void refreshAdminProfessors();
	};

	onMount(() => {
		load(1);
		loadOfferings();
		// Own entity -> refresh the table; offerings feed the assign picker.
		autoRefreshStops.push(
			subscribeEntity('professors', refreshVisible),
			subscribeEntity('offerings', () => void loadOfferings()),
			// Programs feed the department dropdown + offering joins.
			subscribeEntity('programs', () => void loadOfferings()),
			onFocusRevalidate(refreshVisible)
		);
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

	const clearFieldError = (field: string) => {
		if (fieldErrors[field]) fieldErrors = { ...fieldErrors, [field]: '' };
	};

	const openCreate = () => {
		editing = null;
		formError = null;
		fieldErrors = {};
		f_first_name = '';
		f_middle_name = '';
		f_last_name = '';
		f_email = '';
		f_department = '';
		f_courses = [];
		offeringSearch = '';
		if (offeringOptions.length === 0) loadOfferings();
		formOpen = true;
	};

	const openEdit = (p: AdminProfessor) => {
		editing = p;
		formError = null;
		fieldErrors = {};
		f_first_name = p.firstName;
		f_middle_name = p.middleName ?? '';
		f_last_name = p.lastName;
		f_email = p.email;
		f_department = p.department ?? '';
		f_courses = (p.assigned_courses ?? []).map((c) => c.offering_id);
		offeringSearch = '';
		if (offeringOptions.length === 0) loadOfferings();
		formOpen = true;
	};

	const submitForm = async () => {
		formError = null;
		fieldErrors = {};
		formBusy = true;
		try {
			if (editing === null) {
				const parsed = adminProfessorCreateSchema.safeParse({
					first_name: f_first_name,
					middle_name: f_middle_name || undefined,
					last_name: f_last_name,
					email: f_email,
					department: f_department || undefined,
					courses: f_courses,
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
				const d = parsed.data;
				await createProfessor({
					first_name: d.first_name,
					middle_name: d.middle_name || undefined,
					last_name: d.last_name,
					email: d.email,
					department: d.department || undefined,
					courses: d.courses.length > 0 ? d.courses : undefined,
				});
			} else {
			const parsed = adminProfessorUpdateSchema.safeParse({
				first_name: f_first_name,
				middle_name: f_middle_name || undefined,
				last_name: f_last_name,
				email: f_email,
				department: f_department || undefined,
				courses: f_courses,
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
			const d = parsed.data;
			await updateProfessor(editing.id, {
				first_name: d.first_name,
				// Prefilled modal: empty means "cleared" — send null so the
				// backend nulls the column instead of leaving it unchanged.
				middle_name: d.middle_name || null,
				last_name: d.last_name,
				email: d.email,
				department: d.department || null,
				courses: d.courses,
			});
			}
			formOpen = false;
			await refreshAdminProfessors();
			notifyEntityChanged('professors');
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
			await deleteArchivedProfessor(deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const confirmToggle = async () => {
		if (!toggleTarget || toggleBusy) return;
		toggleBusy = true;
		try {
			await toggleProfessorActive(toggleTarget);
			if (!adminProfessorsState.actionError) toggleTarget = null;
		} finally {
			toggleBusy = false;
		}
	};
</script>

<div class="page page-enter">
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
		<button class="btn btn-secondary" data-testid="apply" onclick={applyFilters}>Apply</button>
	</section>

	{#if adminProfessorsState.loading && adminProfessorsState.items.length === 0}
		<SkeletonTable rows={8} cols={6} label="Loading professors…" />
	{:else if adminProfessorsState.error}
		<section class="card"><p class="error">Could not load professors: {adminProfessorsState.error}</p></section>
	{:else if adminProfessorsState.items.length === 0}
		<section class="card">
			<EmptyState
				icon="users"
				title="No professors match these filters"
				hint="Add the first record to seed the roster."
			/>
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
						<th scope="col">Department</th>
						<th scope="col">Courses</th>
						<th scope="col">Claim</th>
						<th scope="col"><span class="sr">Actions</span></th>
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
								<div class="row-actions">
									<button class="link" onclick={() => openEdit(p)}>Edit</button>
									<button
										class="link"
										onclick={() => {
											adminProfessorsState.actionError = null;
											toggleTarget = p;
										}}
									>
										{p.isActive ? 'Deactivate' : 'Reactivate'}
									</button>
									{#if !p.isActive}
										<button class="link danger" onclick={() => { adminProfessorsState.actionError = null; deleteTarget = p; }}>Delete</button>
									{/if}
									<button class="link" onclick={() => (resetTarget = p)}>Reset password</button>
								</div>
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
					<label>
						First name *
						<input
							class="input"
							class:invalid={!!fieldErrors.first_name}
							bind:value={f_first_name}
							maxlength="100"
							aria-required="true"
							aria-invalid={!!fieldErrors.first_name}
							aria-describedby="prof-first-help"
							oninput={() => clearFieldError('first_name')}
						/>
						{#if fieldErrors.first_name}
							<p class="field-error" role="alert">{fieldErrors.first_name}</p>
						{:else}
							<p class="hint" id="prof-first-help">Up to 100 characters.</p>
						{/if}
					</label>
					<label>
						Middle name (optional)
						<input
							class="input"
							class:invalid={!!fieldErrors.middle_name}
							bind:value={f_middle_name}
							maxlength="100"
							aria-invalid={!!fieldErrors.middle_name}
							aria-describedby="prof-middle-help"
							oninput={() => clearFieldError('middle_name')}
						/>
						{#if fieldErrors.middle_name}
							<p class="field-error" role="alert">{fieldErrors.middle_name}</p>
						{:else}
							<p class="hint" id="prof-middle-help">Optional. Leave blank if no middle name.</p>
						{/if}
					</label>
				</div>
				<div class="grid2">
					<label>
						Last name *
						<input
							class="input"
							class:invalid={!!fieldErrors.last_name}
							bind:value={f_last_name}
							maxlength="100"
							aria-required="true"
							aria-invalid={!!fieldErrors.last_name}
							aria-describedby="prof-last-help"
							oninput={() => clearFieldError('last_name')}
						/>
						{#if fieldErrors.last_name}
							<p class="field-error" role="alert">{fieldErrors.last_name}</p>
						{:else}
							<p class="hint" id="prof-last-help">Up to 100 characters.</p>
						{/if}
					</label>
					<label>
						Email *
						<input
							class="input"
							class:invalid={!!fieldErrors.email}
							type="email"
							bind:value={f_email}
							maxlength="255"
							aria-required="true"
							aria-invalid={!!fieldErrors.email}
							aria-describedby="prof-email-help"
							oninput={() => clearFieldError('email')}
						/>
						{#if fieldErrors.email}
							<p class="field-error" role="alert">{fieldErrors.email}</p>
						{:else}
							<p class="hint" id="prof-email-help">Valid email, up to 255 characters.</p>
						{/if}
					</label>
				</div>
				<label>
					Department (optional)
					<input
						class="input"
						class:invalid={!!fieldErrors.department}
						bind:value={f_department}
						list="department-suggestions"
						autocomplete="off"
						placeholder="Type or pick a program…"
						maxlength="100"
						aria-invalid={!!fieldErrors.department}
						aria-describedby="prof-dept-help"
						oninput={() => clearFieldError('department')}
					/>
					{#if fieldErrors.department}
						<p class="field-error" role="alert">{fieldErrors.department}</p>
					{:else}
						<p class="hint" id="prof-dept-help">Optional org unit — teaching scope comes from the offerings below.</p>
					{/if}
				</label>
				<datalist id="department-suggestions">
					{#each programOptions as p (p.id)}
						<option value={p.code}>{p.name}</option>
						<option value={p.name}>{p.code}</option>
					{/each}
				</datalist>
				<fieldset class="courses" aria-describedby="prof-courses-help">
					<legend>Course assignments (offerings) · {f_courses.length} selected</legend>
					<p class="hint" id="prof-courses-help">Select one or more offerings; leave empty if none.</p>
					{#if offeringsLoading}
						<div class="skeleton-stack" role="status" aria-busy="true">
							<span class="sr-only">Loading offerings…</span>
							<Skeleton height={14} width="70%" />
							<Skeleton height={14} width="55%" />
						</div>
					{:else if offeringsError}
						<p class="error" role="alert">{offeringsError}</p>
					{:else if offeringOptions.length === 0}
						<p class="hint">No active offerings found. Create one under Offerings first.</p>
					{:else}
						<input
							class="input offering-search"
							type="search"
							placeholder="Filter by code, name, program…"
							aria-label="Filter offerings"
							bind:value={offeringSearch}
						/>
						{#if filteredOfferings.length === 0}
							<p class="hint">No offerings match “{offeringSearch.trim()}”.</p>
						{:else}
							{#each filteredOfferings as o (o.id)}
								<label class="check" title={offeringTitle(o)}>
									<input
										type="checkbox"
										checked={f_courses.includes(o.id)}
										onchange={() => toggleCourse(o.id)}
									/>
									<span class="offering-text">
										<span class="primary">{offeringPrimary(o)}</span>
										<span class="secondary">{offeringSecondary(o)}</span>
									</span>
								</label>
							{/each}
						{/if}
					{/if}
				</fieldset>
				<p class="hint">Assignments are saved with the professor (replaces the set on edit); no user row is created until the professor self-registers.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (formOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-professor" aria-busy={formBusy} disabled={formBusy} onclick={submitForm}>
					{formBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if toggleTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="toggle-professor-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (toggleBusy ? undefined : (toggleTarget = null)) }}
		>
			<h2 id="toggle-professor-title" class="modal-title">
				{toggleTarget.isActive ? 'Deactivate professor?' : 'Reactivate professor?'}
			</h2>
			<p class="modal-text">
				{#if toggleTarget.isActive}
					{fullName(toggleTarget)} will be moved to the Archive and lose login access. You can restore them later from the Archive.
				{:else}
					{fullName(toggleTarget)} will return to the active roster and regain login access.
				{/if}
			</p>
			{#if adminProfessorsState.actionError}
				<p class="error" role="alert">{adminProfessorsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={toggleBusy} onclick={() => (toggleTarget = null)}>Cancel</button>
				<button
					class="btn {toggleTarget.isActive ? 'btn-danger' : 'btn-primary'}"
					aria-busy={toggleBusy}
					disabled={toggleBusy}
					onclick={() => void confirmToggle()}
				>
					{toggleBusy ? 'Saving…' : (toggleTarget.isActive ? 'Deactivate' : 'Reactivate')}
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
				{fullName(deleteTarget)} is inactive. This cannot be undone. If class sessions are
				still linked, deletion will be blocked and the record stays archived.
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
		align-items: flex-start;
		gap: 0.5rem;
		font-weight: 500;
		cursor: pointer;
	}

	.courses .check input {
		margin-top: 0.2rem;
		flex-shrink: 0;
	}

	.offering-search {
		width: 100%;
	}

	.offering-text {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		min-width: 0;
	}

	.offering-text .primary {
		font-weight: 600;
		color: var(--text-strong);
	}

	.offering-text .secondary {
		font-size: 0.75rem;
		font-weight: 400;
		color: var(--text-muted);
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

	.input.invalid {
		border-color: var(--danger);
	}

	.field-error {
		color: var(--danger);
		font-size: 0.75rem;
		margin: 0;
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
