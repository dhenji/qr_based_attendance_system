<script lang="ts">
	// SkeletonCards
	// Placeholder stat/tile cards for dashboard-shaped pages: a short label
	// line, a large value line, and a secondary line. Self-contained card
	// surface, matching the 8px radius + token palette the pages use.
	import Skeleton from './Skeleton.svelte';

	interface Props {
		count?: number;
		label?: string;
	}

	let { count = 4, label = 'Loading…' }: Props = $props();
</script>

<div class="skeleton-cards" role="status" aria-busy="true">
	<span class="sr-only">{label}</span>
	{#each Array(count) as _}
		<div class="sk-card" aria-hidden="true">
			<Skeleton height={11} width="42%" />
			<Skeleton height={30} width="64%" />
			<Skeleton height={10} width="52%" />
		</div>
	{/each}
</div>

<style>
	.skeleton-cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
		gap: 1rem;
	}

	.sk-card {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 1.25rem 1.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
