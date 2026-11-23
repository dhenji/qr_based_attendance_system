<!-- features/admin/programs/components/TermRowsEditor.svelte -->
<script lang="ts">
	import { DEFAULT_TERM_WEEKS, TERM_CODES, TERM_LABELS } from '$lib/shared/constants/terms';

	export type TermEditorRow = {
		code: string;
		label: string;
		weeks?: number;
		existing?: boolean;
	};

	let {
		rows = $bindable<TermEditorRow[]>([]),
		busy = false,
		lockCodeForExisting = false,
		emptyMessage = 'No terms yet. Add one below, or save empty — a termless year cannot back offerings yet.',
		addLabel = 'Add term',
		removeLabel = 'Remove',
		showCounter = true,
	}: {
		rows?: TermEditorRow[];
		busy?: boolean;
		lockCodeForExisting?: boolean;
		emptyMessage?: string;
		addLabel?: string;
		removeLabel?: string;
		showCounter?: boolean;
	} = $props();

	const isCanonicalCode = (value: string): boolean =>
		(TERM_CODES as readonly string[]).includes(value);

	const isCanonicalLabel = (value: string): boolean =>
		(TERM_LABELS as readonly string[]).includes(value);

	const nextRow = (): TermEditorRow => {
		const usedCodes = new Set(rows.map((row) => row.code));
		const usedLabels = new Set(rows.map((row) => row.label));
		return {
			code: (TERM_CODES as readonly string[]).find((code) => !usedCodes.has(code)) ?? TERM_CODES[0],
			label:
				(TERM_LABELS as readonly string[]).find((label) => !usedLabels.has(label)) ?? TERM_LABELS[0],
			weeks: DEFAULT_TERM_WEEKS,
			existing: false,
		};
	};

	const duplicateCodes = $derived.by<Set<string>>(() => {
		const seen = new Set<string>();
		const duplicates = new Set<string>();
		for (const row of rows) {
			if (seen.has(row.code)) duplicates.add(row.code);
			seen.add(row.code);
		}
		return duplicates;
	});

	const hasDuplicateCodes = $derived(duplicateCodes.size > 0);
	const usedCodeCount = $derived(new Set(rows.map((row) => row.code)).size);
	const allCodesUsed = $derived(usedCodeCount >= TERM_CODES.length);

	function addRow(): void {
		if (busy || allCodesUsed) return;
		rows = [...rows, nextRow()];
	}

	function removeRow(index: number): void {
		if (busy) return;
		rows = rows.filter((_, rowIndex) => rowIndex !== index);
	}
</script>

<div class="term-editor" aria-busy={busy}>
	{#if rows.length === 0}
		<p class="muted empty">{emptyMessage}</p>
	{/if}

	{#each rows as row, index (index)}
		<article class="term-row">
			<header class="term-row-head">
				<span class="term-row-title">Term {index + 1}</span>
				<button
					type="button"
					class="btn btn-ghost btn-sm"
					disabled={busy}
					onclick={() => removeRow(index)}
				>
					{removeLabel}
				</button>
			</header>

			<div class="term-fields">
				<label>
					<span class="field-label">Term code (saved value)</span>
					<select
						class="input"
						bind:value={rows[index].code}
						disabled={busy || (lockCodeForExisting && Boolean(row.existing))}
						title={lockCodeForExisting && row.existing
							? 'Term code cannot be changed after creation; add a new term instead.'
							: undefined}
					>
						{#if !isCanonicalCode(row.code)}
							<option value={row.code}>{row.code} (custom)</option>
						{/if}
						{#each TERM_CODES as code (code)}
							<option value={code}>{code}</option>
						{/each}
					</select>
					{#if lockCodeForExisting && row.existing}
						<span class="hint">Saved term code — kept stable for offerings.</span>
					{/if}
				</label>

				<label>
					<span class="field-label">Display name</span>
					<select
						class="input"
						bind:value={rows[index].label}
						disabled={busy}
					>
						{#if !isCanonicalLabel(row.label)}
							<option value={row.label}>{row.label} (custom)</option>
						{/if}
						{#each TERM_LABELS as label (label)}
							<option value={label}>{label}</option>
						{/each}
					</select>
				</label>

				<label>
					<span class="field-label">Session weeks</span>
					<input
						class="input"
						type="number"
						min="1"
						max="52"
						inputmode="numeric"
						placeholder={String(DEFAULT_TERM_WEEKS)}
						bind:value={rows[index].weeks}
						disabled={busy}
					/>
					<span class="hint">How many weeks this term runs. Offerings inherit it.</span>
				</label>
			</div>
		</article>
	{/each}

	<div class="term-editor-toolbar">
		<button
			type="button"
			class="btn btn-secondary btn-sm"
			disabled={busy || allCodesUsed}
			title={allCodesUsed ? 'All term codes are already used' : undefined}
			onclick={addRow}
		>
			{addLabel}
		</button>
		{#if showCounter}
			<span class="muted counter">{usedCodeCount} of {TERM_CODES.length} codes used</span>
		{/if}
	</div>

	{#if hasDuplicateCodes}
		<p class="error" role="alert">Term codes must be unique within a year.</p>
	{/if}
</div>

<style>
	.term-editor {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.empty {
		margin: 0;
	}

	.term-row {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
		padding: 0.75rem;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--bg-muted, var(--bg-card));
	}

	.term-row-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.term-row-title {
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text-strong);
	}

	.term-fields {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	.field-label {
		display: block;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: 0.375rem;
	}

	.input {
		width: 100%;
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

	.input:disabled {
		background: var(--divider);
		color: var(--text-muted);
		cursor: not-allowed;
	}

	.hint {
		display: block;
		margin-top: 0.25rem;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.term-editor-toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.counter {
		font-size: 0.75rem;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
	}

	.btn-sm {
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
	}

	@media (max-width: 640px) {
		.term-fields {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
