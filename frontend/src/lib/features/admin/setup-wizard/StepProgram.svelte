<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte';
	import SkeletonDetail from '$lib/components/SkeletonDetail.svelte';
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { goToStep, setWizardProgram, wizardState } from './store.svelte';
	import { createProgram, getProgram, listPrograms } from '$lib/features/admin/programs/service';
	import { programCreateSchema } from '$lib/features/admin/programs/schema';
	import type { Program } from '$lib/shared/types';
	import { APIError } from '$lib/api/client';
	import { notifyEntityChanged } from '$lib/shared/utils/entityEvents';
	import { friendlyActionError } from '$lib/shared/utils/deleteErrors';

	// Wizard step 1: bind the flow to one program. Either pick an existing
	// program (the common case — the wizard then guides structure on top of
	// it) or create a new one with the same schema + service the Programs
	// page uses. The choice is stored in the wizard store so steps 2 and 3
	// inherit it; switching programs later clears the downstream picks.

	let view = $state<'pick' | 'summary'>(wizardState.programId === null ? 'pick' : 'summary');
	let mode = $state<'existing' | 'new'>('existing');

	let options = $state<Program[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);

	let pickedId = $state('');
	let confirmError = $state<string | null>(null);

	let f_code = $state('');
	let f_name = $state('');
	let f_description = $state('');
	let f_total_years = $state('');
	let formError = $state<string | null>(null);
	let formBusy = $state(false);

	const chosen = $derived(
		wizardState.programId === null
			? null
			: (options.find((p) => p.id === wizardState.programId) ?? null)
	);

	const load = async () => {
		loading = true;
		loadError = null;
		try {
			options = (await listPrograms({ page: 1, size: 50 })).items;
			await reconcilePersistedProgram();
		} catch (e: unknown) {
			loadError = friendlyActionError(e, 'Could not load programs.');
		} finally {
			loading = false;
		}
	};

	// A persisted program id can go stale (deleted on another tab) or sit
	// past the first list page. Verify it instead of trusting storage: a
	// confirmed program is merged into the picker so the summary can render.
	// Only a true 404 clears the pick — transient failures keep it, so a
	// network blip cannot strand the admin back at step 1.
	const reconcilePersistedProgram = async (): Promise<void> => {
		if (wizardState.programId === null) return;
		if (options.some((p) => p.id === wizardState.programId)) return;
		try {
			const detail = await getProgram(wizardState.programId);
			options = [detail, ...options];
		} catch (e: unknown) {
			if (e instanceof APIError && (e.code === 'program_not_found' || e.status === 404)) {
				setWizardProgram(null);
				view = 'pick';
			}
		}
	};

	onMount(() => {
		void load();
	});

	const confirmExisting = () => {
		confirmError = null;
		const id = Number(pickedId);
		if (!Number.isInteger(id) || id <= 0) {
			confirmError = 'Pick a program from the list first.';
			return;
		}
		setWizardProgram(id);
		view = 'summary';
	};

	const submitNew = async () => {
		formError = null;
		formBusy = true;
		try {
			const parsed = programCreateSchema.safeParse({
				code: f_code,
				name: f_name,
				description: f_description || undefined,
				total_years: f_total_years,
			});
			if (!parsed.success) {
				formError = parsed.error.issues[0]?.message ?? 'Check the form and try again.';
				return;
			}
			const created = await createProgram({
				code: parsed.data.code,
				name: parsed.data.name,
				description: parsed.data.description || undefined,
				total_years: parsed.data.total_years,
			});
			options = [created, ...options.filter((p) => p.id !== created.id)];
			setWizardProgram(created.id);
			notifyEntityChanged('programs');
			view = 'summary';
		} catch (e: unknown) {
			formError = friendlyActionError(e, 'Save failed. Please try again.');
		} finally {
			formBusy = false;
		}
	};

	const startChange = () => {
		confirmError = null;
		formError = null;
		pickedId = wizardState.programId === null ? '' : String(wizardState.programId);
		view = 'pick';
	};
</script>

