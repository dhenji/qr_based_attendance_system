<script lang="ts">
	import { onMount } from 'svelte';
	import DayPicker from '$lib/components/DayPicker.svelte';
	import { goToStep, setWizardYear, wizardState } from './store.svelte';
	import { getProgram } from '$lib/features/admin/programs/service';
	import { listCourses } from '$lib/features/admin/courses/service';
	import {
		createOffering,
		offeringTitle,
	} from '$lib/features/admin/offerings/service';
	import {
		offeringCreateSchema,
		windowsWithinDuration,
	} from '$lib/features/admin/offerings/schema';
	import type { AdminCourse, AdminOffering, ProgramDetail } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Wizard step 3: schedule offerings for the chosen program. The program is
	// locked in from step 1 and the year picker defaults to the first usable
	// year (a year with terms — a termless year cannot back offerings), so the
	// admin only answers “which course, which term, when and where”. The form
	// validates exactly like the Offerings page create modal (same schema,
	// same windows-within-duration guard, same coordinate parsing), and every
	// success notifies so the management pages stay fresh.
	//
	// After each save the form stays open for “create another”; Finish swaps
	// to a summary with links into the management pages.

	let program = $state<ProgramDetail | null>(null);
	let courses = $state<AdminCourse[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let f_year_id = $state('');
	let f_course_id = $state('');
	let f_semester = $state('');
	let f_academic_year = $state('');
	let f_sessions_per_week = $state('2');
	let f_semester_weeks = $state('18');
	let f_schedule_days = $state('');
	let f_start = $state('');
	let f_end = $state('');
	let f_classroom = $state('');
	let f_lat = $state('');
	let f_lng = $state('');
	let f_present = $state('5');
	let f_late = $state('10');

	let formError = $state<string | null>(null);
	let formBusy = $state(false);
	let lastSaved = $state<AdminOffering | null>(null);
	let created = $state<AdminOffering[]>([]);
	let done = $state(false);

	// Academic-year suggestion from the calendar (August start): editable,
	// just a starting value so the field is rarely blank.
	const defaultAcademicYear = (): string => {
		const now = new Date();
		const year = now.getFullYear();
		const start = now.getMonth() + 1 >= 8 ? year : year - 1;
		return `${start}-${start + 1}`;
	};

	const usableYears = $derived((program?.yearLevels ?? []).filter((y) => y.terms.length > 0));

	const pickedYear = $derived(
		usableYears.find((y) => String(y.id) === f_year_id) ??
			(program?.yearLevels ?? []).find((y) => String(y.id) === f_year_id) ??
			null
	);

	// Semester options come from the picked year's own term structure
	// (frontend-only read of data the year list already carries — no new
	// endpoint). A year with no terms falls back to free text, mirroring the
	// Offerings page modal.
	const semesterOptions = $derived(pickedYear?.terms ?? []);

	const selectedCourse = $derived(
		courses.find((c) => String(c.id) === f_course_id) ?? null
	);

	const windowBudget = $derived(
		selectedCourse === null
			? null
			: Math.round(selectedCourse.sessionDurationHours * 60)
	);

	onMount(async () => {
		if (wizardState.programId === null) {
			loadError = 'No program selected. Go back to Step 1 first.';
			loading = false;
			return;
		}
		try {
			const [detail, courseList] = await Promise.all([
				getProgram(wizardState.programId),
				listCourses({ page: 1, size: 100 }),
			]);
			program = detail;
			courses = courseList.items;
			const years = detail.yearLevels.filter((y) => y.terms.length > 0);
			const savedValid =
				wizardState.yearLevelId !== null &&
				years.some((y) => y.id === wizardState.yearLevelId);
			const first = savedValid
				? years.find((y) => y.id === wizardState.yearLevelId)
				: (years[0] ?? detail.yearLevels[0]);
			f_year_id = first ? String(first.id) : '';
			f_semester = first && first.terms.length > 0 ? first.terms[0].code : '';
			f_academic_year = defaultAcademicYear();
		} catch (e: unknown) {
			loadError = friendlyActionError(e, 'Could not load setup data.');
		} finally {
			loading = false;
		}
	});

	const changeYear = () => {
		f_semester = '';
		setWizardYear(f_year_id ? Number(f_year_id) : null);
		const year = pickedYear;
		if (year && year.terms.length > 0) {
			f_semester = year.terms[0].code;
		}
	};

	const parseCoord = (raw: string, label: string, min: number, max: number): number | undefined => {
		const trimmed = raw.trim();
		if (!trimmed) return undefined;
		const value = Number(trimmed);
		if (!Number.isFinite(value) || value < min || value > max) {
			throw new Error(`${label} must be a number between ${min} and ${max}`);
		}
		return value;
	};

	const resetIdentityFields = () => {
		f_course_id = '';
		f_schedule_days = '';
		f_start = '';
		f_end = '';
		f_classroom = '';
		f_lat = '';
		f_lng = '';
	};

	const submitForm = async () => {
		if (program === null) return;
		formError = null;
		lastSaved = null;
		formBusy = true;
		try {
			const parsed = offeringCreateSchema.safeParse({
				course_id: f_course_id,
				program_id: program.id,
				year_level_id: f_year_id,
				semester: f_semester,
				academic_year: f_academic_year,
				sessions_per_week: f_sessions_per_week,
				semester_weeks: f_semester_weeks,
				schedule_days: f_schedule_days,
				schedule_start_time: f_start,
				schedule_end_time: f_end,
				classroom_name: f_classroom || undefined,
				default_present_window_minutes: f_present,
				default_late_window_minutes: f_late,
			});
			if (!parsed.success) {
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			// Windows-sum guard (backend 422 windows_exceed_duration): present
			// + late must fit inside the selected course's session duration.
			const course = courses.find((c) => c.id === parsed.data.course_id);
			if (
				course &&
				!windowsWithinDuration(
					parsed.data.default_present_window_minutes,
					parsed.data.default_late_window_minutes,
					course.sessionDurationHours
				)
			) {
				formError = `Present + late windows exceed the ${course.courseCode} session duration (${course.sessionDurationHours * 60} min)`;
				return;
			}
			const lat = parseCoord(f_lat, 'Latitude', -90, 90);
			const lng = parseCoord(f_lng, 'Longitude', -180, 180);
			const saved = await createOffering({
				course_id: parsed.data.course_id,
				program_id: parsed.data.program_id,
				year_level_id: parsed.data.year_level_id,
				semester: parsed.data.semester,
				academic_year: parsed.data.academic_year,
				sessions_per_week: parsed.data.sessions_per_week,
				semester_weeks: parsed.data.semester_weeks,
				schedule_days: parsed.data.schedule_days,
				schedule_start_time: parsed.data.schedule_start_time,
				schedule_end_time: parsed.data.schedule_end_time,
				classroom_name: parsed.data.classroom_name || undefined,
				classroom_lat: lat,
				classroom_lng: lng,
				default_present_window_minutes: parsed.data.default_present_window_minutes,
				default_late_window_minutes: parsed.data.default_late_window_minutes,
			});
			lastSaved = saved;
			created = [saved, ...created];
			setWizardYear(saved.yearLevelId);
			notifyEntityChanged('offerings');
			resetIdentityFields();
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const savedTitle = (o: AdminOffering): string =>
		offeringTitle({
			...o,
			courseCode: o.courseCode ?? courses.find((c) => c.id === o.courseId)?.courseCode,
			courseName: o.courseName ?? courses.find((c) => c.id === o.courseId)?.courseName,
			programCode: o.programCode ?? program?.code,
			yearLevelLabel:
				o.yearLevelLabel ?? program?.yearLevels.find((y) => y.id === o.yearLevelId)?.label,
		});
</script>

<section class="card">
	<h2 class="step-title">Step 3 — Offerings</h2>
	{#if program}
		<p class="muted">
			Scheduling for <strong>{program.code} — {program.name}</strong>. Each offering
			instances one course template for one year level and term. Identity fields
			(course, program, year, semester, academic year) lock at creation.
			<button class="link" onclick={() => goToStep(1)}>Change program</button>
		</p>
	{:else}
		<p class="muted">Schedule course instances for a year level and term.</p>
	{/if}

	{#if loading}
		<p class="muted">Loading setup data…</p>
	{:else if loadError && !program}
		<p class="error" role="alert">{loadError}</p>
		<div class="nav-row">
			<button class="btn btn-secondary" onclick={() => goToStep(2)}>Back to Step 2</button>
			<span></span>
		</div>
	{:else if done}
		<div class="done-panel" role="status">
			<p class="done-title">Setup complete</p>
			<p class="muted">
				{#if created.length === 0}
					No offerings were created in this run. The program structure from Steps 1
					and 2 is saved and ready whenever you need it.
				{:else}
					Created {created.length} {created.length === 1 ? 'offering' : 'offerings'} for
					<strong>{program?.code}</strong>:
				{/if}
			</p>
			{#if created.length > 0}
				<ul class="rows">
					{#each created as o (o.id)}
						<li>{savedTitle(o)}</li>
					{/each}
				</ul>
			{/if}
			<div class="done-links">
				<a class="btn btn-secondary" href={Routes.ADMIN_PROGRAMS}>Programs</a>
				<a class="btn btn-secondary" href={Routes.ADMIN_COURSES}>Courses</a>
				<a class="btn btn-secondary" href={Routes.ADMIN_OFFERINGS}>Offerings</a>
			</div>
			<div class="nav-row">
				<button class="btn btn-secondary" onclick={() => (done = false)}>Create another</button>
				<a class="btn btn-primary" href={Routes.ADMIN_DASHBOARD}>Go to dashboard</a>
			</div>
		</div>
	{:else}
		{#if lastSaved}
			<p class="success" role="status">
				Saved: {savedTitle(lastSaved)}. The form is ready for the next one.
			</p>
		{/if}
		{#if created.length > 0}
			<p class="muted created-count">
				{created.length} {created.length === 1 ? 'offering' : 'offerings'} created this run.
			</p>
		{/if}

		{#if usableYears.length === 0}
			<p class="error" role="alert">
				This program has no year level with terms yet — offerings need a term to
				schedule against. Add one in Step 2 first.
			</p>
			<div class="nav-row">
				<button class="btn btn-secondary" onclick={() => goToStep(2)}>Back to Step 2</button>
				<span></span>
			</div>
		{:else if courses.length === 0}
			<p class="error" role="alert">
				No course templates exist yet — offerings instance a template. Add one in
				Step 2 first.
			</p>
			<div class="nav-row">
				<button class="btn btn-secondary" onclick={() => goToStep(2)}>Back to Step 2</button>
				<span></span>
			</div>
		{:else}
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Course
						<select class="input" bind:value={f_course_id} aria-label="Pick a course">
							<option value="">Pick a course…</option>
							{#each courses as c (c.id)}
								<option value={c.id}>{c.courseCode} — {c.courseName}</option>
							{/each}
						</select>
					</label>
					<label>Academic year<input class="input" bind:value={f_academic_year} placeholder="2025-2026" /></label>
				</div>
				<div class="grid2">
					<label>Year level
						<select class="input" bind:value={f_year_id} onchange={changeYear} aria-label="Pick a year level">
							{#each (program?.yearLevels ?? []) as y (y.id)}
								<option value={y.id} disabled={y.terms.length === 0}>
									{y.label}{y.terms.length === 0 ? ' (no terms)' : ''}
								</option>
							{/each}
						</select>
					</label>
					<label>Semester
						{#if semesterOptions.length > 0}
							<select class="input" bind:value={f_semester} aria-label="Pick a semester">
								<option value="">Pick a term…</option>
								{#each semesterOptions as t (t.code)}
									<option value={t.code}>{t.label}</option>
								{/each}
							</select>
						{:else}
							<input class="input" bind:value={f_semester} placeholder="e.g. 1st Sem" />
						{/if}
					</label>
				</div>
				<DayPicker bind:value={f_schedule_days} />
				<div class="grid2">
					<label>Sessions / week<input class="input" inputmode="numeric" bind:value={f_sessions_per_week} /></label>
					<label>Semester weeks<input class="input" inputmode="numeric" bind:value={f_semester_weeks} /></label>
				</div>
				<div class="grid2">
					<label>Start time<input class="input" type="time" bind:value={f_start} /></label>
					<label>End time<input class="input" type="time" bind:value={f_end} /></label>
				</div>
				<label>Classroom (optional)<input class="input" bind:value={f_classroom} placeholder="Room 301" /></label>
				<div class="grid2">
					<label>Latitude (optional)<input class="input" inputmode="decimal" bind:value={f_lat} placeholder="14.5995" /></label>
					<label>Longitude (optional)<input class="input" inputmode="decimal" bind:value={f_lng} placeholder="120.9842" /></label>
				</div>
				<div class="grid2">
					<label>Present window, min<input class="input" inputmode="numeric" bind:value={f_present} /></label>
					<label>Late window, min<input class="input" inputmode="numeric" bind:value={f_late} /></label>
				</div>
				{#if windowBudget !== null}
					<p class="hint">
						{selectedCourse?.courseCode} sessions run {windowBudget} min — present + late must fit inside that.
					</p>
				{:else}
					<p class="hint">Pick a course to see its session budget for the attendance windows.</p>
				{/if}
			</div>
			<div class="nav-row">
				<button class="btn btn-secondary" onclick={() => goToStep(2)}>Back</button>
				<div class="nav-end">
					<button
						class="btn btn-primary"
						data-testid="wizard-save-offering"
						disabled={formBusy}
						onclick={() => void submitForm()}
					>
						{formBusy ? 'Saving…' : created.length > 0 ? 'Save another offering' : 'Save offering'}
					</button>
					<button
						class="btn btn-secondary"
						disabled={formBusy}
						onclick={() => (done = true)}
					>
						Finish
					</button>
				</div>
			</div>
		{/if}
	{/if}
</section>

<style>
	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: var(--shadow-sm);
		font-family: system-ui, sans-serif;
	}

	.step-title {
		margin: 0 0 0.375rem;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--text);
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0 0 1.25rem;
	}

	.created-count {
		margin: 0 0 1rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.success {
		color: var(--success);
		background: var(--success-bg);
		border-radius: 8px;
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
		font-weight: 600;
		margin: 0 0 1rem;
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

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.nav-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-top: 1.5rem;
		flex-wrap: wrap;
	}

	.nav-end {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.done-panel {
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 1.25rem;
		background: var(--bg-muted);
	}

	.done-title {
		margin: 0 0 0.375rem;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.done-panel .muted {
		margin-bottom: 1rem;
	}

	.rows {
		list-style: none;
		margin: 0 0 1rem;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.rows li {
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
		font-size: 0.875rem;
		color: var(--text-strong);
		background: var(--bg-card);
	}

	.done-links {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-bottom: 0.5rem;
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
		text-decoration: none;
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

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
