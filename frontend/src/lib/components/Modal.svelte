<script lang="ts">
	// Preferred dialog shell for NEW modals: correct semantics, focus trap,
	// Escape, and focus restore, all from lib/shared/actions/focusTrap.
	//
	// The app's existing ~20 hand-rolled modals keep their own markup and get
	// the action applied directly (`use:trapFocus`) rather than being rewritten
	// onto this component — see the note at the top of focusTrap.ts. Migrate a
	// dialog onto this only when its styles are already token-driven.
	import type { Snippet } from 'svelte';
	import { trapFocus } from '$lib/shared/actions/focusTrap';

	interface Props {
		/** Heading text; also the dialog's accessible name. */
		title: string;
		/** Escape handler. Omit to make the dialog Escape-inert. */
		onclose?: () => void;
		/** Clicking the backdrop calls `onclose`. Default false — a destructive
		 *  dialog should not close on a stray outside click. */
		closeOnBackdrop?: boolean;
		/** Extra class on the panel, for size variants. */
		panelClass?: string;
		children: Snippet;
		/** Rendered inside a `.modal-actions` row at the bottom. */
		footer?: Snippet;
	}

	let {
		title,
		onclose,
		closeOnBackdrop = false,
		panelClass = '',
		children,
		footer,
	}: Props = $props();

	const titleId = $props.id();
</script>

<div
	class="modal-overlay"
	role="presentation"
	onclick={(event) => {
		if (closeOnBackdrop && onclose && event.target === event.currentTarget) onclose();
	}}
>
	<div
		class="modal {panelClass}"
		role="dialog"
		aria-modal="true"
		aria-labelledby={titleId}
		tabindex="-1"
		use:trapFocus={{ onEscape: onclose }}
	>
		<h2 id={titleId} class="modal-title">{title}</h2>
		{@render children()}
		{#if footer}
			<div class="modal-actions">{@render footer()}</div>
		{/if}
	</div>
</div>

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: var(--overlay);
	}

	.modal {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		width: 100%;
		max-width: 420px;
		max-height: 90vh;
		overflow-y: auto;
		padding: 1.5rem;
		border-radius: 12px;
		background: var(--bg-card);
		color: var(--text-strong);
		box-shadow: var(--shadow-lg);
	}

	.modal-title {
		margin: 0;
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--text);
	}

	.modal-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.75rem;
	}
</style>