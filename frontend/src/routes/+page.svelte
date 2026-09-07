<script lang="ts">
	import { isAuthenticated, isStudent, isProfessor, isAdmin, doLogout } from '$lib/features/auth/store.svelte';
</script>

<main class="landing">
	<h1>QR Attendance System</h1>
	<p>Scan to mark your presence. Live sessions for professors. Analytics for admins.</p>

	{#if isAuthenticated()}
		<div class="card">
			<h2>Welcome back</h2>
			{#if isStudent()}
				<a href="/student/dashboard">Go to Student Dashboard</a>
				<a href="/student/scan">Scan Now</a>
			{:else if isProfessor()}
				<a href="/professor/sessions">Go to Sessions</a>
			{:else if isAdmin()}
				<a href="/admin/students">Go to Admin Panel</a>
			{/if}
			<button onclick={doLogout}>Logout</button>
		</div>
	{:else}
		<div class="card">
			<h2>Get started</h2>
			<a href="/auth/login">Login</a>
			<a href="/auth/register">Register</a>
		</div>
	{/if}
</main>

<style>
	main.landing {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		gap: 1rem;
		font-family: system-ui, sans-serif;
		background: #f5f7fb;
		text-align: center;
		padding: 2rem;
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		background: white;
		padding: 2rem;
		border-radius: 12px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
		min-width: 260px;
	}

	a,
	button {
		padding: 0.7rem 1rem;
		border-radius: 8px;
		border: none;
		background: #2563eb;
		color: white;
		text-decoration: none;
		font-size: 1rem;
		cursor: pointer;
	}

	a:hover,
	button:hover {
		background: #1d4ed8;
	}
</style>