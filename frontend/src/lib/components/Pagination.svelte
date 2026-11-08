<script lang="ts">
	// Shared pagination control. Mirrors the professor attendance ledger's
	// full pagination (first/prev/numbered pages with gap ellipsis/next/last)
	// so analytics and other pages stay consistent.
	let {
		page,
		totalPages,
		onPageChange,
	}: {
		page: number;
		totalPages: number;
		onPageChange: (p: number) => void;
	} = $props();

	const visiblePages = $derived.by((): Array<number | 'gap-start' | 'gap-end'> => {
		const count = Math.max(1, totalPages);
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

<nav class="pagination" aria-label="Pagination">
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
	<button class="page" type="button" disabled={page >= totalPages} onclick={() => onPageChange(Math.min(totalPages, page + 1))} aria-label="Next page">Next</button>
	<button class="page" type="button" disabled={page >= totalPages} onclick={() => onPageChange(totalPages)} aria-label="Last page">Last</button>
	<span class="page-count" aria-live="polite">Page {page} of {Math.max(1, totalPages)}</span>
</nav>

<style>
	.pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-top: 1rem; }
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