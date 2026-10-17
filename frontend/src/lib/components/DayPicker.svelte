<script lang="ts">
	// DayPicker
	// Checkbox group for `schedule_days`, Monday to Sunday. Emits the compact
	// code string the backend interprets (e.g. "MWF").
	//
	// The codes are NOT the obvious initials: student/service.py::_meets_on
	// reads the string per character with T=Tuesday/H=Thursday (T was taken),
	// S=Saturday/U=Sunday (S was taken). Multi-letter codes like "TH" or
	// "SUN" would match extra days, so each day maps to exactly one letter
	// here and the stored string is rebuilt in canonical Mon..Sun order.
	// Unknown letters in an incoming value (legacy free text) are dropped on
	// the next toggle rather than rendered.
	interface DayOption {
		code: string;
		label: string;
	}

	const DAYS: DayOption[] = [
		{ code: 'M', label: 'Monday' },
		{ code: 'T', label: 'Tuesday' },
		{ code: 'W', label: 'Wednesday' },
		{ code: 'H', label: 'Thursday' },
		{ code: 'F', label: 'Friday' },
		{ code: 'S', label: 'Saturday' },
		{ code: 'U', label: 'Sunday' },
	];

	let { value = $bindable('') }: { value: string } = $props();

	const isChecked = (code: string): boolean => value.toUpperCase().includes(code);

	const toggle = (code: string): void => {
		const current = new Set(value.toUpperCase().split(''));
		if (current.has(code)) {
			current.delete(code);
		} else {
			current.add(code);
		}
		value = DAYS.map((d) => d.code)
			.filter((c) => current.has(c))
			.join('');
	};
</script>

<fieldset class="day-picker">
	<legend class="form-label">Schedule days</legend>
	<div class="days" role="group" aria-label="Schedule days, Monday to Sunday">
		{#each DAYS as day (day.code)}
			<label class="day" class:checked={isChecked(day.code)} title={`${day.label} (${day.code})`}>
				<input
					type="checkbox"
					class="sr"
					checked={isChecked(day.code)}
					onchange={() => toggle(day.code)}
				/>
				<span class="day-name">{day.label}</span>
				<span class="day-code" aria-hidden="true">{day.code}</span>
			</label>
		{/each}
	</div>
	<p class="hint" aria-live="polite">
		{#if value}
			Stored as “{value.toUpperCase()}”.
		{:else}
			Pick at least one day.
		{/if}
	</p>
</fieldset>

<style>
	.day-picker {
		border: none;
		padding: 0;
		margin: 0;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		padding: 0;
		margin-bottom: 0.375rem;
	}

	.days {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.day {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border-strong);
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		background: var(--bg-card);
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
	}

	.day:hover {
		background: var(--bg-hover);
	}

	.day:focus-within {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.day.checked {
		color: var(--on-brand);
		background: var(--brand);
		border-color: var(--brand);
	}

	.day-code {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1.375rem;
		height: 1.375rem;
		padding-inline: 0.25rem;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 700;
		background: var(--divider);
		color: var(--text-secondary);
	}

	.day.checked .day-code {
		background: rgba(255, 255, 255, 0.25);
		color: var(--on-brand);
	}

	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0.5rem 0 0;
	}
</style>
