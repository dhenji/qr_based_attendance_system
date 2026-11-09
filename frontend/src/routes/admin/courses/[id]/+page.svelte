<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import SkeletonTable from '$lib/components/SkeletonTable.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		adminCourseDetailState,
		adminCoursesState,
		deleteArchivedCourse,
		initAdminCourseDetail,
		refreshAdminCourseDetail,
	} from '$lib/features/admin/courses/store.svelte';
	import {
		setCourseActive,
		updateCourse,
	} from '$lib/features/admin/courses/service';
	import { APIError } from '$lib/api/client';
import { courseUpdateSchema } from '$lib/features/admin/courses/schema';
import { friendlyActionError } from '$lib/shared/utils/deleteErrors';
	import {
		enrichOfferings,
		listOfferings,
	} from '$lib/features/admin/offerings/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import type { AdminOffering, Program, YearLevel } from '$lib/shared/types';
import { sessionMixLabel } from '$lib/shared/types';
	import { Routes, adminOffering } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Course Detail: template overview (units, duration) plus the offerings
	// that instance it across programs/years (D6: one template spans many
	// cohorts). Offering rows link to the offering detail, where schedule,
	// professors, roster, and settings live (wireframe 4.5d, admin-manual
	// §2.4). Archive here is DELETE (soft, is_active=false).

	const courseId = $derived(Number(page.params.id));
	const course = $derived(adminCourseDetailState.course);

	let offerings = $state<AdminOffering[]>([]);
	let offeringsLoading = $state(false);
	let offeringsError = $state<string | null>(null);

	let editOpen = $state(false);
	let e_code = $state('');
	let e_name = $state('');
	let e_units = $state('');
	let e_duration = $state('');
	let editError = $state<string | null>(null);
	let editFieldErrors = $state<Record<string, string>>({});
	let editBusy = $state(false);

	let archiveBusy = $state(false);
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!Number.isFinite(courseId) || courseId <= 0) return;
		if (!adminCourseDetailState.loading) void refreshAdminCourseDetail(courseId);
	};

	onMount(() => {
		if (Number.isFinite(courseId) && courseId > 0) {
			initAdminCourseDetail(courseId);
			loadOfferings(courseId);
		}
		// Own entity -> refresh the detail (1 GET on focus); offerings
		// events -> reload the joined offerings rows below.
		autoRefreshStops.push(
			subscribeEntity('courses', refreshVisible),
			subscribeEntity('offerings', () => {
				if (Number.isFinite(courseId) && courseId > 0 && !offeringsLoading)
					void loadOfferings(courseId);
			}),
			onFocusRevalidate(refreshVisible)
		);
	});

	// Offerings of this template, joined with program/year labels for display
	// (the contract carries ids only). Programs load once; year levels load
	// per distinct program present, like the students cascade.
	const loadOfferings = async (id: number) => {
		offeringsLoading = true;
		offeringsError = null;
		try {
			const raw = await listOfferings({ course_id: id, page: 1, size: 50 });
			const courses = (await listCourses({ page: 1, size: 100 })).items;
			const programs: Program[] = (await listPrograms({ page: 1, size: 50 })).items;
			const programIds = [...new Set(raw.items.map((o) => o.programId))];
			const years: YearLevel[] = (
				await Promise.all(programIds.map((pid) => listYearLevels(pid).catch(() => [])))
			).flat();
			offerings = enrichOfferings(raw.items, courses, programs, years);
		} catch (e: unknown) {
			offeringsError = e instanceof Error && e.message ? e.message : 'Could not load offerings';
		} finally {
			offeringsLoading = false;
		}
	};

	const openEdit = () => {
		if (!course) return;
		editError = null;
		editFieldErrors = {};
		e_code = course.courseCode;
		e_name = course.courseName;
		e_units = String(course.units);
		e_duration = String(course.sessionDurationHours);
		editOpen = true;
	};

	const clearEditFieldError = (field: string) => {
		if (editFieldErrors[field]) editFieldErrors = { ...editFieldErrors, [field]: '' };
	};

	const submitEdit = async () => {
		if (!course) return;
		editError = null;
		editFieldErrors = {};
		editBusy = true;
		try {
			const parsed = courseUpdateSchema.safeParse({
				course_code: e_code,
				course_name: e_name,
				units: e_units,
				session_duration_hours: e_duration,
			});
			if (!parsed.success) {
				const fe: Record<string, string> = {};
				for (const issue of parsed.error.issues) {
					const key = String(issue.path[0] ?? '');
					if (key && !fe[key]) fe[key] = issue.message;
				}
				editFieldErrors = fe;
				editError =
					Object.keys(fe).length > 0
						? 'Some information needs your attention. Review the highlighted fields and correct the indicated errors.'
						: (parsed.error.issues[0]?.message ?? 'Check the form and try again.');
				return;
			}
			await updateCourse(course.id, {
				course_code: parsed.data.course_code,
				course_name: parsed.data.course_name,
				units: parsed.data.units,
				session_duration_hours: parsed.data.session_duration_hours,
			});
			editFieldErrors = {};
			editOpen = false;
			await refreshAdminCourseDetail(course.id);
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			if (e instanceof APIError && e.code === 'validation_error') {
				editError =
					'Some information needs your attention. Review the highlighted fields and correct the indicated errors.';
			} else {
				editError = friendlyActionError(
					e,
					'We couldn’t save the course due to an unexpected error. Please try again.'
				);
			}
		} finally {
			editBusy = false;
		}
	};

	const onArchive = async () => {
		if (!course || archiveBusy) return;
		archiveBusy = true;
		try {
			await setCourseActive(course.id, false);
			await refreshAdminCourseDetail(course.id);
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			adminCourseDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to archive course';
		} finally {
			archiveBusy = false;
		}
	};

	const onReactivate = async () => {
		if (!course || archiveBusy) return;
		archiveBusy = true;
		try {
			await setCourseActive(course.id, true);
			await refreshAdminCourseDetail(course.id);
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			adminCourseDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to reactivate course';
		} finally {
			archiveBusy = false;
		}
	};

	let deleteOpen = $state(false);
	let deleteBusy = $state(false);
	let archiveConfirm = $state(false);

	const confirmArchive = async () => {
		await onArchive();
		if (course && !course.isActive) archiveConfirm = false;
	};

	const confirmDelete = async () => {
		if (!course || deleteBusy) return;
		deleteBusy = true;
		try {
			await deleteArchivedCourse(course.id);
			deleteOpen = false;
			notifyEntityChanged('courses');
			await goto(Routes.ADMIN_COURSES);
		} catch {
			// The store holds the friendly guard copy (`course_has_offerings`,
			// …); mirror it onto the detail state so the modal shows it even
			// on a direct landing.
			adminCourseDetailState.actionError =
				adminCoursesState.actionError ?? 'Failed to delete course';
		} finally {
			deleteBusy = false;
		}
	};
