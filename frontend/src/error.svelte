<script lang="ts">
	// Outermost fallback. SvelteKit renders this when an error escapes even the
	// route-level `+error.svelte` (i.e. the error page itself failed), so it must
	// stay dependency-free — no ErrorBoundary, no store, no API client.
	// `error` is intentionally unused: the internals are never rendered here.
	interface Props {
		error: unknown;
		status: number;
	}

	let { status }: Props = $props();
</script>

<svelte:head>
	<title>{status} · Attendly</title>
</svelte:head>

<div class="page">
	<p class="status" aria-hidden="true">{status}</p>
	<h1>Something went wrong</h1>
	<p class="text">The app hit an unexpected error. Reloading usually clears it.</p>
	<button class="btn" type="button" onclick={() => window.location.reload()}>Reload page</button>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		min-height: 100vh;
		justify-content: center;
		padding: 2rem 1.5rem;
		font-family: system-ui, sans-serif;
		text-align: center;
		color: var(--text, #0f172a);
		background: var(--bg-page, #f8fafc);
	}

	.status {
		margin: 0;
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 3rem;
		font-weight: 800;
		line-height: 1;
		color: var(--brand, #1e3a5f);
	}

	h1 {
		margin: 0;
		font-size: 1.375rem;
		font-weight: 700;
	}

	.text {
		margin: 0;
		color: var(--text-muted, #64748b);
		font-size: 0.9375rem;
	}

	.btn {
		margin-top: 0.75rem;
		padding: 0.625rem 1.25rem;
		border-radius: 8px;
		border: 1px solid var(--border-strong, #cbd5e1);
		background: var(--bg-card, #ffffff);
		color: var(--text-strong, #0f172a);
		font: inherit;
		font-size: 0.9375rem;
		font-weight: 600;
		cursor: pointer;
	}
</style>