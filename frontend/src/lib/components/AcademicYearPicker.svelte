<script lang="ts">
	// Reusable academic-year selector. Emits the canonical `YYYY-YYYY` form the
	// backend and existing data already use (e.g. 2026-2027), so it never
	// introduces a new storage format. Native <select> keeps keyboard
	// navigation and screen-reader support without a new dependency.

	interface Props {
		value: string;
		disabled?: boolean;
		minOffset?: number;
		maxOffset?: number;
		id?: string;
		ariaLabel?: string;
	}

	let {
		value = $bindable(''),
		disabled = false,
		minOffset = -5,
		maxOffset = 5,
		id,
		ariaLabel = 'Academic year',
	}: Props = $props();

	const currentStart = $derived.by(() => {
		const now = new Date();
		const year = now.getFullYear();
		return now.getMonth() + 1 >= 8 ? year : year - 1;
	});

	const options = $derived.by(() => {
		const lo = currentStart + (minOffset ?? -5);
		const hi = currentStart + (maxOffset ?? 5);
		const starts = new Set<number>();
		for (let y = lo; y <= hi; y += 1) starts.add(y);

		// Keep an existing (possibly non-canonical) selection representable so
		// the field never silently blanks out.
		const match = value?.match(/^(\d{4})-(\d{4})$/);
		if (match) starts.add(Number(match[1]));
		const list = [...starts].sort((a, b) => a - b).map((y) => ({
			value: `${y}-${y + 1}`,
			label: `${y}-${y + 1}`,
		}));
		if (value && !list.some((o) => o.value === value)) {
			list.unshift({ value, label: value });
		}
		return list;
	});
</script>

<select
	class="input"
	{id}
	bind:value
	{disabled}
	aria-label={ariaLabel}
>
	{#each options as opt (opt.value)}
		<option value={opt.value}>{opt.label}</option>
	{/each}
</select>

<style>
	.input {
		padding: 0.625rem 0.875rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.9375rem;
		font-family: inherit;
		color: var(--text-strong);
		background: var(--bg-card);
		width: 100%;
		box-sizing: border-box;
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}
</style>