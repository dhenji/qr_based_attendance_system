<script lang="ts">
	import { onMount } from 'svelte';
	import { getSchedule } from '$lib/features/student/service';
	import type { ScheduledClass } from '$lib/shared/types';

	// My Schedule — live on GET /student/schedule (no params; identity from
	// the Bearer token). One row per active enrollment ordered by offering_id;
	// empty enrollments return { offerings: [] }, which keeps the original
	// empty-state copy below.

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);

	let classes = $state<ScheduledClass[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const load = async () => {
		loading = true;
		error = null;
		try {
			classes = await getSchedule();
		} catch (e: unknown) {
			error = e instanceof Error && e.message ? e.message : 'Could not load schedule.';
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		void load();
	});
</script>

<div class="wrap">
	<header class="header">
		<div>
			<h1>My Schedule</h1>
			<p class="muted">{today} · {classes.length} enrolled</p>
		</div>
	</header>

	{#if loading}
		<p class="empty">Loading…</p>
	{:else if error}
		<p class="empty error">Could not load schedule: {error} <button class="retry-btn" onclick={() => void load()}>Try again</button></p>
	{:else if classes.length === 0}
		<p class="empty">No classes scheduled yet. Your enrolled subjects will appear here.</p>
	{:else}
		<ul class="list">
			{#each classes as c (c.offeringId)}
				<li class="card">
					<div class="row">
						<strong>{c.courseCode}</strong>
						<span class="muted"> · {c.courseName}</span>
					</div>
					<div class="meta">
						<span>{c.scheduleDays} {c.scheduleStartTime}–{c.scheduleEndTime}</span>
						<span>{c.classroomName ?? 'Room TBA'}</span>
						<span>{c.professorName ?? 'Professor TBA'}</span>
					</div>
					<div class="sub muted">{c.programCode} · {c.yearLevelLabel} · {c.semester}</div>
				</li>
			{/each}
		</ul>
	{/if}
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

	.empty.error {
		color: var(--danger);
	}

	.retry-btn {
		margin-left: 0.75rem;
		background: var(--bg-card);
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		padding: 0.375rem 0.875rem;
		font-size: 0.875rem;
		font-weight: 600;
		font-family: inherit;
		color: var(--brand);
		cursor: pointer;
	}

	.list {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin: 0;
		padding: 0;
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 1rem 1.25rem;
		box-shadow: var(--shadow-sm);
	}

	.row {
		font-size: 1rem;
		margin-bottom: 0.25rem;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1rem;
		font-size: 0.875rem;
		color: var(--text-secondary);
	}

	.sub {
		margin-top: 0.25rem;
		font-size: 0.75rem;
	}
</style>