</script>

<div class="page">
	<div class="page-top">
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_COURSES)}>
			← Back to Course Management
		</button>
	</div>

	{#if adminCourseDetailState.loading}
		<SkeletonDetail rows={5} label="Loading course…" />
	{:else if adminCourseDetailState.error || !course}
		<section class="card">
			<p class="error">Could not load course: {adminCourseDetailState.error ?? 'Not found'}</p>
		</section>
	{:else}
		<header class="header">
			<div>
				<h1>{course.courseCode} — {course.courseName}</h1>
				<p class="muted">
					Units: {course.units} · Default session: {course.sessionDurationHours}h ·
					<span class="badge" class:inactive={!course.isActive}>
						{course.isActive ? 'Active' : 'Inactive'}
					</span>
				</p>
			</div>
			<div class="header-actions">
				<button class="btn btn-secondary" onclick={openEdit}>Edit</button>
			</div>
		</header>

		{#if adminCourseDetailState.actionError && !deleteOpen && !archiveConfirm}
			<section class="card"><p class="error" role="alert">{adminCourseDetailState.actionError}</p></section>
		{/if}

		<section class="card">
			<h2 class="card-title">Offerings ({offerings.length})</h2>
			<p class="muted">Program/year instances of this template. Schedule, professors, and roster live on each offering.</p>
			{#if offeringsLoading}
				<SkeletonTable bare rows={3} cols={5} label="Loading offerings…" />
			{:else if offeringsError}
				<p class="error">{offeringsError}</p>
			{:else if offerings.length === 0}
				<EmptyState
					icon="file"
					title="No offerings yet"
					hint="Create one from the Offerings page."
				/>
			{:else}
				<div class="table-wrap">
					<table>
						<thead>
							<tr>
								<th scope="col">Cohort</th>
								<th scope="col">Term</th>
								<th scope="col">Schedule</th>
								<th scope="col">Type</th>
								<th scope="col">Enrolled</th>
								<th scope="col">Status</th>
								<th scope="col"><span class="sr">Actions</span></th>
							</tr>
						</thead>
						<tbody>
							{#each offerings as o (o.id)}
								<tr>
									<td>{[o.programCode ?? `Program ${o.programId}`, o.yearLevelLabel ?? `Year ${o.yearLevelId}`].join(' · ')}</td>
									<td>{o.semester} {o.academicYear}</td>
									<td>{o.scheduleDays} {o.scheduleStartTime.slice(0, 5)}–{o.scheduleEndTime.slice(0, 5)}</td>
									<td>
										<span class="badge type-lab" class:type-lec={o.sessionTypes[0] === 'lecture' && o.sessionTypes.length === 1}>
											{sessionMixLabel(o.sessionTypes)}
										</span>
									</td>
									<td>{o.enrolledCount}</td>
									<td>
										<span class="badge" class:inactive={!o.isActive}>
											{o.isActive ? 'Active' : 'Inactive'}
										</span>
									</td>
									<td>
										<div class="row-actions">
											<button class="link" onclick={() => goto(adminOffering(o.id))}>Open</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>

		<section class="card danger">
			<h2 class="card-title">Danger zone</h2>
			<p class="muted">
				Status: <strong>{course.isActive ? 'Active' : 'Inactive'}</strong>. Archiving
				flips this template to inactive — existing offerings keep working.
				Reactivating restores it. Deletion is permanent and blocked while
				offerings still use this template.
			</p>
			<div class="danger-actions">
				{#if course.isActive}
					<button class="btn btn-danger" disabled={archiveBusy} onclick={() => { adminCourseDetailState.actionError = null; archiveConfirm = true; }}>
						Archive course
					</button>
				{:else}
					<button class="btn btn-secondary" disabled={archiveBusy} onclick={onReactivate}>
						{archiveBusy ? 'Reactivating…' : 'Reactivate course'}
					</button>
				{/if}
				<button
					class="btn btn-danger"
					disabled={deleteBusy || course.isActive}
					title={course.isActive ? 'Archive first — only archived courses can be deleted' : undefined}
					onclick={() => { adminCourseDetailState.actionError = null; deleteOpen = true; }}
				>
					Delete permanently
				</button>
			</div>
			{#if !course.isActive}
				<p class="hint">Delete is blocked while offerings still use this template.</p>
			{/if}
		</section>
	{/if}
</div>

{#if editOpen && course}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="course-edit-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (editBusy ? undefined : (editOpen = false)) }}
		>
			<h2 id="course-edit-title" class="modal-title">Edit course</h2>
			{#if editError}
				<p class="error form-error" role="alert">{editError}</p>
			{/if}
			<div class="form">
				<section class="form-section">
					<h3 class="form-section-title">Course details</h3>
					<div class="grid2">
						<label>
							Course code *
							<input
								class="input"
								class:invalid={!!editFieldErrors.course_code}
								bind:value={e_code}
								maxlength="20"
								aria-required="true"
								aria-invalid={!!editFieldErrors.course_code}
								aria-describedby="edit-course-code-help"
								oninput={() => clearEditFieldError('course_code')}
							/>
							{#if editFieldErrors.course_code}
								<p class="field-error" role="alert">{editFieldErrors.course_code}</p>
							{:else}
								<p class="hint" id="edit-course-code-help">2–20 characters. Stored in uppercase.</p>
							{/if}
						</label>
						<label>
							Units *
							<input
								class="input"
								class:invalid={!!editFieldErrors.units}
								type="text"
								inputmode="numeric"
								bind:value={e_units}
								min="1"
								step="1"
								aria-required="true"
								aria-invalid={!!editFieldErrors.units}
								aria-describedby="edit-course-units-help"
								oninput={() => clearEditFieldError('units')}
							/>
							{#if editFieldErrors.units}
								<p class="field-error" role="alert">{editFieldErrors.units}</p>
							{:else}
								<p class="hint" id="edit-course-units-help">Whole number of credit units (1 or more). Example: 3 units = 3 hours of scheduled class time per week.</p>
							{/if}
						</label>
					</div>
					<label>
						Course name *
						<input
							class="input"
							class:invalid={!!editFieldErrors.course_name}
							bind:value={e_name}
							maxlength="100"
							aria-required="true"
							aria-invalid={!!editFieldErrors.course_name}
							aria-describedby="edit-course-name-help"
							oninput={() => clearEditFieldError('course_name')}
						/>
						{#if editFieldErrors.course_name}
							<p class="field-error" role="alert">{editFieldErrors.course_name}</p>
						{:else}
							<p class="hint" id="edit-course-name-help">Up to 100 characters.</p>
						{/if}
					</label>
				</section>
				<section class="form-section">
					<h3 class="form-section-title">Credit &amp; session defaults</h3>
					<label>
						Default session length (hours) *
						<input
							class="input"
							class:invalid={!!editFieldErrors.session_duration_hours}
							inputmode="decimal"
							bind:value={e_duration}
							min="0.5"
							max="8"
							step="0.5"
							aria-required="true"
							aria-invalid={!!editFieldErrors.session_duration_hours}
							aria-describedby="edit-course-duration-help"
							oninput={() => clearEditFieldError('session_duration_hours')}
						/>
						{#if editFieldErrors.session_duration_hours}
							<p class="field-error" role="alert">{editFieldErrors.session_duration_hours}</p>
						{:else}
							<p class="hint" id="edit-course-duration-help">Typical length of one class session (0.5–8 hours). Used for attendance windows and fallback session expiry.</p>
						{/if}
					</label>
				</section>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={editBusy} onclick={() => (editOpen = false)}>Cancel</button>
				<button class="btn btn-primary" aria-busy={editBusy} disabled={editBusy} onclick={submitEdit}>
					{editBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if archiveConfirm && course}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="course-archive-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (archiveConfirm = false) }}
		>
			<h2 id="course-archive-title" class="modal-title">Archive {course.courseCode}?</h2>
			<p class="modal-text">
				{course.courseName} will be flipped to inactive. Its offerings keep
				working, and you can reactivate it anytime.
			</p>
			{#if adminCourseDetailState.actionError}
				<p class="error" role="alert">{adminCourseDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (archiveConfirm = false)}>Cancel</button>
				<button class="btn btn-danger" aria-busy={archiveBusy} disabled={archiveBusy} onclick={confirmArchive}>
					{archiveBusy ? 'Archiving…' : 'Archive'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if deleteOpen && course}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="course-delete-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteOpen = false) }}
		>
			<h2 id="course-delete-title" class="modal-title">Permanently delete {course.courseCode}?</h2>
			<p class="modal-text">
				{course.courseName} will be removed for good.
				If offerings still use it, deletion will be blocked
				and the course stays archived.
			</p>
			{#if adminCourseDetailState.actionError}
				<p class="error" role="alert">{adminCourseDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteOpen = false)}>Cancel</button>
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
		flex-wrap: wrap;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
	}

	.card-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.card .muted {
		margin-bottom: 1rem;
	}

	.danger {
		border-color: var(--danger-bg);
	}

	.danger-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	.badge.type-lec {
		color: var(--success);
		background: var(--success-bg);
	}

	.badge.type-lab {
		color: var(--warning-text);
		background: var(--warning-bg);
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

	/* Back button reads as its own header block, so the .page flex gap
	 * does not push it a full row apart (same pattern as Program Management). */
	.page-top {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
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

	.btn-primary {
		background: var(--brand);
		border: 1px solid var(--brand);
		color: var(--on-brand);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--brand-hover);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.btn-danger:hover:not(:disabled) {
		background: var(--danger-strong);
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
