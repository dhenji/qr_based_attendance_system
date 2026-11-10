<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminProgramDetailState,
		adminProgramsState,
		deleteArchivedProgram,
		deleteProgramYear,
		initAdminProgramDetail,
		refreshAdminProgramDetail,
	} from '$lib/features/admin/programs/store.svelte';
	import {
		createYearLevel,
		setProgramActive,
		updateProgram,
		updateYearLevel,
	} from '$lib/features/admin/programs/service';
	import {
		programUpdateSchema,
		yearLevelCreateSchema,
		yearLevelUpdateSchema,
	} from '$lib/features/admin/programs/schema';
	import { yearLabel } from '$lib/shared/utils/format';
	import { nextTermRow } from '$lib/shared/constants/terms';
import TermRowsEditor from '$lib/features/admin/programs/components/TermRowsEditor.svelte';
	import type { YearLevel } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Program Detail (wireframe 4.5b): header with totals + edit, year-level
	// cards with editable term chips, add-year and manage-terms modals, year
	// delete with its 409 has-offerings guard surfaced inline, and program
	// delete (archived programs only) with its 409 has-offerings/has-students
	// guards surfaced inline. Terms persist
	// via PATCH {program}/years/{year} — one save per modal, and an empty term
	// list is allowed (a termless year just can't back offerings yet).

	const programId = $derived(Number(page.params.id));

	let editOpen = $state(false);
	let e_name = $state('');
	let e_description = $state('');
	let editError = $state<string | null>(null);
	let editFieldErrors = $state<Record<string, string>>({});
	let editBusy = $state(false);

	let yearOpen = $state(false);
	let y_number = $state('');
	let y_terms = $state<{ code: string; label: string; weeks?: number; existing?: boolean }[]>([]);
	let yearError = $state<string | null>(null);
	let yearBusy = $state(false);

	let termsOpen = $state(false);
	let termsTarget = $state<YearLevel | null>(null);
	let t_rows = $state<{ code: string; label: string; weeks?: number; existing?: boolean }[]>([]);
	let termsError = $state<string | null>(null);
	let termsBusy = $state(false);
	// When set, saving Manage Terms also writes these weeks to every sibling
	// year level that offers the same term code (D86 drift guard).
	let applyWeeksToAll = $state(false);

	let deleteTarget = $state<YearLevel | null>(null);
	let deleteBusy = $state(false);
	let programDeleteOpen = $state(false);
	let programDeleteBusy = $state(false);
	const autoRefreshStops: (() => void)[] = [];

	onDestroy(() => {
		for (const stop of autoRefreshStops) stop();
	});

	const refreshVisible = () => {
		if (!Number.isFinite(programId)) return;
		if (!adminProgramDetailState.loading) void refreshAdminProgramDetail(programId);
	};

	onMount(() => {
		if (Number.isFinite(programId)) initAdminProgramDetail(programId);
		// Own entity -> refresh the detail (covers year edits/deletes made
		// on other tabs; the store mutator emits after its own refresh).
		autoRefreshStops.push(
			subscribeEntity('programs', refreshVisible),
			onFocusRevalidate(refreshVisible)
		);
	});

	const program = $derived(adminProgramDetailState.program);


	const openEdit = () => {
		if (!program) return;
		editError = null;
		editFieldErrors = {};
		e_name = program.name;
		e_description = program.description ?? '';
		editOpen = true;
	};

	const submitEdit = async () => {
		if (!program) return;
		editError = null;
		editFieldErrors = {};
		editBusy = true;
		try {
			const parsed = programUpdateSchema.safeParse({
				name: e_name,
				description: e_description || undefined,
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
			await updateProgram(program.id, {
				name: parsed.data.name,
				description: parsed.data.description,
			});
			editOpen = false;
			await refreshAdminProgramDetail(program.id);
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			editError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			editBusy = false;
		}
	};

	// Years still available to add: 1..total_years, minus any already created.
	// Hiding the taken ones avoids the backend's 409 year_number_exists.
	const availableYears = $derived.by(() => {
		if (!program) return [] as number[];
		const taken = new Set(program.yearLevels.map((y) => y.yearNumber));
		return Array.from({ length: program.totalYears }, (_, i) => i + 1).filter(
			(n) => !taken.has(n)
		);
	});

	const openYear = () => {
		yearError = null;
		// Default to the first free year; the label is derived from it.
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
				terms: y_terms.map(({ code, label, weeks }) => ({ code, label, weeks })),
			});
			if (!parsed.success) {
				yearError =
					parsed.error.issues.map((issue) => issue.message).join(' ') || 'Check the form and try again.';
				return;
			}
			await createYearLevel(program.id, {
				year_number: parsed.data.year_number,
				label: parsed.data.label,
				term_structure: { terms: parsed.data.terms },
			});
			yearOpen = false;
			await refreshAdminProgramDetail(program.id);
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			yearError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			yearBusy = false;
		}
	};

	const openTerms = (year: YearLevel) => {
		termsTarget = year;
		termsError = null;
		applyWeeksToAll = false;
		t_rows = year.terms.map((t) => ({ ...t, existing: true }));
		termsOpen = true;
	};

	const submitTerms = async () => {
		if (!program || !termsTarget) return;
		termsError = null;
		termsBusy = true;
		try {
			const parsed = yearLevelUpdateSchema.safeParse({
				terms: t_rows.map(({ code, label, weeks }) => ({ code, label, weeks })),
			});
			if (!parsed.success) {
				termsError =
					parsed.error.issues.map((issue) => issue.message).join(' ') ||
					'Each term needs a code and a label.';
				return;
			}
			const terms = parsed.data.terms ?? [];
			await updateYearLevel(program.id, termsTarget.id, {
				term_structure: { terms },
			});
			// Drift guard: optionally push these weeks to every sibling year
			// level offering the same term code (D86).
			if (applyWeeksToAll) {
				const edits = new Map<string, number | undefined>(
					terms.map((t) => [t.code, t.weeks])
				);
				for (const y of program.yearLevels) {
					if (y.id === termsTarget.id) continue;
					let changed = false;
					const siblingTerms = y.terms.map((t) => {
						const weeks = edits.get(t.code);
						if (weeks !== undefined && weeks !== t.weeks) {
							changed = true;
							return { ...t, weeks };
						}
						return t;
					});
					if (changed) {
						await updateYearLevel(program.id, y.id, {
							term_structure: { terms: siblingTerms },
						});
					}
				}
			}
			termsOpen = false;
			termsTarget = null;
			applyWeeksToAll = false;
			await refreshAdminProgramDetail(program.id);
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			termsError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			termsBusy = false;
		}
	};

	// Term codes whose session weeks differ across the program's year levels
	// (D86). Non-blocking: offerings in different years would be scored
	// against different term lengths, which is usually accidental. The modal
	// value is the reference; any year that disagrees is flagged so the odd
	// one out is visible at a glance.
	const termDrift = $derived.by<
		{ code: string; values: { yearId: number; label: string; weeks: number; isOutlier: boolean }[] }[]
	>(() => {
		if (!program || !termsTarget) return [];
		const rows: {
			code: string;
			values: { yearId: number; label: string; weeks: number; isOutlier: boolean }[];
		}[] = [];
		const codes = new Set(t_rows.map((row) => row.code));
		for (const code of codes) {
			const values: { yearId: number; label: string; weeks: number }[] = [];
			for (const y of program.yearLevels) {
				if (y.id === termsTarget.id) {
					// Use the editor's pending value for this year so the
					// warning clears as soon as the admin fixes it.
					const row = t_rows.find((r) => r.code === code);
					if (row && row.weeks != null) {
						values.push({ yearId: y.id, label: y.label, weeks: Number(row.weeks) });
					}
					continue;
				}
				const term = y.terms.find((t) => t.code === code);
				if (term?.weeks != null) {
					values.push({ yearId: y.id, label: y.label, weeks: Number(term.weeks) });
				}
			}
			if (new Set(values.map((v) => v.weeks)).size <= 1) continue;

			// Reference = the modal value (ties → earliest year level), so the
			// minority values are the ones flagged.
			const counts = new Map<number, number>();
			for (const v of values) counts.set(v.weeks, (counts.get(v.weeks) ?? 0) + 1);
			let reference = values[0].weeks;
			let best = -1;
			for (const v of values) {
				const count = counts.get(v.weeks) ?? 0;
				if (count > best) {
					best = count;
					reference = v.weeks;
				}
			}

			rows.push({
				code,
				values: values.map((v) => ({ ...v, isOutlier: v.weeks !== reference })),
			});
		}
		return rows;
	});
	const hasSiblings = $derived((program?.yearLevels.length ?? 0) > 1);
	// What the "apply to other year levels" checkbox will actually copy —
	// only terms with a week count typed in this year's editor.
	const weeksToApply = $derived(
		t_rows
			.filter((row) => row.weeks != null)
			.map((row) => `${row.code} ${row.weeks}w`)
	);

	const confirmDeleteYear = async () => {
		if (!program || !deleteTarget) return;
		deleteBusy = true;
		try {
			await deleteProgramYear(program.id, deleteTarget.id);
			deleteTarget = null;
		} finally {
			deleteBusy = false;
		}
	};

	const confirmDeleteProgram = async () => {
		if (!program) return;
		programDeleteBusy = true;
		try {
			await deleteArchivedProgram(program.id);
			programDeleteOpen = false;
			await goto(Routes.ADMIN_PROGRAMS);
		} finally {
			programDeleteBusy = false;
		}
	};

	let archiveBusy = $state(false);
	let archiveConfirm = $state(false);
	let reactivateConfirm = $state(false);

	const setActive = async (active: boolean, failure: string) => {
		if (!program || archiveBusy) return;
		archiveBusy = true;
		try {
			await setProgramActive(program.id, active);
			await refreshAdminProgramDetail(program.id);
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			adminProgramDetailState.actionError =
				e instanceof Error && e.message ? e.message : failure;
		} finally {
			archiveBusy = false;
		}
	};

	const onReactivate = () => void setActive(true, 'Failed to reactivate program');

	const confirmArchive = async () => {
		await setActive(false, 'Failed to archive program');
		if (program && !program.isActive) archiveConfirm = false;
	};

	const closeProgramDelete = () => {
		adminProgramsState.actionError = null;
		programDeleteOpen = false;
	};

	const termsText = (year: YearLevel) =>
		year.terms.length > 0
			? year.terms
					.map((t) => (t.weeks ? `${t.label} (${t.weeks}w)` : t.label))
					.join(' · ')
			: 'No terms yet';
