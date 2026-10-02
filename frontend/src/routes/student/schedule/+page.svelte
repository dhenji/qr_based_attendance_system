<script lang="ts">
	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);
</script>

<div class="wrap">
	<header class="header">
		<div>
			<h1>My Schedule</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	<p class="empty">No classes scheduled yet. Your enrolled subjects will appear here.</p>
</div>

<style>
	.wrap {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		max-width: 1100px;
		font-family: system-ui, sans-serif;
	}

	.header h1 {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 0.25rem;
	}

	.muted {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.empty {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}
</style>