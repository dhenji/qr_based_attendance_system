<script lang="ts">
	import { onMount } from 'svelte';
	import { studentState, initStudent, complianceRate, participationRate } from '$lib/features/student/store.svelte';
	import { formatPercentage } from '$lib/shared/utils/format';

	onMount(() => {
		initStudent();
	});
</script>

<main class="dashboard">
	<header>
		<h1>Student Dashboard</h1>
		<nav>
			<a href="/student/dashboard" aria-current="page">Dashboard</a>
			<a href="/student/scan">Scan</a>
			<a href="/">Home</a>
		</nav>
	</header>

	{#if studentState.loading}
		<p class="muted">Loading profile…</p>
	{:else if studentState.student}
		<section class="grid">
			<div class="card">
				<h2>Profile</h2>
				<p><strong>{studentState.student.firstName} {studentState.student.lastName}</strong></p>
				<p>{studentState.student.studentNumber}</p>
				<p>{studentState.student.programCode} · {studentState.student.yearLevelLabel} · Section {studentState.student.section}</p>
				<p>Face enrolled: {studentState.student.faceEnrolled ? 'Yes' : 'No'}</p>
			</div>

			<div class="card">
				<h2>Statistics</h2>
				<p>Compliance rate: <strong>{formatPercentage(complianceRate())}</strong></p>
				<p>Participation rate: <strong>{formatPercentage(participationRate())}</strong></p>
			</div>
		</section>

		{#if studentState.courses.length > 0}
			<section class="card">
				<h2>My Courses</h2>
				<ul>
					{#each studentState.courses as course}
						<li>
							<strong>{course.courseCode}</strong> — {course.courseName}
							<span class="muted">
								({course.scheduleDays.join(', ')} {course.scheduleStartTime}–{course.scheduleEndTime})
							</span>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if studentState.history.length > 0}
			<section class="card">
				<h2>Recent Attendance</h2>
				<table>
					<thead>
						<tr><th>Course</th><th>Status</th><th>Via</th><th>Time</th></tr>
					</thead>
					<tbody>
						{#each studentState.history as record}
							<tr>
								<td>{record.courseName}</td>
								<td>{record.status}</td>
								<td>{record.scannedVia}</td>
								<td>{new Date(record.scannedAt).toLocaleString()}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</section>
		{/if}
	{:else}
		<p class="muted">No profile found. Please complete registration.</p>
	{/if}

	{#if studentState.error}
		<p class="error">{studentState.error}</p>
	{/if}
</main>

<style>
	.dashboard {
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

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 1rem;
		margin: 1.5rem 0;
	}

	.card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 1.5rem;
	}

	ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	li {
		padding: 0.5rem 0;
		border-bottom: 1px solid #f3f4f6;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.95rem;
	}

	th,
	td {
		text-align: left;
		padding: 0.5rem;
		border-bottom: 1px solid #f3f4f6;
	}

	.muted {
		color: #6b7280;
	}

	.error {
		color: #dc2626;
	}
</style>