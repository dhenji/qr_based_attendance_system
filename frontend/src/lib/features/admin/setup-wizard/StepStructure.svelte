<script lang="ts">
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { goToStep, setStructureReady, wizardState } from './store.svelte';
	import {
		createYearLevel,
		getProgram,
	} from '$lib/features/admin/programs/service';
	import { yearLevelCreateSchema } from '$lib/features/admin/programs/schema';
	import { createCourse, listCourses } from '$lib/features/admin/courses/service';
	import { courseCreateSchema } from '$lib/features/admin/courses/schema';
	import { nextTermRow } from '$lib/shared/constants/terms';
import TermRowsEditor from '$lib/features/admin/programs/components/TermRowsEditor.svelte';
	import { yearLabel } from '$lib/shared/utils/format';
	import type { AdminCourse, ProgramDetail } from '$lib/shared/types';
	import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Wizard step 2: build the structure an offering needs. Two independent
	// checklists over the program chosen in step 1:
	//
	// - year levels (with at least one term each — a termless year cannot back
	//   offerings, same rule as the program detail page), created with the
	//   same schema + service as the detail page;
	// - course templates (standalone reusable rows, no program link — the
	//   link to a program/year only exists once an offering instances them),
	//   created with the same schema + service as the Courses page.
	//
	// Continue unlocks when at least one usable year and one course exist.

	type TermRow = { code: string; label: string };

	let program = $state<ProgramDetail | null>(null);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let courses = $state<AdminCourse[]>([]);
	let coursesLoading = $state(true);
	let coursesError = $state<string | null>(null);

	let yearOpen = $state(false);
	let y_number = $state('');
	let y_terms = $state<TermRow[]>([]);
	let yearError = $state<string | null>(null);
	let yearBusy = $state(false);

	let courseOpen = $state(false);
	let c_code = $state('');
	let c_name = $state('');
	let c_units = $state('');
	let c_duration = $state('');
	let courseError = $state<string | null>(null);
	let courseBusy = $state(false);

	const reloadProgram = async () => {
		if (wizardState.programId === null) return;
		try {
			program = await getProgram(wizardState.programId);
		} catch (e: unknown) {
			loadError = friendlyActionError(e, 'Could not load the program.');
		}
	};

	const reloadCourses = async () => {
		try {
			courses = (await listCourses({ page: 1, size: 100 })).items;
		} catch (e: unknown) {
			coursesError = friendlyActionError(e, 'Could not load courses.');
		}
	};

	onMount(async () => {
		if (wizardState.programId === null) {
			loadError = 'No program selected. Go back to Step 1 first.';
			loading = false;
			coursesLoading = false;
			return;
		}
		await Promise.all([reloadProgram(), reloadCourses()]);
		loading = false;
		coursesLoading = false;
	});

	// Years still available: 1..total_years minus created ones. Hiding the
	// taken ones avoids the backend 409 year_number_exists (same approach as
	// the program detail page).
	const availableYears = $derived.by(() => {
		if (!program) return [] as number[];
		const taken = new Set(program.yearLevels.map((y) => y.yearNumber));
		return Array.from({ length: program.totalYears }, (_, i) => i + 1).filter(
			(n) => !taken.has(n)
		);
	});

	const usableYears = $derived((program?.yearLevels ?? []).filter((y) => y.terms.length > 0));

	const readyYears = $derived(usableYears.length > 0);
	const readyCourses = $derived(courses.length > 0);
	const readyAll = $derived(readyYears && readyCourses);

	// Report the checklist to the wizard store so the shell can gate step
	// 3 on it (and resume can trust the persisted flag).
	$effect(() => {
		setStructureReady(readyAll);
	});

	const termsText = (terms: { label: string }[]): string =>
		terms.length > 0 ? terms.map((t) => t.label).join(' · ') : 'No terms yet';


	const openYear = () => {
		yearError = null;
		y_number = String(availableYears[0] ?? '');
		y_terms = [nextTermRow([])];
		yearOpen = true;
	};

	const submitYear = async () => {
		if (!program) return;
		yearError = null;
		yearBusy = true;
		try {
			const parsed = yearLevelCreateSchema.safeParse({
				year_number: y_number,
				label: yearLabel(Number(y_number)),
				terms: y_terms,
			});
			if (!parsed.success) {
				yearError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await createYearLevel(program.id, {
				year_number: parsed.data.year_number,
				label: parsed.data.label,
				term_structure: { terms: parsed.data.terms },
			});
			yearOpen = false;
			await reloadProgram();
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			yearError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			yearBusy = false;
		}
	};

	const openCourse = () => {
		courseError = null;
		c_code = '';
		c_name = '';
		c_units = '';
		c_duration = '';
		courseOpen = true;
	};

	const submitCourse = async () => {
		courseError = null;
		courseBusy = true;
		try {
			const parsed = courseCreateSchema.safeParse({
				course_code: c_code,
				course_name: c_name,
				units: c_units,
				session_duration_hours: c_duration,
			});
			if (!parsed.success) {
				courseError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			await createCourse({
				course_code: parsed.data.course_code,
				course_name: parsed.data.course_name,
				units: parsed.data.units,
				session_duration_hours: parsed.data.session_duration_hours,
			});
			courseOpen = false;
			await reloadCourses();
			notifyEntityChanged('courses');
		} catch (e: unknown) {
			courseError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			courseBusy = false;
		}
	};
</script>

<section class="card">
	<h2 class="step-title">Step 2 — Structure</h2>
	{#if program}
		<p class="muted">
			Building on <strong>{program.code} — {program.name}</strong>. An offering needs
			two things: a year level with terms (the “when” in the school calendar) and a
			course template (the “what”). Add any that are still missing.
			<button class="link" onclick={() => goToStep(1)}>Change program</button>
		</p>
	{:else}
		<p class="muted">Year levels and course templates for the chosen program.</p>
	{/if}

	{#if loading}
		<p class="muted">Loading structure…</p>
	{:else if loadError && !program}
		<p class="error" role="alert">{loadError}</p>
		<div class="nav-row">
			<button class="btn btn-secondary" onclick={() => goToStep(1)}>Back to Step 1</button>
			<span></span>
		</div>
	{:else}
		<div class="checklist" role="status" aria-live="polite">
			<span class="check" class:done={readyYears}>
				<AppIcon name={readyYears ? 'check' : 'alert'} size={16} />
				{readyYears ? `${usableYears.length} usable year levels` : 'No usable year level yet'}
			</span>
			<span class="check" class:done={readyCourses}>
				<AppIcon name={readyCourses ? 'check' : 'alert'} size={16} />
				{readyCourses ? `${courses.length} course templates` : 'No course templates yet'}
			</span>
		</div>

		<div class="two-col">
			<div class="panel">
				<div class="panel-head">
					<h3>Year levels</h3>
					<button
						class="btn btn-secondary btn-sm"
						disabled={availableYears.length === 0}
						title={availableYears.length === 0 ? 'All years for this program already exist' : undefined}
						onclick={openYear}
					>
						<AppIcon name="plus" size={16} />
						Add year
					</button>
				</div>
				{#if (program?.yearLevels ?? []).length === 0}
					<p class="empty">No year levels yet. Add the first one — terms come with it.</p>
				{:else}
					<ul class="rows">
						{#each (program?.yearLevels ?? []) as y (y.id)}
							<li class:termless={y.terms.length === 0}>
								<span class="row-main">{y.label}</span>
								<span class="row-sub">{termsText(y.terms)}</span>
							</li>
						{/each}
					</ul>
					<p class="hint">A year with no terms cannot back offerings yet — add terms on the program detail page.</p>
				{/if}

				{#if yearOpen}
					{#if yearError}
						<p class="error" role="alert">{yearError}</p>
					{/if}
					<div class="form">
						<label>Year number
							<select class="input" bind:value={y_number} aria-label="Year number">
								{#each availableYears as n (n)}
									<option value={n}>{yearLabel(n)}</option>
								{/each}
							</select>
						</label>
						<div class="terms">
							<span class="form-label">Terms in this year</span>
							<TermRowsEditor
								bind:rows={y_terms}
								busy={yearBusy}
								lockCodeForExisting={false}
								emptyMessage="No terms yet. Add one below, or save empty — a termless year cannot back offerings yet."
							/>
						</div>
						<div class="form-actions">
							<button class="btn btn-ghost" onclick={() => (yearOpen = false)}>Cancel</button>
							<button
								class="btn btn-primary"
								disabled={yearBusy || !y_number}
								onclick={() => void submitYear()}
							>
								{yearBusy ? 'Saving…' : 'Save year'}
							</button>
						</div>
					</div>
				{/if}
			</div>

			<div class="panel">
				<div class="panel-head">
					<h3>Course templates</h3>
					<button class="btn btn-secondary btn-sm" onclick={openCourse}>
						<AppIcon name="plus" size={16} />
						Add course
					</button>
				</div>
				{#if coursesLoading}
					<p class="muted">Loading courses…</p>
				{:else if coursesError}
					<p class="error" role="alert">{coursesError}</p>
				{:else if courses.length === 0}
					<p class="empty">No course templates yet. Add the first one — scheduling is set later, on the offering.</p>
				{:else}
					<ul class="rows">
						{#each courses.slice(0, 8) as c (c.id)}
							<li>
								<span class="row-main">{c.courseCode}</span>
								<span class="row-sub">{c.courseName} · {c.units}u · {c.sessionDurationHours}h</span>
							</li>
						{/each}
					</ul>
					{#if courses.length > 8}
						<p class="hint">Showing 8 of {courses.length} — the full list lives on the Courses page.</p>
					{/if}
				{/if}

				{#if courseOpen}
					{#if courseError}
						<p class="error" role="alert">{courseError}</p>
					{/if}
					<div class="form">
						<div class="grid2">
							<label>Code<input class="input" bind:value={c_code} placeholder="CS101" /></label>
							<label>Units<input class="input" inputmode="numeric" bind:value={c_units} placeholder="3" /></label>
						</div>
						<label>Name<input class="input" bind:value={c_name} placeholder="Intro to Computing" /></label>
						<label>Session hours<input class="input" inputmode="decimal" bind:value={c_duration} placeholder="1.5" /></label>
						<div class="form-actions">
							<button class="btn btn-ghost" onclick={() => (courseOpen = false)}>Cancel</button>
							<button
								class="btn btn-primary"
								disabled={courseBusy}
								onclick={() => void submitCourse()}
							>
								{courseBusy ? 'Saving…' : 'Save course'}
							</button>
						</div>
					</div>
				{/if}
			</div>
		</div>

		{#if !readyAll}
			<p class="gate-hint" role="note">
				{#if !readyYears && !readyCourses}
					Add at least one year level with terms and one course template to continue.
				{:else if !readyYears}
					Add at least one year level with terms to continue.
				{:else}
					Add at least one course template to continue.
				{/if}
			</p>
		{/if}

		<div class="nav-row">
			<button class="btn btn-secondary" onclick={() => goToStep(1)}>Back</button>
			<button
				class="btn btn-primary"
				data-testid="wizard-step2-next"
				disabled={!readyAll}
				title={!readyAll ? 'Finish the checklist above first' : undefined}
				onclick={() => goToStep(3)}
			>
				Continue to Offerings
			</button>
		</div>
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

	.empty {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
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

	.checklist {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-bottom: 1.25rem;
	}

	.check {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.875rem;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-muted);
		background: var(--divider);
	}

	.check.done {
		color: var(--success);
		background: var(--success-bg);
	}

	.two-col {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
	}

	.panel {
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1.25rem;
		background: var(--bg-card);
	}

	.panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.panel-head h3 {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: var(--text);
	}

	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.rows li {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--divider);
		border-radius: 8px;
	}

	.rows li.termless {
		border-style: dashed;
		border-color: var(--border-strong);
	}

	.row-main {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.row-sub {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px dashed var(--border-strong);
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

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.terms {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0.75rem 0 0;
	}

	.gate-hint {
		margin: 1.25rem 0 0;
		font-size: 0.875rem;
		color: var(--text-secondary);
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.75rem 1rem;
	}

	.nav-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-top: 1.5rem;
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

	.btn-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
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

	@media (max-width: 760px) {
		.two-col {
			grid-template-columns: minmax(0, 1fr);
		}
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
