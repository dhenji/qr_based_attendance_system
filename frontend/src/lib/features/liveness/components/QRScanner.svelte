<script lang="ts">
	import { onMount } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';
	import { initiateQRScan } from '$lib/features/liveness/service';

	let isScanning = $state(false);
	let scannedCode = $state<string | null>(null);
	let scanError = $state<string | null>(null);
	let qrCode: Html5Qrcode | null = null;

	onMount(() => {
		return () => {
			if (qrCode) {
				qrCode.stop().catch(() => undefined);
				qrCode.clear();
			}
		};
	});

	const startScanning = async () => {
		scanError = null;
		isScanning = true;

		// Small wait for the DOM element to render
		await new Promise((r) => setTimeout(r, 100));

		try {
			if (!qrCode) {
				qrCode = new Html5Qrcode('qr-reader');
			}
			// Auto-initiate scan flow
			await initiateQRScan(1);
			await qrCode.start(
				{ facingMode: 'environment' },
				{ fps: 10, qrbox: { width: 250, height: 250 } },
				(decodedText) => {
					scannedCode = decodedText;
					isScanning = false;
					qrCode?.stop().catch(() => undefined);
				},
				() => {
					// Ignore frame-read errors (happens between successful scans)
				}
			);
		} catch (err) {
			scanError = err instanceof Error ? err.message : 'Failed to start camera';
			isScanning = false;
		}
	};

	const stopScanning = () => {
		isScanning = false;
		qrCode?.stop().catch(() => undefined);
	};
</script>

<div class="qr-scanner">
	{#if isScanning}
		<div id="qr-reader" class="qr-reader-box"></div>
		<p>Scanning... Position QR code within the frame</p>
		<button onclick={stopScanning}>Cancel</button>
	{:else if scannedCode}
		<div class="scan-success">
			<p>Scan successful!</p>
			<p>Code: {scannedCode}</p>
			<button onclick={() => { scannedCode = null; }}>Another Scan</button>
		</div>
	{:else}
		<button onclick={startScanning}>Scan Session QR</button>
		{#if scanError}
			<p class="error">{scanError}</p>
		{/if}
	{/if}
</div>
