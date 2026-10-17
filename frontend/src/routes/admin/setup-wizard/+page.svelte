<script lang="ts">
	import { onMount } from 'svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import {
		WIZARD_STEPS,
		canReachStep,
		goToStep,
		loadWizard,
		resetWizard,
		wizardState,
		type WizardStep,
	} from '$lib/features/admin/setup-wizard/store.svelte';
	import StepProgram from '$lib/features/admin/setup-wizard/StepProgram.svelte';
	import StepStructure from '$lib/features/admin/setup-wizard/StepStructure.svelte';
	import StepOffering from '$lib/features/admin/setup-wizard/StepOffering.svelte';

	// Setup Wizard shell: the guided Program -> Structure -> Offerings flow.
	// The breadcrumb bar is the whole navigation model — steps unlock in
	// order (step 1 first, then 2 and 3 once a program is bound), completed
	// steps stay clickable, and progress resumes after a reload via the
	// store's localStorage position. Each step component owns its own data;
	// this shell only renders the current one and offers a guarded reset.

	let confirmReset = $state(false);

	onMount(() => {
		loadWizard();
	});

	// Defensive correction: if the store ever holds step 2/3 without a
	// program (e.g. storage edited by hand), bounce to step 1 instead of
	// rendering a step whose data cannot load. No loop: goToStep(1) clears
	// the condition that fires this effect.
	$effect(() => {
		if (wizardState.step > 1 && wizardState.programId === null) {
			goToStep(1);
		}
	});

	const stateOf = (n: WizardStep): 'done' | 'current' | 'todo' =>
		n < wizardState.step ? 'done' : n === wizardState.step ? 'current' : 'todo';

	const clickStep = (n: WizardStep) => {
		confirmReset = false;
		goToStep(n);
	};

	const askReset = () => {
		confirmReset = true;
	};

	const doReset = () => {
		confirmReset = false;
		resetWizard();
	};
</script>

<div class="page">
	<header class="header">
		<div>
			<h1>Setup Wizard</h1>
			<p class="muted">
				One guided path from a new program to scheduled offerings. Progress is saved —
				leave and come back any time.
			</p>
		</div>
		<div class="header-actions">
			{#if confirmReset}
				<span class="reset-confirm" role="alert">
					Start over? Your saved position is cleared (created records stay).
				</span>
				<button class="btn btn-secondary" onclick={() => (confirmReset = false)}>Keep</button>
				<button class="btn btn-danger" data-testid="wizard-reset-confirm" onclick={doReset}>
					Start over
				</button>
			{:else}
				<button class="btn btn-secondary" onclick={askReset}>Start over</button>
			{/if}
		</div>
	</header>

	<nav class="steps" aria-label="Setup progress">
		{#each WIZARD_STEPS as s, i (s.n)}
			{#if i > 0}
				<span class="step-sep" aria-hidden="true">→</span>
			{/if}
			<button
				class="step"
				class:done={stateOf(s.n) === 'done'}
				class:current={stateOf(s.n) === 'current'}
				disabled={!canReachStep(s.n)}
				title={canReachStep(s.n) ? s.blurb : 'Finish the earlier steps first'}
				aria-current={stateOf(s.n) === 'current' ? 'step' : undefined}
				onclick={() => clickStep(s.n)}
			>
				<span class="step-dot" aria-hidden="true">
					{#if stateOf(s.n) === 'done'}
						<AppIcon name="check" size={16} />
					{:else}
						{s.n}
					{/if}
				</span>
				<span class="step-text">
					<span class="step-title">{s.title}</span>
					<span class="step-blurb">{s.blurb}</span>
				</span>
			</button>
		{/each}
	</nav>

	{#key wizardState.step}
		{#if wizardState.step === 1}
			<StepProgram />
		{:else if wizardState.step === 2}
			<StepStructure />
		{:else}
			<StepOffering />
		{/if}
	{/key}
</div>

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
		align-items: center;
		flex-wrap: wrap;
	}

	.reset-confirm {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.steps {
		display: flex;
		align-items: stretch;
		gap: 0.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.75rem;
		box-shadow: var(--shadow-sm);
	}

	.step-sep {
		align-self: center;
		color: var(--text-muted);
		font-weight: 700;
	}

	.step {
		flex: 1 1 0;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.625rem 0.875rem;
		border: 1px solid transparent;
		border-radius: 8px;
		background: transparent;
		font-family: inherit;
		text-align: left;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.step:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.step:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.step:disabled {
		opacity: 0.55;
		cursor: not-allowed;
	}

	.step.current {
		border-color: var(--brand);
		background: var(--bg-muted);
	}

	.step-dot {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		flex-shrink: 0;
		border-radius: 999px;
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-muted);
		background: var(--divider);
	}

	.step.current .step-dot {
		color: var(--on-brand);
		background: var(--brand);
	}

	.step.done .step-dot {
		color: var(--success);
		background: var(--success-bg);
	}

	.step-text {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		min-width: 0;
	}

	.step-title {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.step-blurb {
		font-size: 0.75rem;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
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

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover {
		background: var(--divider);
	}

	.btn-danger {
		background: var(--danger);
		border: 1px solid var(--danger);
		color: var(--on-brand);
	}

	.btn-danger:hover {
		background: var(--danger-strong);
	}

	@media (max-width: 760px) {
		.steps {
			flex-direction: column;
		}

		.step-sep {
			display: none;
		}

		.step-blurb {
			white-space: normal;
		}
	}
</style>
