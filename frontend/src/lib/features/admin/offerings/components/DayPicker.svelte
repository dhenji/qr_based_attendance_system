<script lang="ts">
	import { DAY_OPTIONS } from '$lib/shared/constants/days';

	// Multi-day picker for one meeting row. Binds the canonical days string
	// (a subset of MTWHFSU in weekday order, e.g. "MWF"): every toggle rewrites
	// it, so the caller's derived weekly totals recalculate immediately. One
	// checked day is one weekly session; several checked days share the row's
	// time, and each meeting row keeps its own independent set. Callers only
	// render this while the
	// bound value stays inside the MTWHFSU alphabet — legacy free text with
	// other characters keeps a plain input instead, so toggling can never
	// silently drop characters it cannot represent.

	interface Props {
		value?: string;
		disabled?: boolean;
		legend?: string;
	}

	let { value = $bindable(''), disabled = false, legend = 'Days' }: Props = $props();

	const ORDER = 'MTWHFSU';

	const upper = (s: string): string[] => s.toUpperCase().split('');

	const isChecked = (code: string): boolean => upper(value).includes(code);

	const toggle = (code: string) => {
		const next = isChecked(code)
			? upper(value).filter((ch) => ch !== code)
			: [...upper(value), code];
		value = [...new Set(next)]
			.filter((ch) => ORDER.includes(ch))
			.sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))
			.join('');
	};
</script>

<fieldset class="picker" {disabled}>
	<legend>{legend} <span class="pick-hint">pick at least one</span></legend>
	<div class="days">
		{#each DAY_OPTIONS as day (day.code)}
			<label class="day" class:on={isChecked(day.code)} title={day.label}>
				<input
					type="checkbox"
					checked={isChecked(day.code)}
					{disabled}
					onchange={() => toggle(day.code)}
					aria-label={day.label}
				/>
				<span aria-hidden="true">{day.code}</span>
			</label>
		{/each}
	</div>
</fieldset>

<style>
	.picker {
		border: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.picker legend {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		padding: 0;
	}

	.pick-hint {
		font-weight: 400;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.days {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.day {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.625rem;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-secondary);
		background: var(--bg-card);
		cursor: pointer;
	}

	.day.on {
		border-color: var(--brand);
		color: var(--brand);
		background: var(--bg-muted);
	}

	.day input {
		accent-color: var(--brand);
		margin: 0;
	}

	.day input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
