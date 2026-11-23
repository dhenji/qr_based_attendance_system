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
		/** Optional abort handler for long-running exports. When provided, Cancel
		 *  stays enabled while busy and invokes this instead of (just) closing. */
		onabort?: () => void;
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
		onabort,
		onclose,
	}: Props = $props();

	let busy = $state(false);
	let saved = $state(false);
	let errorMsg = $state<string | null>(null);

	const confirm = async () => {
		if (busy) return;
		busy = true;
		saved = false;
		errorMsg = null;
		try {
			await onconfirm();
			saved = true;
			await new Promise((resolve) => setTimeout(resolve, 2000));
		} catch (e) {
			errorMsg = e instanceof Error ? e.message : 'Export failed. Please try again.';
			await new Promise((resolve) => setTimeout(resolve, 2500));
		} finally {
			busy = false;
			saved = false;
			errorMsg = null;
			onclose();
		}
	};

	const cancel = () => {
		if (busy && !onabort) return;
		if (busy) onabort?.();
		onclose();
	};

	const escapeHandler = $derived(
		busy
			? onabort
				? () => {
						onabort?.();
						onclose();
					}
				: undefined
			: onclose
	);
</script>

<Modal
	{title}
	onclose={escapeHandler}
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

	{#if errorMsg}
		<p class="confirm-error" role="alert">{errorMsg}</p>
	{:else if saved}
		<p class="confirm-saved" role="status" aria-live="polite">Saved successfully.</p>
	{:else if busy}
		<p class="confirm-busy" role="status" aria-live="polite">{busyLabel}</p>
	{/if}

	{#snippet footer()}
		<button
			class="btn btn-ghost"
			type="button"
			data-testid="cancel-export"
			disabled={busy && !onabort}
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
			{saved ? 'Saved' : busy ? busyLabel : confirmLabel}
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

	.confirm-saved {
		margin: 0;
		font-size: 0.875rem;
		color: var(--success, #16a34a);
		font-weight: 600;
	}

	.confirm-error {
		margin: 0;
		font-size: 0.875rem;
		color: var(--danger, #dc2626);
		font-weight: 600;
	}

	.btn-ghost {
		background: transparent;
		color: var(--text-secondary);
	}
</style>