<section class="card">
	<h2 class="step-title">Step 1 — Program</h2>
	<p class="muted">
		Everything in this setup belongs to one degree program. Pick the program you are
		setting up, or create it now — year levels, courses, and offerings attach to it
		in the next steps.
	</p>

	{#if loading}
		<SkeletonDetail bare rows={4} label="Loading programs…" />
	{:else if loadError}
		<p class="error" role="alert">{loadError}</p>
		<button class="btn btn-secondary" onclick={() => void load()}>Retry</button>
	{:else if view === 'summary' && chosen}
		<div class="chosen">
			<div>
				<p class="chosen-code">{chosen.code}</p>
				<p class="chosen-name">{chosen.name}</p>
				<p class="muted">
					{chosen.totalYears} {chosen.totalYears === 1 ? 'year' : 'years'} ·
					{chosen.yearLevelCount} year {chosen.yearLevelCount === 1 ? 'level' : 'levels'} ·
					{chosen.courseCount} {chosen.courseCount === 1 ? 'course' : 'courses'}
				</p>
			</div>
			<button class="btn btn-secondary" onclick={startChange}>Change</button>
		</div>
		<div class="nav-row">
			<span></span>
			<button class="btn btn-primary" data-testid="wizard-step1-next" onclick={() => goToStep(2)}>
				Continue to Structure
			</button>
		</div>
	{:else}
		<div class="toggle-group" role="group" aria-label="Program source">
			<button
				type="button"
				class="toggle-btn"
				class:selected={mode === 'existing'}
				aria-pressed={mode === 'existing'}
				onclick={() => (mode = 'existing')}
			>
				Use existing
			</button>
			<button
				type="button"
				class="toggle-btn"
				class:selected={mode === 'new'}
				aria-pressed={mode === 'new'}
				onclick={() => (mode = 'new')}
			>
				Create new
			</button>
		</div>

		{#if mode === 'existing'}
			{#if options.length === 0}
				<EmptyState
					icon="file"
					title="No programs yet"
					hint="Switch to “Create new” to add the first one."
				/>
			{:else}
				{#if confirmError}
					<p class="error" role="alert">{confirmError}</p>
				{/if}
				<div class="form">
					<label>Program
						<select class="input" bind:value={pickedId} aria-label="Pick a program">
							<option value="">Pick a program…</option>
							{#each options as p (p.id)}
								<option value={p.id}>{p.code} — {p.name}</option>
							{/each}
						</select>
					</label>
					<p class="hint">
						Year levels already on this program are kept. Step 2 shows what is still missing.
					</p>
				</div>
				<div class="nav-row">
					<span></span>
					<button
						class="btn btn-primary"
						disabled={!pickedId}
						onclick={confirmExisting}
					>
						Use this program
					</button>
				</div>
			{/if}
		{:else}
			{#if formError}
				<p class="error" role="alert">{formError}</p>
			{/if}
			<div class="form">
				<div class="grid2">
					<label>Code<input class="input" bind:value={f_code} placeholder="BSCS" /></label>
					<label>Total years<input class="input" inputmode="numeric" bind:value={f_total_years} placeholder="4" /></label>
				</div>
				<label>Name<input class="input" bind:value={f_name} placeholder="BS Computer Science" /></label>
				<label>Description (optional)<input class="input" bind:value={f_description} /></label>
				<p class="hint">Year levels and term structures are added in Step 2.</p>
			</div>
			<div class="nav-row">
				<span></span>
				<button
					class="btn btn-primary"
					data-testid="wizard-create-program"
					aria-busy={formBusy}
					disabled={formBusy}
					onclick={() => void submitNew()}
				>
					{formBusy ? 'Saving…' : 'Create and continue'}
				</button>
			</div>
		{/if}

		{#if chosen}
			<div class="resume-note">
				<AppIcon name="check" size={16} />
				<span>
					Currently set to <strong>{chosen.code}</strong>. Picking or creating a
					program replaces it (and clears the year picked in Step 3).
				</span>
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

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.chosen {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		background: var(--bg-muted);
	}

	.chosen-code {
		margin: 0;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.chosen-name {
		margin: 0.125rem 0;
		font-size: 0.9375rem;
		color: var(--text);
	}

	.chosen .muted {
		margin: 0;
	}

	.toggle-group {
		display: inline-flex;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		overflow: hidden;
		margin-bottom: 1.25rem;
	}

	.toggle-btn {
		padding: 0.625rem 1rem;
		border: none;
		background: var(--bg-card);
		color: var(--text-secondary);
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.toggle-btn.selected {
		background: var(--brand);
		color: var(--on-brand);
	}

	.toggle-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
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
	}

	.resume-note {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		margin-top: 1.25rem;
		font-size: 0.8125rem;
		color: var(--text-secondary);
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
