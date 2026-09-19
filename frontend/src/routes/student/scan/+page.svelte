<script lang="ts">
	import QRScanner from '$lib/features/liveness/components/QRScanner.svelte';
</script>

<div class="scan-page">
	<h1>Scan Attendance</h1>
	<section class="scan-card">
		<h2>Point your camera at the session QR code</h2>
		<p class="muted">Your GPS location and liveness check will be attached to the scan.</p>
		<QRScanner />
	</section>
</div>

<style>
	.scan-page {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		font-family: system-ui, sans-serif;
	}

	h1 {
		font-family: system-ui, sans-serif;
		font-size: 1.625rem;
		font-weight: 700;
		color: #1e293b;
		margin: 0;
	}

	.scan-card {
		background: white;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		padding: 2.5rem;
		text-align: center;
		box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
	}

	h2 {
		font-size: 1.0625rem;
		margin: 0 0 0.5rem;
		color: #1e293b;
	}

	.muted {
		color: #64748b;
		font-size: 0.875rem;
		margin: 0 0 1.5rem;
	}
</style>