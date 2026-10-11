<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		adminProgramDetailState,
		deleteProgramYear,
		initAdminProgramDetail,
		refreshAdminProgramDetail,
	} from '$lib/features/admin/programs/store.svelte';
	import {
		createYearLevel,
		updateProgram,
		updateYearLevel,
	} from '$lib/features/admin/programs/service';
	import {
		programUpdateSchema,
		yearLevelCreateSchema,
		yearLevelUpdateSchema,
	} from '$lib/features/admin/programs/schema';
	import { yearLabel } from '$lib/shared/utils/format';
	import { TERM_CODES, TERM_LABELS } from '$lib/shared/constants/terms';
	import type { YearLevel } from '$lib/shared/types';
	import { Routes } from '$lib/shared/constants/routes';
	import { notifyEntityChanged, subscribeEntity } from '$lib/shared/utils/entityEvents';
	import { onFocusRevalidate } from '$lib/shared/utils/revalidateOnFocus';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	// Program Detail (wireframe 4.5b): header with totals + edit, year-level
	// cards with editable term chips, add-year and manage-terms modals, year
	// delete with its 409 has-offerings guard surfaced inline. Terms persist
	// via PATCH {program}/years/{year} — one save per modal, and an empty term
	// list is allowed (a termless year just can't back offerings yet).

	const programId = $derived(Number(page.params.id));

	let editOpen = $state(false);
	let e_name = $state('');
	let e_description = $state('');
	let editError = $state<string | null>(null);
	let editBusy = $state(false);

	let yearOpen = $state(false);
	let y_number = $state('');
	let y_terms = $state<{ code: string; label: string }[]>([]);
	let yearError = $state<string | null>(null);
	let yearBusy = $state(false);

	let termsOpen = $state(false);
	let termsTarget = $state<YearLevel | null>(null);
	let t_rows = $state<{ code: string; label: string }[]>([]);
	let termsError = $state<string | null>(null);
	let termsBusy = $state(false);

	let deleteTarget = $state<YearLevel | null>(null);
	let deleteBusy = $state(false);
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

	type TermRow = { code: string; label: string };

	// The user picks the code and the label; this only picks sensible starting
	// values for a new row by taking whichever are not already in use, so the
	// default never collides. Nothing here caps how many rows can be added.
	const nextTermRow = (rows: TermRow[]): TermRow => {
		const usedCodes = new Set(rows.map((r) => r.code));
		const usedLabels = new Set(rows.map((r) => r.label));
		return {
			code: TERM_CODES.find((c) => !usedCodes.has(c)) ?? TERM_CODES[0],
			label: TERM_LABELS.find((l) => !usedLabels.has(l)) ?? TERM_LABELS[0],
		};
	};

	const openEdit = () => {
		if (!program) return;
		editError = null;
		e_name = program.name;
		e_description = program.description ?? '';
		editOpen = true;
	};

	const submitEdit = async () => {
		if (!program) return;
		editError = null;
		editBusy = true;
		try {
			const parsed = programUpdateSchema.safeParse({
				name: e_name || undefined,
				description: e_description || undefined,
			});
			if (!parsed.success) {
				editError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
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
		t_rows = year.terms.map((t) => ({ ...t }));
		termsOpen = true;
	};

	const submitTerms = async () => {
		if (!program || !termsTarget) return;
		termsError = null;
		termsBusy = true;
		try {
			const parsed = yearLevelUpdateSchema.safeParse({ terms: t_rows });
			if (!parsed.success) {
				termsError = parsed.error.issues[0]?.message ?? 'Each term needs a code and a label.';
				return;
			}
			await updateYearLevel(program.id, termsTarget.id, {
				term_structure: { terms: parsed.data.terms ?? [] },
			});
			termsOpen = false;
			termsTarget = null;
			await refreshAdminProgramDetail(program.id);
			notifyEntityChanged('programs');
		} catch (e: unknown) {
			termsError = e instanceof Error && e.message ? e.message : 'Save failed. Please try again.';
		} finally {
			termsBusy = false;
		}
	};

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

	const termsText = (year: YearLevel) =>
		year.terms.length > 0 ? year.terms.map((t) => t.label).join(' · ') : 'No terms yet';
</script>

<div class="page">
	<div class="page-top">
		<button class="btn btn-secondary" onclick={() => goto(Routes.ADMIN_PROGRAMS)}>
			← Back to Program Management
		</button>
		<p class="crumb"><a href={Routes.ADMIN_PROGRAMS}>Programs</a> / Detail</p>
	</div>

	{#if adminProgramDetailState.loading}
		<section class="card"><p class="muted">Loading…</p></section>
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
				<p class="empty">No year levels yet — add Year 1 to start. Student imports resolve their year_level against these rows.</p>
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
				<label>Name<input class="input" bind:value={e_name} /></label>
				<label>Description<input class="input" bind:value={e_description} /></label>
				<p class="hint">Code and total years are immutable after creation.</p>
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
					{#each y_terms as term, i (i)}
						<div class="grid2">
							<select class="input" aria-label="Term code" bind:value={y_terms[i].code}>
								{#each TERM_CODES as c (c)}
									<option value={c}>{c}</option>
								{/each}
							</select>
							<select class="input" aria-label="Term label" bind:value={y_terms[i].label}>
								{#each TERM_LABELS as l (l)}
									<option value={l}>{l}</option>
								{/each}
							</select>
						</div>
					{/each}
					<div class="terms-row">
						<button
							class="btn btn-secondary"
							onclick={() => (y_terms = [...y_terms, nextTermRow(y_terms)])}
						>
							Add term
						</button>
						{#if y_terms.length > 0}
							<button class="btn btn-ghost" onclick={() => (y_terms = y_terms.slice(0, -1))}>
								Remove last
							</button>
						{/if}
					</div>
				</div>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => (yearOpen = false)}>Cancel</button>
				<button class="btn btn-primary" data-testid="save-year" disabled={yearBusy} onclick={submitYear}>
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
				{#if t_rows.length === 0}
					<p class="muted">No terms. Add one below, or save empty — a termless year just can't back offerings yet.</p>
				{/if}
				{#each t_rows as term, i (i)}
					<div class="grid2">
						<select class="input" aria-label="Term code" bind:value={t_rows[i].code}>
							{#each TERM_CODES as c (c)}
								<option value={c}>{c}</option>
							{/each}
						</select>
						<select class="input" aria-label="Term label" bind:value={t_rows[i].label}>
							{#each TERM_LABELS as l (l)}
								<option value={l}>{l}</option>
							{/each}
						</select>
					</div>
				{/each}
				<div class="terms-row">
					<button
						class="btn btn-secondary"
						onclick={() => (t_rows = [...t_rows, nextTermRow(t_rows)])}
					>
						Add term
					</button>
					{#if t_rows.length > 0}
						<button class="btn btn-ghost" onclick={() => (t_rows = t_rows.slice(0, -1))}>
							Remove last
						</button>
					{/if}
				</div>
			</div>
			<div class="modal-actions">
				<button class="btn btn-ghost" onclick={() => { termsOpen = false; termsTarget = null; }}>Cancel</button>
				<button class="btn btn-primary" disabled={termsBusy} onclick={submitTerms}>
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

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		font-family: system-ui, sans-serif;
	}

	/* Back button + breadcrumb read as one header block, so the .page flex gap
	 * (1.5rem) does not push them a full row apart. */
	.page-top {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.crumb {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.crumb a {
		color: var(--accent);
		text-decoration: none;
		font-weight: 600;
	}

	.crumb a:hover {
		text-decoration: underline;
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

	.terms-row {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	@media (max-width: 640px) {
		.card {
			padding: 1.25rem;
		}

		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
