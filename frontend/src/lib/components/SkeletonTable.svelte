<script lang="ts">
	// SkeletonTable
	// Drop-in replacement for the "<section class=\"card\"><p>Loading…</p>"
	// pattern on list pages. Renders a self-contained card whose header row and
	// data rows mirror a real table, so the swap from placeholder to rows does
	// not shift the page. Screen readers hear the label, not the blocks.
	import Skeleton from './Skeleton.svelte';

	interface Props {
		rows?: number;
		cols?: number;
		label?: string;
		/** Drop the card surface when nesting inside an existing card. */
		bare?: boolean;
	}

	let { rows = 6, cols = 5, label = 'Loading…', bare = false }: Props = $props();

	// Deterministic, slightly irregular widths so the placeholder reads as
	// data instead of a uniform barcode.
	const widths = ['88%', '62%', '74%', '48%', '68%', '56%'];
	const headWidths = ['42%', '30%', '36%', '24%', '30%', '28%'];
</script>

<div class="skeleton-table" class:bare role="status" aria-busy="true">
	<span class="sr-only">{label}</span>
	<div class="head-row" aria-hidden="true">
		{#each Array(cols) as _, c}
			<span class="cell">
				<Skeleton height={10} width={headWidths[c % headWidths.length]} />
			</span>
		{/each}
	</div>
	{#each Array(rows) as _, r}
		<div class="row" aria-hidden="true">
			{#each Array(cols) as _, c}
				<span class="cell">
					<Skeleton height={12} width={widths[(r + c) % widths.length]} />
				</span>
			{/each}
		</div>
	{/each}
</div>

<style>
	.skeleton-table {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.25rem 1.5rem;
		box-shadow: var(--shadow-sm);
		overflow: hidden;
	}

	.skeleton-table.bare {
		background: none;
		border: 0;
		border-radius: 0;
		padding: 0;
		box-shadow: none;
		overflow: visible;
	}

	.head-row,
	.row {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.875rem 0;
	}

	.head-row {
		border-bottom: 1px solid var(--border);
	}

	.row {
		border-bottom: 1px solid var(--divider);
	}

	.row:last-child {
		border-bottom: none;
	}

	.cell {
		flex: 1 1 0;
		min-width: 0;
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
