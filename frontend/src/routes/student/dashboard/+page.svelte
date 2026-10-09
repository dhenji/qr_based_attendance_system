<script lang="ts">
	import { onMount } from 'svelte';
	import {
		studentState,
		initStudent,
		complianceRate,
		hasDashboardData,
		scansToday,
		totalScans,
	} from '$lib/features/student/store.svelte';
	import DashboardStats from '$lib/features/student/components/DashboardStats.svelte';
	import { Routes } from '$lib/shared/constants/routes';

	onMount(() => {
		initStudent();
	});

	const firstName = $derived(studentState.student?.firstName ?? 'Student');

	const today = $derived(
		new Date().toLocaleDateString(undefined, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
		})
	);
</script>

<div class="dashboard">
	<header class="header">
		<div>
			<h1>Welcome, {firstName}</h1>
			<p class="muted">{today}</p>
		</div>
	</header>

	{#if studentState.error}
		<p class="error">{studentState.error} <button class="retry-btn" onclick={() => void initStudent()}>Try again</button></p>
	{/if}

	<section class="hero">
		<DashboardStats complianceRate={complianceRate()} hasData={hasDashboardData()} />
	</section>

	<section class="kpis">
		<div class="kpi">
			<span class="kpi-value">{studentState.loading ? '—' : scansToday()}</span>
			<span class="kpi-label">Scans today</span>
		</div>
		<div class="kpi">
			<span class="kpi-value">{studentState.loading ? '—' : totalScans()}</span>
			<span class="kpi-label">Total scans</span>
		</div>
	</section>

	<a class="scan-btn" href={Routes.SCAN}>Scan QR Attendance</a>

	<section class="card">
		<h2 class="section-title">Today's Schedule</h2>
		{#if studentState.loading}
			<p class="muted">Loading…</p>
		{:else if studentState.courses.length > 0}
			<ul>
				{#each studentState.courses as course}
					<li>
						<strong>{course.courseCode}</strong> — {course.courseName}
						<span class="muted">
							({course.scheduleDays} {course.scheduleStartTime}–{course.scheduleEndTime})
						</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="empty">No classes scheduled yet. Your enrolled subjects will appear here.</p>
		{/if}
	</section>
</div>

<style>
	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 2rem;
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

	.hero {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
	}

	.kpi {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 1.25rem;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.kpi-value {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text);
		line-height: 1;
	}

	.kpi-label {
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.scan-btn {
		display: block;
		width: 100%;
		padding: 1.125rem;
		background: var(--brand);
		color: var(--on-brand);
		border: none;
		border-radius: 8px;
		font-size: 1rem;
		font-weight: 700;
		font-family: system-ui, sans-serif;
		text-align: center;
		text-decoration: none;
		cursor: pointer;
		box-shadow: 0 4px 14px rgba(30, 58, 95, 0.25);
		transition: box-shadow 0.15s ease, transform 0.15s ease, background 0.15s ease;
	}

	.scan-btn:hover {
		background: var(--brand-hover);
		transform: translateY(-1px);
		box-shadow: 0 6px 18px rgba(30, 58, 95, 0.3);
	}

	.card {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 2rem;
		box-shadow: var(--shadow-sm);
		transition: box-shadow 0.15s ease;
	}

	.card:hover {
		box-shadow: 0 6px 24px rgba(15, 23, 42, 0.1);
	}

	.section-title {
		font-family: 'DM Sans', system-ui, sans-serif;
		font-size: 1.0625rem;
		font-weight: 700;
		color: var(--text);
		margin: 0 0 1rem;
	}

	ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	li {
		padding: 0.75rem;
		border-bottom: 1px solid var(--divider);
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.5rem;
		align-items: baseline;
	}

	li:last-child {
		border-bottom: none;
	}

	.empty {
		color: var(--text-muted);
		font-size: 0.9375rem;
		margin: 0;
	}

	.error {
		color: var(--danger);
		margin: 0;
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
</style>