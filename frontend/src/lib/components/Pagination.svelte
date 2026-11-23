<script lang="ts">
	// Shared pagination control. Two variants:
	// - full: first/prev/numbered pages with gap ellipsis/next/last (analytics,
	//   professor attendance, student history, excuse requests)
	// - compact: prev / "Page X of Y" / next (archive roster pages)
	// `spacing={false}` lets a parent that already owns the surrounding
	// padding (for example a table footer) drop the root top margin.
	let {
		page,
		totalPages,
		onPageChange,
		variant = 'full',
		spacing = true,
		ariaLabel = 'Pagination',
	}: {
		page: number;
		totalPages: number;
		onPageChange: (p: number) => void;
		variant?: 'full' | 'compact';
		spacing?: boolean;
		ariaLabel?: string;
	} = $props();

	const count = $derived(Math.max(1, totalPages));

	const visiblePages = $derived.by((): Array<number | 'gap-start' | 'gap-end'> => {
		if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1);
		const window: Array<number | 'gap-start' | 'gap-end'> = [1];
		const start = Math.max(2, page - 2);
		const end = Math.min(count - 1, page + 2);
		if (start > 2) window.push('gap-start');
		for (let p = start; p <= end; p += 1) window.push(p);
		if (end < count - 1) window.push('gap-end');
		window.push(count);
		return window;
	});
</script>

{#if variant === 'compact'}
	<nav class="pagination" class:no-spacing={!spacing} aria-label={ariaLabel}>
		<button
			class="btn btn-secondary"
			type="button"
			disabled={page <= 1}
			onclick={() => onPageChange(Math.max(1, page - 1))}
			aria-label="Previous page"
		>
			‹ Prev
		</button>
		<span class="page-count" aria-live="polite">Page {page} of {count}</span>
		<button
			class="btn btn-secondary"
			type="button"
			disabled={page >= count}
			onclick={() => onPageChange(Math.min(count, page + 1))}
			aria-label="Next page"
		>
			Next ›
		</button>
	</nav>
{:else}
	<nav class="pagination" class:no-spacing={!spacing} aria-label={ariaLabel}>
		<button class="page" type="button" disabled={page <= 1} onclick={() => onPageChange(1)} aria-label="First page">First</button>
		<button class="page" type="button" disabled={page <= 1} onclick={() => onPageChange(Math.max(1, page - 1))} aria-label="Previous page">Prev</button>
		{#each visiblePages as p (p)}
			{#if typeof p === 'number'}
				<button
					class="page"
					class:current={p === page}
					type="button"
					disabled={p === page}
					onclick={() => onPageChange(p)}
					aria-label={`Page ${p}`}
					aria-current={p === page ? 'page' : undefined}
				>
					{p}
				</button>
			{:else}
				<span class="gap" aria-hidden="true">…</span>
			{/if}
		{/each}
		<button class="page" type="button" disabled={page >= count} onclick={() => onPageChange(Math.min(count, page + 1))} aria-label="Next page">Next</button>
		<button class="page" type="button" disabled={page >= count} onclick={() => onPageChange(count)} aria-label="Last page">Last</button>
		<span class="page-count" aria-live="polite">Page {page} of {count}</span>
	</nav>
{/if}

<style>
	.pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-top: 1rem; }
	.pagination.no-spacing { margin-top: 0; }
	.page {
		min-width: 2.25rem; padding: 0.4rem 0.6rem; border-radius: 8px;
		border: 1px solid var(--border-strong); background: var(--bg-card);
		color: var(--text-strong); font: inherit; font-size: 0.8125rem; font-weight: 600; cursor: pointer;
	}
	.page:hover:not(:disabled) { background: var(--bg-hover, var(--divider)); }
	.page:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
	.page.current { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
	.page:disabled:not(.current) { color: var(--text-muted); background: var(--bg-page); border-color: var(--border); cursor: not-allowed; }
	.gap { padding: 0 0.125rem; color: var(--text-muted); font-weight: 700; user-select: none; }
	.page-count { margin-left: 0.5rem; font-size: 0.8125rem; font-weight: 600; color: var(--text-muted); white-space: nowrap; }
</style>
