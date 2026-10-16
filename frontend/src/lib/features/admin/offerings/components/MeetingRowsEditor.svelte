<script module lang="ts">
	// Shared meeting-rows state. Both offering create surfaces (the Setup
	// Wizard step 3 and the Offerings page modal) bind their rows to this
	// shape and validate each row with the shared `componentCreateSchema`,
	// so the two forms cannot drift apart again.

	export interface MeetingDraft {
		type: 'lecture' | 'lab';
		days: string;
		start: string;
		end: string;
		room: string;
		lat: string;
		lng: string;
	}

	export const blankMeeting = (type: 'lecture' | 'lab' = 'lecture'): MeetingDraft => ({
		type,
		days: '',
		start: '',
		end: '',
		room: '',
		lat: '',
		lng: '',
	});
</script>

<script lang="ts">
	import { DAY_OPTIONS } from '$lib/shared/constants/days';

	// One row per weekly meeting on a single day: each row has its own day,
	// type, time, and room — e.g. a lecture Monday plus a laboratory
	// Wednesday, or two sessions on the same day. One session per entry, so
	// the entry count is the sessions/week count. Validation lives with the
	// caller (per-row messages in `rowErrors`, parallel to `rows`); this
	// component only edits rows and reports structure. At least one row is
	// always kept — removal is offered only past the first — and growth
	// stops at `maxRows` (a week has 7 days; the backend caps
	// sessions_per_week at 7, so more rows could not submit anyway).

	interface Props {
		rows: MeetingDraft[];
		rowErrors?: string[];
		busy?: boolean;
		maxRows?: number;
		addLabel?: string;
	}

	let {
		rows = $bindable(),
		rowErrors = [],
		busy = false,
		maxRows = 7,
		addLabel = 'Add another meeting',
	}: Props = $props();

	const removeAt = (index: number) => {
		rows = rows.filter((_, j) => j !== index);
	};

	// A new row inherits the last row's type (adding a second lecture day
	// is the common multi-row action); day and time stay blank so an
	// accidental exact duplicate can never be created.
	const addRow = () => {
		if (rows.length >= maxRows) return;
		const lastType = rows.length > 0 ? rows[rows.length - 1].type : 'lecture';
		rows = [...rows, blankMeeting(lastType)];
	};
</script>

<div class="field">
	<span class="form-label">Class meetings</span>
	<p class="hint">
		One row, one day: each meeting has its own day, type, time, and room. Add
		another row for each additional day or time — e.g. a lecture Monday plus a
		laboratory Wednesday, or two sessions on the same day. Each row counts as
		one session per week.
	</p>
</div>
{#each rows as m, i (i)}
	<div class="meeting-box">
		<div class="meeting-head">
			<span class="meeting-title">Meeting {i + 1}</span>
			{#if rows.length > 1}
				<button
					class="link"
					type="button"
					disabled={busy}
					onclick={() => removeAt(i)}
				>
					Remove
				</button>
			{/if}
		</div>
		{#if rowErrors[i]}
			<p class="error" role="alert">{rowErrors[i]}</p>
		{/if}
		<div class="grid2">
			<label>Day
				<select class="input" bind:value={m.days} disabled={busy} aria-label={`Meeting ${i + 1} day`}>
					<option value="">Pick a day…</option>
					{#each DAY_OPTIONS as day (day.code)}
						<option value={day.code}>{day.label}</option>
					{/each}
				</select>
			</label>
			<label>Type
				<select class="input" bind:value={m.type} disabled={busy}>
					<option value="lecture">Lecture</option>
					<option value="lab">Laboratory</option>
				</select>
			</label>
		</div>
		<label>Room (optional)<input class="input" bind:value={m.room} placeholder="Lab 101" disabled={busy} /></label>
		<div class="grid2">
			<label>Start time<input class="input" type="time" bind:value={m.start} disabled={busy} /></label>
			<label>End time<input class="input" type="time" bind:value={m.end} disabled={busy} /></label>
		</div>
		<div class="grid2">
			<label>Latitude (optional)<input class="input" inputmode="decimal" bind:value={m.lat} placeholder="14.5995" disabled={busy} /></label>
			<label>Longitude (optional)<input class="input" inputmode="decimal" bind:value={m.lng} placeholder="120.9842" disabled={busy} /></label>
		</div>
		{#if m.type === 'lab'}
			<p class="hint">Laboratory sessions enforce the geofence: opening one without coordinates fails.</p>
		{/if}
	</div>
{/each}
{#if rows.length < maxRows}
	<button class="btn btn-secondary" type="button" disabled={busy} onclick={addRow}>
		{addLabel}
	</button>
{:else}
	<p class="hint">Up to {maxRows} meetings per offering — further meetings go on the offering detail page.</p>
{/if}

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.form-label {
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		color: var(--text-secondary);
		margin-bottom: 0.375rem;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin: 0;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
	}

	.meeting-box {
		display: flex;
		flex-direction: column;
		gap: 0.875rem;
		padding: 1rem;
		background: var(--bg-page);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.meeting-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.meeting-title {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-strong);
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

	.link:hover:not(:disabled) {
		text-decoration: underline;
	}

	.link:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
		width: 100%;
		box-sizing: border-box;
	}

	.input:focus {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.meeting-box label {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
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

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-secondary {
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		color: var(--text-strong);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--divider);
	}

	@media (max-width: 640px) {
		.grid2 {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
