<script lang="ts">
	import QRScanner from '$lib/features/liveness/components/QRScanner.svelte';
</script>

<main class="scan-page">
	<header>
		<h1>Scan Attendance</h1>
		<nav>
			<a href="/student/dashboard">Dashboard</a>
			<a href="/">Home</a>
		</nav>
	</header>

	<section class="scan-card">
		<h2>Point your camera at the session QR code</h2>
		<p class="muted">Your GPS location and liveness check will be attached to the scan.</p>
		<QRScanner />
	</section>
</main>

<style>
	.scan-page {
		font-family: system-ui, sans-serif;
		max-width: 640px;
		margin: 0 auto;
		padding: 2rem 1rem;
		text-align: center;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 2rem;
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

	.scan-card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 2rem;
	}

	.muted {
		color: #6b7280;
	}
</style>