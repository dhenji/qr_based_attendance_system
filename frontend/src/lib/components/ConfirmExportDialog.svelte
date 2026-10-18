<script lang="ts">
	// Shared confirmation dialog for ALL data export entry points.
	//
	// Built on `lib/components/Modal.svelte` (the preferred shell for new
	// dialogs), so it inherits focus trap, Escape handling, focus restore,
	// scroll lock, and `aria-modal` for free. The export itself is only ever
	// invoked from `confirm()` — opening the dialog never triggers a request,
	// and Cancel/Escape close it with zero side effects.
	//
	// `onconfirm` is the page's EXISTING export function (untouched). It may be
	// sync or async; while it runs the dialog stays open in a busy state, which
	// is what blocks duplicate submissions.
	import Modal from '$lib/components/Modal.svelte';

	interface Detail {
		label: string;
		value: string;
	}

	interface Props {
		/** Dialog heading; also the accessible name. */
		title?: string;
		/** Body copy. Default is the generic export confirmation copy. */
		message?: string;
		/** Optional contextual rows (export type, format, row counts, filters). */
		details?: Detail[];
		/** Label for the confirm button. */
		confirmLabel?: string;
		/** Label shown on the confirm button while processing. */
		busyLabel?: string;
		/** The existing export flow. Only invoked when the user confirms. */
		onconfirm: () => void | Promise<void>;
		/** Close the dialog (Cancel / Escape / after settle). */
		onclose: () => void;
	}

	let {
		title = 'Confirm Data Export',
		message = 'Are you sure you want to export this data? The file will be generated and downloaded after you confirm.',
		details = [],
		confirmLabel = 'Confirm Export',
		busyLabel = 'Exporting…',
		onconfirm,
		onclose,
	}: Props = $props();

	let busy = $state(false);

	const confirm = async () => {
		if (busy) return;
		busy = true;
		try {
			await onconfirm();
		} finally {
			busy = false;
			onclose();
		}
	};

	const cancel = () => {
		if (busy) return;
		onclose();
	};
</script>

<Modal
	{title}
	onclose={busy ? undefined : onclose}
	closeOnBackdrop={false}
>
	<p class="confirm-message">{message}</p>

	{#if details.length > 0}
		<dl class="confirm-details">
			{#each details as d (d.label)}
				<div class="confirm-row">
					<dt>{d.label}</dt>
					<dd>{d.value}</dd>
				</div>
			{/each}
		</dl>
	{/if}

	{#if busy}
		<p class="confirm-busy" role="status" aria-live="polite">{busyLabel}</p>
	{/if}

	{#snippet footer()}
		<button
			class="btn btn-ghost"
			type="button"
			data-testid="cancel-export"
			disabled={busy}
			onclick={cancel}
		>
			Cancel
		</button>
		<button
			class="btn btn-primary"
			type="button"
			data-testid="confirm-export"
			disabled={busy}
			aria-busy={busy}
			onclick={() => void confirm()}
		>
			{busy ? busyLabel : confirmLabel}
		</button>
	{/snippet}
</Modal>

<style>
	.confirm-message {
		margin: 0;
		font-size: 0.9375rem;
		color: var(--text-secondary);
	}

	.confirm-details {
		margin: 0;
		display: grid;
		gap: 0.375rem;
		padding: 0.75rem;
		border-radius: 8px;
		background: var(--bg-muted);
		border: 1px solid var(--border);
	}

	.confirm-row {
		display: flex;
		gap: 0.75rem;
		font-size: 0.875rem;
	}

	.confirm-row dt {
		font-weight: 600;
		color: var(--text);
		min-width: 6rem;
	}

	.confirm-row dd {
		margin: 0;
		color: var(--text-secondary);
	}

	.confirm-busy {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.625rem 1.125rem;
		border: 1px solid transparent;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
		transition: background 0.15s ease;
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
		color: var(--on-brand);
	}

	.btn-ghost {
		background: transparent;
		color: var(--text-secondary);
	}
</style>
