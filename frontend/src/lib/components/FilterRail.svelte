<script lang="ts">
	// Shared analytics filter rail (issue #497).
	//
	// Presentational only: the parent owns every filter value, the course
	// search, the advanced-open state, and the fetch/apply calls. The rail
	// contributes the common shell — scope grid, date presets, from/to dates,
	// reset, advanced toggle, and the advanced panel container. Parents pass
	// their entity-specific controls through the `scope` and `advanced`
	// snippets, so both analytics surfaces share one layout without a
	// lowest-common-denominator prop list.
	import type { Snippet } from 'svelte';
	import { DATE_PRESETS, type DatePresetId, type PresetId } from '$lib/components/filter-rail';

	let {
		scope,
		advanced,
		preset,
		from,
		to,
		advancedOpen,
		advancedActiveCount = 0,
		idPrefix,
		advancedId = 'advanced-filters',
		onPreset,
		onFromChange,
		onToChange,
		onReset,
		onAdvancedToggle,
		onClearAdvanced
	}: {
		scope: Snippet;
		advanced?: Snippet;
		preset: DatePresetId;
		from: string;
		to: string;
		advancedOpen: boolean;
		advancedActiveCount?: number;
		idPrefix: string;
		advancedId?: string;
		onPreset: (preset: PresetId) => void;
		onFromChange: (value: string) => void;
		onToChange: (value: string) => void;
		onReset: () => void;
		onAdvancedToggle: () => void;
		onClearAdvanced: () => void;
	} = $props();
</script>

<div class="filter-rail">
	<p class="eyebrow">Scope</p>
	<div class="filter-grid">
		{@render scope()}
	</div>

	<p class="eyebrow time-range">Time range</p>
	<div class="preset-row">
		{#each DATE_PRESETS as p (p.id)}
			<button
				class="btn btn-ghost"
				class:selected={preset === p.id}
				type="button"
				aria-pressed={preset === p.id}
				onclick={() => onPreset(p.id)}
			>
				{p.label}
			</button>
		{/each}
	</div>
	<div class="filter-grid filter-grid-4">
		<div class="field">
			<label class="form-label" for={`${idPrefix}-from`}>From date</label>
			<input
				id={`${idPrefix}-from`}
				class="form-input"
				type="date"
				value={from}
				onchange={(e) => onFromChange(e.currentTarget.value)}
			/>
		</div>
		<div class="field">
			<label class="form-label" for={`${idPrefix}-to`}>To date</label>
			<input
				id={`${idPrefix}-to`}
				class="form-input"
				type="date"
				value={to}
				onchange={(e) => onToChange(e.currentTarget.value)}
			/>
		</div>
		<div class="field">
			<span class="form-label">&nbsp;</span>
			<button class="btn btn-secondary" type="button" onclick={onReset}>Reset filters</button>
		</div>
		<div class="field">
			<span class="form-label">&nbsp;</span>
			<button
				class="btn btn-secondary advanced-toggle"
				type="button"
				aria-expanded={advancedOpen}
				aria-controls={advancedId}
				onclick={onAdvancedToggle}
			>
				Advanced filters{#if advancedActiveCount > 0} ({advancedActiveCount}){/if}
			</button>
		</div>
	</div>

	{#if advancedOpen && advanced}
		<div id={advancedId} class="advanced-panel">
			{@render advanced()}
			<div class="field">
				<span class="form-label">&nbsp;</span>
				<button class="btn btn-secondary" type="button" onclick={onClearAdvanced}>
					Clear advanced
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	/* The rail is one flex child of the page's `.filters` container; forcing a
	   full-width basis keeps the stacked rows aligned regardless of whether the
	   parent uses a card section or a bare div. */
	.filter-rail {
		flex: 1 1 100%;
		min-width: 0;
	}

	.eyebrow {
		margin: 0 0 0.5rem;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-muted);
	}

	.time-range {
		margin-top: 1rem;
	}

	.filter-grid {
		display: grid;
		gap: 1rem;
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}

	.filter-grid-4 {
		grid-template-columns: repeat(4, minmax(0, 1fr));
	}

	.filter-grid .btn {
		width: 100%;
		justify-content: center;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.4375rem;
		min-width: 0;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
	}

	.preset-row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		align-items: center;
		margin: 0.75rem 0;
	}

	/* Preset chips: the shared .btn-ghost is the base control, but the rail
	   intentionally uses the card surface plus a visible border so the chips
	   read as a segmented control against the filter card. */
	.btn-ghost {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
		padding: 0.5rem 0.9rem;
		font-size: 0.875rem;
		border-radius: 8px;
	}

	.btn-ghost:hover:not(:disabled) {
		background: var(--bg-hover, var(--divider));
	}

	.btn-ghost.selected {
		background: var(--brand);
		border-color: var(--brand);
		color: var(--on-brand);
	}

	.btn-ghost.selected:hover:not(:disabled) {
		background: var(--brand-hover);
		border-color: var(--brand-hover);
		color: var(--on-brand);
	}

	.advanced-toggle {
		justify-content: center;
	}

	.advanced-panel {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		align-items: center;
		margin-top: 0.75rem;
		padding: 0.75rem;
		border: 1px dashed var(--border);
		border-radius: 8px;
		background: var(--bg-muted, transparent);
	}

	@media (max-width: 860px) {
		.filter-grid,
		.filter-grid-4 {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 560px) {
		.filter-grid,
		.filter-grid-4 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
