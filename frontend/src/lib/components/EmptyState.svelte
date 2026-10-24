<script lang="ts">
	// EmptyState
	// Shared "nothing here yet" treatment for list pages: muted icon medallion,
	// title, hint, and an optional action (usually a CTA button). Copy stays
	// with the page — this component only owns the visual language.
	import type { ComponentProps, Snippet } from 'svelte';
	import AppIcon from './AppIcon.svelte';

	interface Props {
		icon?: ComponentProps<typeof AppIcon>['name'];
		title: string;
		hint?: string;
		/** Call-to-action content, e.g. an import/add button. */
		children?: Snippet;
	}

	let { icon = 'file', title, hint, children }: Props = $props();
</script>

<div class="empty-state">
	<span class="icon-wrap"><AppIcon name={icon} size={28} /></span>
	<p class="title">{title}</p>
	{#if hint}
		<p class="hint">{hint}</p>
	{/if}
	{#if children}
		<div class="actions">{@render children()}</div>
	{/if}
</div>

<style>
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		gap: 0.5rem;
		padding: 2.75rem 1.5rem;
	}

	.icon-wrap {
		display: grid;
		place-items: center;
		width: 56px;
		height: 56px;
		margin-bottom: 0.375rem;
		border-radius: 50%;
		background: var(--bg-muted);
		color: var(--text-muted);
	}

	.title {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-strong);
	}

	.hint {
		margin: 0;
		max-width: 42ch;
		font-size: 0.875rem;
		line-height: 1.5;
		color: var(--text-muted);
	}

	.actions {
		margin-top: 0.75rem;
	}
</style>