</script>

<div class="page">
	<div class="page-top">
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_PROGRAMS)}>
			← Back to Program Management
		</button>
	</div>

	{#if adminProgramDetailState.loading}
		<SkeletonDetail rows={6} label="Loading program…" />
	{:else if adminProgramDetailState.error || !program}
		<section class="card">
			<p class="error">Could not load program: {adminProgramDetailState.error ?? 'Not found.'}</p>
		</section>
	{:else}
		<header class="header">
			<div>
				<h1>{program.code} — {program.name}</h1>
				<p class="muted">
					{program.totalYears} {program.totalYears === 1 ? 'year' : 'years'} · {program.yearLevelCount}
					year levels · {program.courseCount} courses · {program.isActive ? 'Active' : 'Archived'}
				</p>
			</div>
			<div class="header-actions">
				<button class="btn btn-secondary" data-testid="edit-program" onclick={openEdit}>
					<AppIcon name="file" size={18} />
					Edit
				</button>
			</div>
		</header>

		{#if adminProgramDetailState.actionError}
			<section class="card"><p class="error" role="alert">{adminProgramDetailState.actionError}</p></section>
		{/if}

		<section class="years-head">
			<h2 class="section-title">Year Levels</h2>
			<button
				class="btn btn-primary"
				data-testid="add-year"
				disabled={availableYears.length === 0}
				onclick={openYear}
			>
				<AppIcon name="plus" size={18} />
				Add Year
			</button>
		</section>

		{#if program.yearLevels.length === 0}
			<section class="card">
				<EmptyState
					icon="file"
					title="No year levels yet"
					hint="Add Year 1 to start. Student imports resolve their year_level against these rows."
				/>
			</section>
		{:else}
			<ul class="years">
				{#each program.yearLevels as year (year.id)}
					<li class="card year">
						<div class="year-top">
							<h3 class="year-title">{year.label}</h3>
							<div class="year-actions">
								<button class="link" onclick={() => openTerms(year)}>Manage Terms</button>
								<button class="link danger" onclick={() => { adminProgramDetailState.actionError = null; deleteTarget = year; }}>Delete</button>
							</div>
						</div>
						<p class="muted">Terms: {termsText(year)}</p>
						<div class="chips">
							{#each year.terms as term, i (i)}
								<span class="chip">{term.label}</span>
							{/each}
						</div>
					</li>
				{/each}
			</ul>
		{/if}
		<section class="card danger">
			<h2 class="card-title">Danger zone</h2>
			<p class="muted">
				Status: <strong>{program.isActive ? 'Active' : 'Archived'}</strong>. Archiving
				flips this program to archived — year levels stay, offerings and
				students keep working. Reactivating restores it. Deletion is
				permanent and blocked while course offerings or students still use
				this program.
			</p>
			<div class="danger-actions">
				{#if program.isActive}
					<button class="btn btn-danger" disabled={archiveBusy} onclick={() => { adminProgramDetailState.actionError = null; archiveConfirm = true; }}>
						Archive program
					</button>
				{:else}
					<button class="btn btn-success" disabled={archiveBusy} onclick={() => (reactivateConfirm = true)}>
						{archiveBusy ? 'Reactivating…' : 'Reactivate program'}
					</button>
				{/if}
				<button
					class="btn btn-danger"
					disabled={programDeleteBusy || program.isActive}
					title={program.isActive ? 'Archive first — only archived programs can be deleted' : undefined}
					onclick={() => { adminProgramsState.actionError = null; programDeleteOpen = true; }}
				>
					Delete permanently
				</button>
			</div>
			{#if !program.isActive}
				<p class="hint">Delete is blocked while course offerings or students still use this program.</p>
			{/if}
		</section>
	{/if}
</div>

{#if editOpen && program}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="edit-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (editOpen = false) }}
		>
			<h2 id="edit-title" class="modal-title">Edit program</h2>
			{#if editError}
				<p class="error" role="alert">{editError}</p>
			{/if}
			<div class="form">
				<label>
					Name *
					<input
						class="input"
						class:invalid={!!editFieldErrors.name}
						bind:value={e_name}
						maxlength="100"
						aria-required="true"
						aria-invalid={!!editFieldErrors.name}
						aria-describedby="edit-program-name-help"
						oninput={() => { if (editFieldErrors.name) editFieldErrors = { ...editFieldErrors, name: '' }; }}
					/>
					{#if editFieldErrors.name}
						<p class="field-error" role="alert">{editFieldErrors.name}</p>
					{:else}
						<p class="hint" id="edit-program-name-help">Up to 100 characters.</p>
					{/if}
				</label>
				<label>
					Description (optional)
					<input
						class="input"
						class:invalid={!!editFieldErrors.description}
						bind:value={e_description}
						maxlength="1000"
						aria-invalid={!!editFieldErrors.description}
						aria-describedby="edit-program-desc-help"
						oninput={() => { if (editFieldErrors.description) editFieldErrors = { ...editFieldErrors, description: '' }; }}
					/>
					{#if editFieldErrors.description}
						<p class="field-error" role="alert">{editFieldErrors.description}</p>
					{:else}
						<p class="hint" id="edit-program-desc-help">Optional. Up to 1000 characters.</p>
					{/if}
				</label>
				<p class="hint">Code and total years are immutable after creation.</p>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (editOpen = false)}>Cancel</button>
				<button class="btn btn-primary" aria-busy={editBusy} disabled={editBusy} onclick={submitEdit}>
					{editBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if yearOpen}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="year-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (yearOpen = false) }}
		>
			<h2 id="year-title" class="modal-title">Add year level</h2>
			{#if yearError}
				<p class="error" role="alert">{yearError}</p>
			{/if}
			<div class="form">
				<label>
					Year
					<select class="input" bind:value={y_number}>
						{#each availableYears as n (n)}
							<option value={n}>{yearLabel(n)}</option>
						{/each}
					</select>
				</label>
				<p class="hint">The label is generated from the year, so the two can't disagree.</p>
				<div class="terms-edit">
					<span class="terms-label">Terms</span>
					<TermRowsEditor bind:rows={y_terms} busy={yearBusy} lockCodeForExisting={false} />
				</div>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (yearOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-year" aria-busy={yearBusy} disabled={yearBusy} onclick={submitYear}>
					{yearBusy ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if termsOpen && termsTarget}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="terms-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (termsOpen = false) }}
		>
			<h2 id="terms-title" class="modal-title">Manage terms — {termsTarget.label}</h2>
			{#if termsError}
				<p class="error" role="alert">{termsError}</p>
			{/if}
			<div class="form">
				<p class="hint">
					The code is the value stored on offerings and enrollments; keep it stable for terms already used.
					Only change the display name for cosmetic renames.
				</p>
				<TermRowsEditor
					bind:rows={t_rows}
					busy={termsBusy}
					lockCodeForExisting={true}
					emptyMessage="No terms yet. Add one below, or save empty — a termless year just can't back offerings yet."
				/>
				{#if termDrift.length > 0}
					<aside class="drift" role="status" aria-live="polite">
						<div class="drift-head">
							<span class="drift-icon"><AppIcon name="alert" size={16} /></span>
							<div>
								<p class="drift-title">Session weeks differ across year levels</p>
								<p class="drift-sub">
									The same term is set to different lengths, so offerings in different
									years are scored against different session totals.
								</p>
							</div>
						</div>
						<ul class="drift-list">
							{#each termDrift as drift (drift.code)}
								<li class="drift-row">
									<span class="drift-code">{drift.code}</span>
									<span class="drift-chips">
										{#each drift.values as value (value.yearId)}
											<span class="drift-chip" class:outlier={value.isOutlier}>
												<span class="drift-year">{value.label}</span>
												<span class="drift-weeks">{value.weeks}w</span>
											</span>
										{/each}
									</span>
								</li>
							{/each}
						</ul>
						{#if hasSiblings && weeksToApply.length > 0}
							<label class="drift-apply">
								<input type="checkbox" bind:checked={applyWeeksToAll} disabled={termsBusy} />
								<span>
									<span class="drift-apply-title">
										Copy {termsTarget.label}'s weeks to the other year levels
									</span>
									<span class="drift-apply-hint">
										On save, {weeksToApply.join(' · ')} are also written to every other
										year level that has these terms. Term codes and names aren't changed.
									</span>
								</span>
							</label>
						{/if}
					</aside>
				{/if}
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => { termsOpen = false; termsTarget = null; }}>Cancel</button>
				<button class="btn btn-primary" aria-busy={termsBusy} disabled={termsBusy} onclick={submitTerms}>
					{termsBusy ? 'Saving…' : 'Save terms'}
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
			aria-labelledby="delete-year-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (deleteTarget = null) }}
		>
			<h2 id="delete-year-title" class="modal-title">Delete {deleteTarget.label}?</h2>
			<p class="modal-text">
				This permanently removes the year level. If course offerings still use it,
				deletion will be blocked — move or delete those first.
			</p>
			{#if adminProgramDetailState.actionError}
				<p class="error" role="alert">{adminProgramDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (deleteTarget = null)}>Cancel</button>
				<button class="btn btn-danger" disabled={deleteBusy} onclick={confirmDeleteYear}>
					{deleteBusy ? 'Deleting…' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if archiveConfirm && program}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="program-archive-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (archiveConfirm = false) }}
		>
			<h2 id="program-archive-title" class="modal-title">Archive {program.code}?</h2>
			<p class="modal-text">
				{program.name} will be flipped to archived. Year levels stay, offerings
				and students keep working, and you can reactivate it anytime.
			</p>
			{#if adminProgramDetailState.actionError}
				<p class="error" role="alert">{adminProgramDetailState.actionError}</p>
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

{#if reactivateConfirm && program}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="program-reactivate-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: () => (reactivateConfirm = false) }}
		>
			<h2 id="program-reactivate-title" class="modal-title">Reactivate {program.code}?</h2>
			<p class="modal-text">
				{program.name} will be restored to the active list.
			</p>
			{#if adminProgramDetailState.actionError}
				<p class="error" role="alert">{adminProgramDetailState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" disabled={archiveBusy} onclick={() => (reactivateConfirm = false)}>Cancel</button>
				<button class="btn btn-success" disabled={archiveBusy} onclick={async () => { await onReactivate(); if (program && program.isActive) reactivateConfirm = false; }}>
					{archiveBusy ? 'Reactivating…' : 'Reactivate'}
				</button>
			</div>
		</div>
	</div>
{/if}

{#if programDeleteOpen && program}
	<div class="modal-overlay" role="presentation">
		<div
			class="modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-program-title"
			tabindex="-1"
			use:trapFocus={{ onEscape: closeProgramDelete }}
		>
			<h2 id="delete-program-title" class="modal-title">Permanently delete {program.code}?</h2>
			<p class="modal-text">
				{program.name} will be removed for good, along with its year levels.
				If course offerings or students still use it, deletion will be blocked
				and the program stays archived.
			</p>
			{#if adminProgramsState.actionError}
				<p class="error" role="alert">{adminProgramsState.actionError}</p>
			{/if}
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={closeProgramDelete}>Cancel</button>
				<button class="btn btn-danger" disabled={programDeleteBusy} onclick={confirmDeleteProgram}>
					{programDeleteBusy ? 'Deleting…' : 'Delete'}
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

	/* Back button reads as its own header block, so the .page flex gap
	 * (1.5rem) does not push it a full row apart from the content. */
	.page-top {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
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

	.years-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
	}

	.years {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 1rem;
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

	.year {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.year-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.year-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0;
	}

	.year-actions {
		display: flex;
		gap: 0.75rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.chip {
		display: inline-block;
		padding: 0.25rem 0.625rem;
		border-radius: 99px;
		background: var(--divider);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		font-size: 0.8125rem;
		font-weight: 600;
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

	.terms-edit {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}

	.terms-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.drift {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 0.875rem 1rem;
		border: 1px solid var(--border-strong);
		border-left: 3px solid var(--warning-text);
		border-radius: 8px;
		background: var(--bg-muted);
	}

	.drift-head {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
	}

	.drift-icon {
		flex: none;
		margin-top: 0.0625rem;
		color: var(--warning-text);
	}

	.drift-title {
		margin: 0;
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.drift-sub {
		margin: 0.125rem 0 0;
		font-size: 0.75rem;
		line-height: 1.45;
		color: var(--text-muted);
	}

	.drift-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.drift-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.625rem;
	}

	.drift-code {
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.drift-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}

	.drift-chip {
		display: inline-flex;
		align-items: baseline;
		gap: 0.375rem;
		padding: 0.1875rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 99px;
		background: var(--bg-card);
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.drift-chip.outlier {
		border-color: var(--warning-bg);
		background: var(--warning-bg);
		color: var(--warning-text);
	}

	.drift-year {
		color: var(--text-muted);
	}

	.drift-chip.outlier .drift-year {
		color: inherit;
		opacity: 0.85;
	}

	.drift-weeks {
		font-weight: 700;
	}

	.drift-apply {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--border);
		cursor: pointer;
	}

	.drift-apply input {
		flex: none;
		margin-top: 0.1875rem;
	}

	.drift-apply-title {
		display: block;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-strong);
	}

	.drift-apply-hint {
		display: block;
		margin-top: 0.125rem;
		font-size: 0.75rem;
		line-height: 1.45;
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

	.btn-success {
		background: var(--success);
		border: 1px solid var(--success);
		color: var(--on-brand);
	}

	.btn-success:hover:not(:disabled) {
		filter: brightness(1.05);
	}

	.modal-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
		margin-top: 1.5rem;
	}

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}
	}
</style>
