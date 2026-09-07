<script lang="ts">
	import { onMount } from 'svelte';
	import { listSessions, openSession } from '$lib/features/session/service';

	let sessions = $state<Awaited<ReturnType<typeof listSessions>> | null>(null);
	let courseId = $state(1);
	let duration = $state(90);
	let showForm = $state(false);
	let message = $state<string | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		sessions = await listSessions();
	});

	const handleOpen = async () => {
		error = null;
		message = null;
		try {
			const created = await openSession(courseId, { durationMinutes: duration });
			message = `Session ${created.code} opened!`;
			sessions = await listSessions();
			showForm = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to open session';
		}
	};
</script>

<main class="sessions">
	<header>
		<h1>My Sessions</h1>
		<nav>
			<a href="/professor/sessions" aria-current="page">Sessions</a>
			<a href="/">Home</a>
		</nav>
	</header>

	{#if message}
		<p class="message">{message}</p>
	{/if}
	{#if error}
		<p class="error">{error}</p>
	{/if}

	<button onclick={() => { showForm = !showForm; }}>
		{showForm ? 'Cancel' : '+ Open Session'}
	</button>

	{#if showForm}
		<section class="card form">
			<h2>Open New Session</h2>
			<label>
				Course ID
				<input type="number" bind:value={courseId} min={1} />
			</label>
			<label>
				Duration (minutes)
				<input type="number" bind:value={duration} min={5} />
			</label>
			<button onclick={handleOpen}>Open Session</button>
		</section>
	{/if}

	<section class="list">
		{#if sessions}
			{#each sessions.items as session}
				<div class="card">
					<h3>{session.code}</h3>
					<p class="muted">
						Course #{session.courseId} · Present {session.presentCount} · Late {session.lateCount} · Absent {session.absentCount}
					</p>
					<p>Status: <strong>{session.status}</strong></p>
					<p class="muted">Expires {new Date(session.expiresAt).toLocaleString()}</p>
				</div>
			{:else}
				<p class="muted">No sessions yet. Open one above.</p>
			{/each}
		{:else}
			<p class="muted">Loading sessions…</p>
		{/if}
	</section>
</main>

<style>
	.sessions {
		font-family: system-ui, sans-serif;
		max-width: 800px;
		margin: 0 auto;
		padding: 2rem 1rem;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}

	nav {
		display: flex;
		gap: 0.75rem;
	}

	nav a {
		color: #2563eb;
		text-decoration: none;
		font-weight: 500;
	}

	nav a[aria-current='page'] {
		text-decoration: underline;
	}

	.card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 1.5rem;
		margin-top: 1rem;
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		font-weight: 500;
	}

	input {
		padding: 0.6rem;
		border: 1px solid #d1d5db;
		border-radius: 8px;
	}

	button {
		padding: 0.7rem 1rem;
		border: none;
		border-radius: 8px;
		background: #2563eb;
		color: white;
		font-size: 1rem;
		cursor: pointer;
		margin-top: 1rem;
	}

	button:hover {
		background: #1d4ed8;
	}

	.message {
		color: #16a34a;
	}

	.error {
		color: #dc2626;
	}

	.muted {
		color: #6b7280;
	}
</style>