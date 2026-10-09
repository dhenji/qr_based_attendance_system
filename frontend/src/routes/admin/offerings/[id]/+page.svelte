<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		adminOfferingDetailState,
		assignOfferingProfessor,
		bulkEnrollOffering,
		endOfferingAssignment,
		initAdminOfferingDetail,
		loadOfferingAssignments,
		loadOfferingRoster,
		refreshAdminOfferingDetail,
		updateAdminOffering,
	} from '$lib/features/admin/offerings/store.svelte';
	import {
		archiveOffering,
		setOfferingActive,
	} from '$lib/features/admin/offerings/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import { listPrograms, listYearLevels } from '$lib/features/admin/programs/service';
	import { listProfessors } from '$lib/features/admin/service';
	import {
		assignmentCreateSchema,
		offeringUpdateSchema,
		windowsWithinDuration,
	} from '$lib/features/admin/offerings/schema';
	import { csvFileSchema } from '$lib/features/admin/schema';
	import type {
		AdminBulkEnrollResult,
		AdminCourse,
		AdminProfessor,
		Program,
		YearLevel,
	} from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Offering Detail (wireframe 4.5d, admin-manual §2.4): schedule, classroom
	// GPS, weeks, and default windows live here — the course template page
	// only shows units/duration. Tabs:
	// - Overview: identity + schedule + classroom + windows.
	// - Professors: assignments with effective dating (D7-D9); ending sets
	//   effective_to=today, history is never rewritten.
	// - Enrolled: roster with section filter + bulk CSV enroll of EXISTING
	//   students (creating new students stays on /admin/students/import).
	// - Settings: mutable fields only — course/program/year/semester/
	//   academic_year are identity and not patchable (contract).

	const offeringId = $derived(Number(page.params.id));
	const offering = $derived(adminOfferingDetailState.offering);

	let tab = $state<'overview' | 'professors' | 'enrolled' | 'settings'>('overview');

	let course = $state<AdminCourse | null>(null);
	let programCode = $state<string | null>(null);
	let yearLabel = $state<string | null>(null);
	let professorIndex = $state<Map<number, AdminProfessor>>(new Map());

	// Settings form.
	let s_sessions = $state('');
	let s_weeks = $state('');
	let s_days = $state('');
	let s_start = $state('');
	let s_end = $state('');
	let s_classroom = $state('');
	let s_lat = $state('');
	let s_lng = $state('');
	let s_present = $state('');
	let s_late = $state('');
	let settingsError = $state<string | null>(null);
	let settingsBusy = $state(false);
	let archiveBusy = $state(false);

	// Assign-professor form.
	let assignOpen = $state(false);
	let a_professor_id = $state('');
	let a_primary = $state(false);
	let a_from = $state('');
	let a_to = $state('');
	let a_semester = $state('');
	let assignError = $state<string | null>(null);
	let assignBusy = $state(false);

	// Roster + bulk enroll.
	let sectionFilter = $state('');
	let bulkFile = $state<File | null>(null);
	let bulkBusy = $state(false);
	let bulkResult = $state<AdminBulkEnrollResult | null>(null);

	onMount(async () => {
		if (!Number.isFinite(offeringId) || offeringId <= 0) return;
		await initAdminOfferingDetail(offeringId);
		const o = adminOfferingDetailState.offering;
		if (!o) return;
		await Promise.all([
			loadOfferingAssignments(offeringId),
			loadOfferingRoster(offeringId),
			resolveContext(o.courseId, o.programId, o.yearLevelId),
		]);
		fillSettings();
	});

	const resolveContext = async (courseId: number, programId: number, yearId: number) => {
		try {
			course = (await listCourses({ page: 1, size: 100 })).items.find((c) => c.id === courseId) ?? null;
		} catch {
			course = null;
		}
		try {
			const programs: Program[] = (await listPrograms({ page: 1, size: 50 })).items;
			programCode = programs.find((p) => p.id === programId)?.code ?? null;
		} catch {
			programCode = null;
		}
		try {
			const years: YearLevel[] = await listYearLevels(programId);
			yearLabel = years.find((y) => y.id === yearId)?.label ?? null;
		} catch {
			yearLabel = null;
		}
		try {
			const professors = (await listProfessors({ page: 1, size: 100 })).items;
			professorIndex = new Map(professors.map((p) => [p.id, p]));
		} catch {
			professorIndex = new Map();
		}
	};

	const professorName = (id: number): string => {
		const p = professorIndex.get(id);
		return p ? [p.firstName, p.middleName, p.lastName].filter(Boolean).join(' ') : `Professor ${id}`;
	};

	const professorEmail = (id: number): string => professorIndex.get(id)?.email ?? '';

	const fillSettings = () => {
		const o = adminOfferingDetailState.offering;
		if (!o) return;
		settingsError = null;
		s_sessions = String(o.sessionsPerWeek);
		s_weeks = String(o.semesterWeeks);
		s_days = o.scheduleDays;
		s_start = o.scheduleStartTime.slice(0, 5);
		s_end = o.scheduleEndTime.slice(0, 5);
		s_classroom = o.classroomName ?? '';
		s_lat = o.classroomLat !== undefined ? String(o.classroomLat) : '';
		s_lng = o.classroomLng !== undefined ? String(o.classroomLng) : '';
		s_present = String(o.presentWindowMinutes);
		s_late = String(o.lateWindowMinutes);
	};

	const toggleActive = async () => {
		if (!offering) return;
		try {
			await setOfferingActive(offering.id, !offering.isActive);
			await refreshAdminOfferingDetail(offering.id);
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to update offering status';
		}
	};

	const onArchive = async () => {
		if (!offering || archiveBusy) return;
		archiveBusy = true;
		try {
			await archiveOffering(offering.id);
			await goto(Routes.ADMIN_OFFERINGS);
		} catch (e: unknown) {
			adminOfferingDetailState.actionError =
				e instanceof Error && e.message ? e.message : 'Failed to archive offering';
		} finally {
			archiveBusy = false;
		}
	};

	const parseCoord = (raw: string, label: string, min: number, max: number): number | null | undefined => {
		// Empty clears the stored coordinate (nullable column); a value must
		// parse inside range. `undefined` means "leave untouched".
		if (!raw.trim()) return offering?.classroomLat !== undefined || offering?.classroomLng !== undefined ? null : undefined;
		const value = Number(raw.trim());
		if (!Number.isFinite(value) || value < min || value > max) {
			throw new Error(`${label} must be a number between ${min} and ${max}`);
		}
		return value;
	};

	const submitSettings = async () => {
		if (!offering) return;
		settingsError = null;
		settingsBusy = true;
		try {
			// Merge single-sided time edits against the stored half first: the
			// schema (like the backend body validator) only sees sent fields,
			// so a lone moved start past the stored end is caught here before
			// the request (backend 422 invalid_schedule_window on merge).
			const mergedStart = s_start.trim() || offering.scheduleStartTime.slice(0, 5);
			const mergedEnd = s_end.trim() || offering.scheduleEndTime.slice(0, 5);
			if (mergedEnd <= mergedStart) {
				settingsError = 'End time must be after start time';
				return;
			}
			const parsed = offeringUpdateSchema.safeParse({
				sessions_per_week: s_sessions,
				semester_weeks: s_weeks,
				schedule_days: s_days,
				schedule_start_time: s_start.trim() || undefined,
				schedule_end_time: s_end.trim() || undefined,
				classroom_name: s_classroom,
			});
			if (!parsed.success) {
				settingsError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			const present = Number(s_present);
			const late = Number(s_late);
			if (!Number.isInteger(present) || present < 1 || present > 480 || !Number.isInteger(late) || late < 1 || late > 480) {
				settingsError = 'Windows must be whole minutes between 1 and 480';
				return;
			}
			if (course && !windowsWithinDuration(present, late, course.sessionDurationHours)) {
				settingsError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			await updateAdminOffering(offering.id, {
				sessions_per_week: parsed.data.sessions_per_week,
				semester_weeks: parsed.data.semester_weeks,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: s_classroom.trim() ? s_classroom.trim() : null,
				classroom_lat: parseCoord(s_lat, 'Latitude', -90, 90),
				classroom_lng: parseCoord(s_lng, 'Longitude', -180, 180),
				default_present_window_minutes: present,
				default_late_window_minutes: late,
			});
			fillSettings();
		} catch (e: unknown) {
			settingsError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			settingsBusy = false;
		}
	};

	const openAssign = () => {
		assignError = null;
		a_professor_id = '';
		a_primary = false;
		a_from = new Date().toISOString().slice(0, 10);
		a_to = '';
		a_semester = offering?.semester ?? '';
		assignOpen = true;
	};

	const submitAssign = async () => {
		if (!offering) return;
		assignError = null;
		assignBusy = true;
		try {
			const parsed = assignmentCreateSchema.safeParse({
				professor_id: a_professor_id,
				is_primary: a_primary,
				effective_from: a_from,
				effective_to: a_to || undefined,
				semester: a_semester,
			});
			if (!parsed.success) {
				assignError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await assignOfferingProfessor(offering.id, {
				professor_id: parsed.data.professor_id,
				is_primary: parsed.data.is_primary,
				effective_from: parsed.data.effective_from,
				effective_to: parsed.data.effective_to || undefined,
				semester: parsed.data.semester,
			});
			assignOpen = false;
		} catch (e: unknown) {
			assignError = e instanceof Error && e.message ? e.message : 'Assign failed. Please try again.';
		} finally {
			assignBusy = false;
		}
	};

	const endRow = async (professorId: number) => {
		if (!offering) return;
		try {
			await endOfferingAssignment(offering.id, professorId);
		} catch {
			// Surfaced via the detail state's actionError.
		}
	};

	const applySection = () => {
		if (offering) loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, 1);
	};

	const onBulkFile = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const picked = input.files?.[0] ?? null;
		bulkFile = picked;
		bulkResult = null;
		if (picked) {
			const parsed = csvFileSchema.safeParse(picked);
			if (!parsed.success) {
				adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
				bulkFile = null;
				input.value = '';
			}
		}
	};

	const submitBulk = async () => {
		if (!offering || !bulkFile || bulkBusy) return;
		const parsed = csvFileSchema.safeParse(bulkFile);
		if (!parsed.success) {
			adminOfferingDetailState.actionError = parsed.error.issues[0]?.message ?? 'Invalid CSV file.';
			return;
		}
		bulkBusy = true;
		try {
			bulkResult = await bulkEnrollOffering(offering.id, bulkFile);
		} catch {
			// Surfaced via the detail state's actionError.
		} finally {
			bulkBusy = false;
		}
	};

	const rosterTotalPages = $derived(
		Math.max(1, Math.ceil(adminOfferingDetailState.rosterTotal / 20))
	);
</script>

<div class="page">
	<button class="link back" onclick={() => goto(Routes.ADMIN_OFFERINGS)}>‹ All offerings</button>

	{#if adminOfferingDetailState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
	{:else if adminOfferingDetailState.error || !offering}
		<section class="card">
			<p class="error">Could not load offering: {adminOfferingDetailState.error ?? 'Not found'}</p>
		</section>
	{:else}
		<header class="header">
			<div>
				<h1>{course ? `${course.courseCode} — ${course.courseName}` : `Offering ${offering.id}`}</h1>
				<p class="muted">
					{[programCode ?? `Program ${offering.programId}`, yearLabel ?? `Year ${offering.yearLevelId}`].join(' · ')}
					· {offering.semester} {offering.academicYear} ·
					<span class="badge" class:inactive={!offering.isActive}>
						{offering.isActive ? 'Active' : 'Inactive'}
					</span>
				</p>
			</div>
			<div class="header-actions">
				<button class="btn btn-secondary" onclick={toggleActive}>
					{offering.isActive ? 'Deactivate' : 'Reactivate'}
				</button>
			</div>
		</header>

		{#if adminOfferingDetailState.actionError}
			<section class="card"><p class="error" role="alert">{adminOfferingDetailState.actionError}</p></section>
		{/if}

		<nav class="tabs" aria-label="Offering sections">
			<button class:active={tab === 'overview'} onclick={() => (tab = 'overview')}>Overview</button>
			<button class:active={tab === 'professors'} onclick={() => (tab = 'professors')}>Professors</button>
			<button class:active={tab === 'enrolled'} onclick={() => (tab = 'enrolled')}>Enrolled</button>
			<button class:active={tab === 'settings'} onclick={() => (tab = 'settings')}>Settings</button>
		</nav>

		{#if tab === 'overview'}
			<section class="card">
				<dl class="facts">
					<div><dt>Schedule</dt><dd>{offering.scheduleDays} {offering.scheduleStartTime.slice(0, 5)}–{offering.scheduleEndTime.slice(0, 5)}</dd></div>
					<div><dt>Meetings</dt><dd>{offering.sessionsPerWeek} / week · {offering.semesterWeeks} weeks</dd></div>
					<div><dt>Classroom</dt><dd>{offering.classroomName ?? '—'}</dd></div>
					{#if offering.classroomLat !== undefined && offering.classroomLng !== undefined}
						<div><dt>Geofence center</dt><dd>{offering.classroomLat}, {offering.classroomLng}</dd></div>
					{/if}
					<div><dt>Present window</dt><dd>{offering.presentWindowMinutes} min</dd></div>
					<div><dt>Late window</dt><dd>{offering.lateWindowMinutes} min</dd></div>
					<div><dt>Enrolled</dt><dd>{offering.enrolledCount}</dd></div>
				</dl>
				{#if course}
					<p class="muted">Template: {course.courseCode} · {course.units} units · {course.sessionDurationHours}h sessions</p>
				{/if}
			</section>
		{:else if tab === 'professors'}
			<section class="card">
				<div class="row-head">
					<h2 class="card-title">Assignments</h2>
					<button class="btn btn-primary" onclick={openAssign}>Assign professor</button>
				</div>
				{#if adminOfferingDetailState.assignmentsLoading}
					<p class="muted">Loading assignments…</p>
				{:else if adminOfferingDetailState.assignments.length === 0}
					<p class="empty">No professors assigned yet. Any professor with an active assignment may open sessions for this offering.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Professor</th>
									<th>Role</th>
									<th>Effective</th>
									<th>Semester</th>
									<th><span class="sr">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each adminOfferingDetailState.assignments as a (a.professorId)}
									<tr>
										<td>
											<div class="strong">{professorName(a.professorId)}</div>
											<div class="muted small">{professorEmail(a.professorId)}</div>
										</td>
										<td>
											<span class="badge" class:inactive={!a.isPrimary}>
												{a.isPrimary ? 'Primary' : 'Assistant'}
											</span>
										</td>
										<td>{a.effectiveFrom} → {a.effectiveTo ?? 'ongoing'}</td>
										<td>{a.semester}</td>
										<td class="row-actions">
											{#if !a.effectiveTo}
												<button class="link" onclick={() => endRow(a.professorId)}>End</button>
											{:else}
												<span class="muted small">ended</span>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="hint">Mid-term replacement: end the old assignment, then create the new one — history is never rewritten.</p>
				{/if}
			</section>
		{:else if tab === 'enrolled'}
			<section class="card">
				<div class="row-head">
					<h2 class="card-title">Roster ({adminOfferingDetailState.rosterTotal})</h2>
				</div>
				<div class="filters">
					<input
						class="input"
						placeholder="Section (e.g. A)"
						aria-label="Section filter"
						bind:value={sectionFilter}
						onkeydown={(e) => {
							if (e.key === 'Enter') applySection();
						}}
					/>
					<button class="btn btn-secondary" onclick={applySection}>Apply</button>
				</div>
				{#if adminOfferingDetailState.rosterLoading}
					<p class="muted">Loading roster…</p>
				{:else if adminOfferingDetailState.roster.length === 0}
					<p class="empty">No students enrolled yet.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Student ID</th>
									<th>Name</th>
									<th>Section</th>
									<th>Enrolled</th>
								</tr>
							</thead>
							<tbody>
								{#each adminOfferingDetailState.roster as r (r.studentId)}
									<tr>
										<td class="strong">{r.studentId}</td>
										<td>{r.name}</td>
										<td>{r.section ?? '—'}</td>
										<td>{r.enrolledAt.slice(0, 10)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="pager">
						<button
							class="btn btn-secondary"
							disabled={adminOfferingDetailState.rosterPage <= 1}
							onclick={() => offering && loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, adminOfferingDetailState.rosterPage - 1)}
						>
							‹ Prev
						</button>
						<span class="muted">Page {adminOfferingDetailState.rosterPage} of {rosterTotalPages}</span>
						<button
							class="btn btn-secondary"
							disabled={adminOfferingDetailState.rosterPage >= rosterTotalPages}
							onclick={() => offering && loadOfferingRoster(offering.id, sectionFilter.trim() || undefined, adminOfferingDetailState.rosterPage + 1)}
						>
							Next ›
						</button>
					</div>
				{/if}
			</section>

			<section class="card">
				<h2 class="card-title">Bulk enroll</h2>
				<p class="muted">CSV of EXISTING students: student_id, first_name, middle_name, last_name, email, program_code, year_level, section. Rows that fail (unknown id, email mismatch, wrong program) are reported per line, not applied.</p>
				<div class="filters">
					<input class="input" type="file" accept=".csv,text/csv" onchange={onBulkFile} aria-label="Roster CSV file" />
					<button class="btn btn-primary" disabled={!bulkFile || bulkBusy} onclick={submitBulk}>
						{bulkBusy ? 'Uploading…' : 'Upload'}
					</button>
				</div>
				{#if bulkResult}
					<p class="muted" role="status">
						Enrolled {bulkResult.enrolled} · skipped {bulkResult.skipped}
						{#if bulkResult.errors.length > 0}
							· {bulkResult.errors.length} error{bulkResult.errors.length === 1 ? '' : 's'}:
						{/if}
					</p>
					{#if bulkResult.errors.length > 0}
						<ul class="error-list">
							{#each bulkResult.errors as err (err.line)}
								<li>Line {err.line}: {err.reason}</li>
							{/each}
						</ul>
					{/if}
				{/if}
			</section>
		{:else}
			<section class="card">
				<h2 class="card-title">Offering settings</h2>
				<p class="muted">Mutable fields only. Course, program, year, semester, and academic year are identity — they cannot be changed after creation.</p>
				{#if settingsError}
					<p class="error" role="alert">{settingsError}</p>
				{/if}
				<div class="form">
					<div class="grid2">
						<label>Sessions / week<input class="input" inputmode="numeric" bind:value={s_sessions} /></label>
						<label>Semester weeks<input class="input" inputmode="numeric" bind:value={s_weeks} /></label>
					</div>
					<label>Schedule days<input class="input" bind:value={s_days} placeholder="MWF" /></label>
					<div class="grid2">
						<label>Start time<input class="input" type="time" bind:value={s_start} /></label>
						<label>End time<input class="input" type="time" bind:value={s_end} /></label>
					</div>
					<label>Classroom<input class="input" bind:value={s_classroom} placeholder="Lab 101" /></label>
					<div class="grid2">
						<label>Latitude<input class="input" inputmode="decimal" bind:value={s_lat} /></label>
						<label>Longitude<input class="input" inputmode="decimal" bind:value={s_lng} /></label>
					</div>
					<div class="grid2">
						<label>Present window, min<input class="input" inputmode="numeric" bind:value={s_present} /></label>
						<label>Late window, min<input class="input" inputmode="numeric" bind:value={s_late} /></label>
					</div>
					<p class="hint">Clearing the classroom name removes it; clearing a coordinate clears it. Present + late windows must fit the course session duration.</p>
				</div>
				<div class="modal-actions">
					<button class="btn btn-ghost" onclick={fillSettings}>Reset</button>
					<button class="btn btn-primary" disabled={settingsBusy} onclick={submitSettings}>
						{settingsBusy ? 'Saving…' : 'Save'}
					</button>
				</div>
			</section>

			<section class="card danger">
				<h2 class="card-title">Danger zone</h2>
				<p class="muted">Archiving flips this offering to inactive. Sessions history is kept.</p>
				<button class="btn btn-danger" disabled={archiveBusy || !offering.isActive} onclick={onArchive}>
					{archiveBusy ? 'Archiving…' : 'Archive offering'}
				</button>
			</section>
		{/if}
	{/if}
</div>

{#if assignOpen && offering}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="assign-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (assignOpen = false) }}
		>
			<h2 id="assign-title" class="modal-title">Assign professor</h2>
			{#if assignError}
				<p class="error" role="alert">{assignError}</p>
			{/if}
			<div class="form">
				<label>Professor
					<select class="input" bind:value={a_professor_id}>
						<option value="">Pick a professor…</option>
						{#each [...professorIndex.values()] as p (p.id)}
							<option value={p.id}>{p.firstName} {p.lastName} — {p.email}</option>
						{/each}
					</select>
				</label>
				<label class="check">
					<input type="checkbox" bind:checked={a_primary} /> Primary (uncheck for assistant)
				</label>
				<div class="grid2">
					<label>Effective from<input class="input" type="date" bind:value={a_from} /></label>
					<label>Effective to (optional)<input class="input" type="date" bind:value={a_to} /></label>
				</div>
				<label>Semester<input class="input" bind:value={a_semester} placeholder="1st Sem" /></label>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (assignOpen = false)}>Cancel</button>
				<button class="btn btn-primary" disabled={assignBusy} onclick={submitAssign}>
					{assignBusy ? 'Saving…' : 'Assign'}
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

	.muted.small {
		font-size: 0.75rem;
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

	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid var(--border);
	}

	.tabs button {
		background: none;
		border: none;
		padding: 0.625rem 1rem;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--text-muted);
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -2px;
	}

	.tabs button:hover {
		color: var(--text-strong);
	}

	.tabs button.active {
		color: var(--brand);
		border-bottom-color: var(--brand);
	}

	.row-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}

	.row-head .card-title {
		margin: 0;
	}

	.facts {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem 1.5rem;
		margin: 0 0 1rem;
	}

	.facts div {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.facts dt {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.facts dd {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-strong);
		font-weight: 600;
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

	.strong {
		font-weight: 700;
	}

	td .strong {
		font-size: 0.875rem;
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

	.error-list {
		color: var(--danger);
		font-size: 0.8125rem;
		margin: 0.5rem 0 0;
		padding-left: 1.25rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 1rem 0 0;
	}

	.filters {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		margin-bottom: 1rem;
	}

	.pager {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1rem;
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

	.form label.check {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
	}

	.grid2 {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.875rem;
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

		.grid2,
		.facts {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
