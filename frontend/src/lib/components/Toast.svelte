<script lang="ts">
	// Toast
	// Shared in-app notification pill. Student and professor layouts each
	// carried an identical copy of this markup + CSS; the admin layout had
	// none. One component, mounted by all three layouts.
	//
	// The root keeps the `.toast` class because theme.css hides `.toast` in
	// `@media print` — renaming it would leak the pill onto printed reports.
	interface Props {
		message: string;
		onDismiss?: () => void;
		dismissLabel?: string;
	}

	let { message, onDismiss, dismissLabel = 'Dismiss' }: Props = $props();
</script>

<p class="toast" role="status">
	<span class="toast-text">{message}</span>
	{#if onDismiss}
		<button
			type="button"
			class="toast-dismiss"
			onclick={() => onDismiss?.()}
			aria-label={dismissLabel}
		>
			{dismissLabel}
		</button>
	{/if}
</p>

<style>
	.toast {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 0.75rem 1.5rem 0;
		padding: 0.625rem 0.875rem;
		border-radius: 8px;
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		box-shadow: var(--shadow-sm);
		font-size: 0.875rem;
		color: var(--text-strong);
	}

	.toast-text {
		flex: 1;
		min-width: 0;
	}

	.toast-dismiss {
		border: 0;
		background: none;
		padding: 0;
		color: var(--accent);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
	}
</style>
