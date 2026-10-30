<script lang="ts">
	const DEFAULT_OPTIONS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 150, 200, 300, 500, 1000];

	interface Props {
		value: number;
		min?: number;
		max?: number;
		options?: number[];
		disabled?: boolean;
		onChange: (value: number) => void;
		inheriting?: boolean;
		defaultChipLabel?: string;
		defaultValue?: number;
		onDefault?: () => void;
	}

	let {
		value,
		min = 1,
		max = 1000,
		options = DEFAULT_OPTIONS,
		disabled = false,
		onChange,
		inheriting = false,
		defaultChipLabel,
		defaultValue,
		onDefault
	}: Props = $props();

	type Chip = { kind: 'default' } | { kind: 'value'; v: number };

	const chips = $derived.by<Chip[]>(() => {
		const filtered = options.filter((o) => o >= min && o <= max).sort((a, b) => a - b);
		const clampedValue = Math.min(Math.max(value, min), max);
		let list = filtered.slice();
		if (!list.includes(clampedValue)) {
			list = [...list, clampedValue].sort((a, b) => a - b);
		}
		const dv = defaultValue ?? null;
		const out: Chip[] = [];
		let inserted = false;
		for (const o of list) {
			if (dv !== null && !inserted && o >= dv) {
				if (o === dv) {
					out.push({ kind: 'default' });
					inserted = true;
					continue;
				} else {
					out.push({ kind: 'default' });
					inserted = true;
				}
			}
			out.push({ kind: 'value', v: o });
		}
		if (dv !== null && !inserted) out.push({ kind: 'default' });
		// Only show default chip if label provided.
		if (!defaultChipLabel) {
			return out.filter((c) => c.kind !== 'default');
		}
		return out;
	});
</script>

<div class="radius-selector" class:disabled>
	<div class="selector-head">
		<span class="selector-label">selected radius</span>
	</div>
	<div class="chips-wrap">
		<div class="chips" role="group" aria-label="Geofence radius">
			{#each chips as chip, i (i)}
				{#if chip.kind === 'default'}
					<button
						type="button"
						class="chip default-chip"
						class:selected={inheriting}
						aria-pressed={inheriting}
						{disabled}
						onclick={() => onDefault?.()}
					>
						{defaultChipLabel}
					</button>
				{:else}
					<button
						type="button"
						class="chip"
						class:selected={!inheriting && value === chip.v}
						aria-pressed={!inheriting && value === chip.v}
						{disabled}
						onclick={() => onChange(chip.v)}
					>
						{chip.v}m
					</button>
				{/if}
			{/each}
		</div>
		<span class="scroll-fade" aria-hidden="true"></span>
	</div>
</div>

<style>
	.radius-selector {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		min-width: 0;
		margin-top: 0.5rem;
	}
	.radius-selector.disabled {
		opacity: 0.6;
	}
	.selector-head {
		display: flex;
		align-items: baseline;
		justify-content: flex-start;
		gap: 0.5rem;
	}
	.selector-label {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted, #666);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.chips-wrap {
		position: relative;
	}
	.chips {
		display: flex;
		flex-wrap: nowrap;
		gap: 0.375rem;
		overflow-x: auto;
		padding: 0.125rem 0.125rem 0.375rem;
		scrollbar-width: thin;
	}
	.chip {
		flex: 0 0 auto;
		padding: 0.375rem 0.625rem;
		border: 1px solid var(--border-strong, #aaa);
		border-radius: 6px;
		background: var(--bg-card, #fff);
		color: var(--text-strong, #111);
		font-size: 0.8125rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
	}
	.chip:hover:not(:disabled):not(.selected) {
		background: var(--bg-hover, #eee);
	}
	.chip.selected {
		background: var(--brand, #1e3a5f);
		color: var(--on-brand, #fff);
		border-color: var(--brand, #1e3a5f);
		box-shadow: 0 2px 6px rgba(30, 58, 95, 0.25);
	}
	.chip:disabled {
		cursor: not-allowed;
	}
	.scroll-fade {
		pointer-events: none;
		position: absolute;
		top: 0;
		right: 0;
		bottom: 0.375rem;
		width: 1.5rem;
		background: linear-gradient(to right, transparent, var(--bg-card, #fff));
	}

	.chip.default-chip {
		background: var(--bg-muted, #eef2f7);
		color: var(--text-secondary, #444);
		border-style: dashed;
	}
	.chip.default-chip.selected {
		background: var(--brand, #1e3a5f);
		color: var(--on-brand, #fff);
		border-style: solid;
	}
</style>