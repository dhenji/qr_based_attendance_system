<script lang="ts">
	// Route-level error page. SvelteKit renders this instead of the page's own
	// content when a `load` throws or a child component fails to render — without
	// it, an uncaught error propagates to the SvelteKit root and the user gets a
	// blank screen.
	//
	// It reuses ErrorBoundary for the message/panel (which is the presentational
	// half — it cannot catch render errors itself; this route is the boundary).
	// Stack traces stay dev-only so production doesn't leak internals.
	import { page } from '$app/state';
	import { dev } from '$app/environment';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
	import { Routes } from '$lib/shared/constants/routes';

	const fallback = $derived(
		page.status === 404
			? 'That page does not exist. It may have been moved or removed.'
			: page.status >= 500
				? 'Something went wrong on our side. Please try again in a moment.'
				: 'Something went wrong loading this page.'
	);
</script>

<svelte:head>
	<title>{page.status} · Attendly</title>
</svelte:head>

<div class="page">
	<p class="status" aria-hidden="true">{page.status}</p>
	<ErrorBoundary error={page.error} {fallback} showDetails={dev} retryButton={false} />

	<nav class="actions" aria-label="Recovery">
		<button class="btn" type="button" onclick={() => {
			if (window.history.length > 1) window.history.back();
			else window.location.href = Routes.HOME;
		}}>Go back</button>
		<a class="btn" href={Routes.HOME}>Home</a>
	</nav>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		min-height: 100vh;
		justify-content: center;
		padding: 2rem 1.5rem;
	}

	.status {
		margin: 0;
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 3rem;
		font-weight: 800;
		line-height: 1;
		color: var(--brand);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.625rem 1.25rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong);
		background: var(--bg-card);
		color: var(--text-strong);
		font: inherit;
		font-size: 0.9375rem;
		font-weight: 600;
		text-decoration: none;
		cursor: pointer;
	}

	.btn:hover {
		background: var(--bg-muted);
	}
</style>