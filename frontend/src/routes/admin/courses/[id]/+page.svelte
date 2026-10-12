<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		adminCourseDetailState,
		initAdminCourseDetail,
		refreshAdminCourseDetail,
	} from '$lib/features/admin/courses/store.svelte';
	import {
		archiveCourse,
		setCourseActive,
		updateCourse,
	} from '$lib/features/admin/courses/service';
	import { courseUpdateSchema } from '$lib/features/admin/courses/schema';
	import {
		enrichOfferings,
		listOfferings,
	} from '$lib/features/admin/offerings/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import type { AdminOffering, Program, YearLevel } from '$lib/shared/types';
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
		e_code = course.courseCode;
		e_name = course.courseName;
		e_units = String(course.units);
		e_duration = String(course.sessionDurationHours);
		editOpen = true;
	};

	const submitEdit = async () => {
		if (!course) return;
		editError = null;
		editBusy = true;
		try {
			const parsed = courseUpdateSchema.safeParse({
				course_code: e_code,
				course_name: e_name,
				units: e_units,
				session_duration_hours: e_duration,
			});
			if (!parsed.success) {
				editError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await updateCourse(course.id, {
				course_code: parsed.data.course_code,
				course_name: parsed.data.course_name,
				units: parsed.data.units,
				session_duration_hours: parsed.data.session_duration_hours,
			});
			editOpen = false;
			await refreshAdminCourseDetail(course.id);
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			editError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			editBusy = false;
		}
	};

	const toggleActive = async () => {
		if (!course) return;
		try {
			await setCourseActive(course.id, !course.isActive);
			await refreshAdminCourseDetail(course.id);
			notifyEntityChanged('courses');
		} catch {
			// Surface via the detail state's actionError.
			adminCourseDetailState.actionError = 'Failed to update course status';
		}
	};

	const onArchive = async () => {
		if (!course || archiveBusy) return;
		archiveBusy = true;
		try {
			await archiveCourse(course.id);
			notifyEntityChanged('courses');
			await goto(Routes.ADMIN_COURSES);
		} catch (e: unknown) {
			adminCourseDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to archive course';
		} finally {
			archiveBusy = false;
		}
	};
</script>

<div class="page">
	<button class="link back" onclick={() => goto(Routes.ADMIN_COURSES)}>‹ All courses</button>

	{#if adminCourseDetailState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminCourseDetailState.error || !course}
		<section class="card">
			<p class="error">Could not load course: {adminCourseDetailState.error ?? 'Not found'}</p>
		</section>
	{:else}
		<header class="header">
			<div>
				<h1>{course.courseCode} — {course.courseName}</h1>
				<p class="muted">
					Units: {course.units} · Duration: {course.sessionDurationHours}h ·
					<span class="badge" class:inactive={!course.isActive}>
						{course.isActive ? 'Active' : 'Inactive'}
					</span>
				</p>
			</div>
			<div class="header-actions">
				<button class="btn btn-secondary" onclick={openEdit}>Edit</button>
				<button class="btn btn-secondary" onclick={toggleActive}>
					{course.isActive ? 'Deactivate' : 'Reactivate'}
				</button>
			</div>
		</header>

		{#if adminCourseDetailState.actionError}
			<section class="card"><p class="error" role="alert">{adminCourseDetailState.actionError}</p></section>
		{/if}

		<section class="card">
			<h2 class="card-title">Offerings ({offerings.length})</h2>
			<p class="muted">Program/year instances of this template. Schedule, professors, and roster live on each offering.</p>
			{#if offeringsLoading}
				<p class="muted">Loading offerings…</p>
			{:else if offeringsError}
				<p class="error">{offeringsError}</p>
			{:else if offerings.length === 0}
				<p class="empty">No offerings yet. Create one from the Offerings page.</p>
			{:else}
				<div class="table-wrap">
					<table>
						<thead>
							<tr>
								<th>Cohort</th>
								<th>Term</th>
								<th>Schedule</th>
								<th>Enrolled</th>
								<th>Status</th>
								<th><span class="sr">Actions</span></th>
							</tr>
						</thead>
						<tbody>
							{#each offerings as o (o.id)}
								<tr>
									<td>{[o.programCode ?? `Program ${o.programId}`, o.yearLevelLabel ?? `Year ${o.yearLevelId}`].join(' · ')}</td>
									<td>{o.semester} {o.academicYear}</td>
									<td>{o.scheduleDays} {o.scheduleStartTime.slice(0, 5)}–{o.scheduleEndTime.slice(0, 5)}</td>
									<td>{o.enrolledCount}</td>
									<td>
										<span class="badge" class:inactive={!o.isActive}>
											{o.isActive ? 'Active' : 'Inactive'}
										</span>
									</td>
									<td class="row-actions">
										<button class="link" onclick={() => goto(adminOffering(o.id))}>Open</button>
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
			<p class="muted">Archiving flips this template to inactive. Existing offerings keep working.</p>
			<button class="btn btn-danger" disabled={archiveBusy || !course.isActive} onclick={onArchive}>
				{archiveBusy ? 'Archiving…' : 'Archive course'}
			</button>
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
			use:trapFocus={{ onEscape: () => (editOpen = false) }}
		>
			<h2 id="course-edit-title" class="modal-title">Edit course</h2>
			{#if editError}
				<p class="error" role="alert">{editError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Code<input class="input" bind:value={e_code} /></label>
					<label>Units (1–6)<input class="input" inputmode="numeric" bind:value={e_units} /></label>
				</div>
				<label>Name<input class="input" bind:value={e_name} /></label>
				<label>Session duration, hours (0.5–8)<input class="input" inputmode="decimal" bind:value={e_duration} /></label>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (editOpen = false)}>Cancel</button>
				<button class="btn btn-primary" disabled={editBusy} onclick={submitEdit}>
					{editBusy ? 'Saving…' : 'Save'}
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

	.back {
		align-self: flex-start;
		font-size: 0.875rem;
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
