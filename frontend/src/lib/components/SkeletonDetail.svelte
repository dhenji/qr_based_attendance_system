<script lang="ts">
	// SkeletonDetail
	// Placeholder card for detail/profile/settings pages: a title line plus
	// label/value rows that mirror a profile <dl> or a settings form.
	// Self-contained card surface, same tokens as the rest of the skeletons.
	import Skeleton from './Skeleton.svelte';

	interface Props {
		rows?: number;
		label?: string;
		/** Drop the card surface when nesting inside an existing card. */
		bare?: boolean;
	}

	let { rows = 5, label = 'Loading…', bare = false }: Props = $props();
</script>

<div class="skeleton-detail" class:bare role="status" aria-busy="true">
	<span class="sr-only">{label}</span>
	<Skeleton height={18} width="36%" />
	<div class="rows" aria-hidden="true">
		{#each Array(rows) as _, i}
			<div class="row">
				<Skeleton height={12} width={i % 2 === 0 ? '24%' : '30%'} />
				<Skeleton height={12} width={i % 3 === 0 ? '58%' : '44%'} />
			</div>
		{/each}
	</div>
</div>

<style>
	.skeleton-detail {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		padding: 1.5rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: var(--shadow-sm);
	}

	.skeleton-detail.bare {
		background: none;
		border: 0;
		padding: 0;
		box-shadow: none;
	}

	.rows {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.row {
		display: flex;
		gap: 1.5rem;
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
