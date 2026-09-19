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
		<p>Scanning. Position the QR code within the frame.</p>
		<button class="btn btn-ghost" onclick={stopScanning}>Cancel</button>
	{:else if scannedCode}
		<div class="scan-success">
			<p>Scan successful</p>
			<p>Code: {scannedCode}</p>
			<button class="btn" onclick={() => { scannedCode = null; }}>Scan another code</button>
		</div>
	{:else}
		<button class="btn" onclick={startScanning}>Start camera scanner</button>
		{#if scanError}
			<p class="error">{scanError}</p>
		{/if}
	{/if}
</div>

<style>
	.qr-scanner {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.875rem;
		width: 100%;
	}

	.qr-reader-box {
		width: 100%;
		max-width: 320px;
	}

	.btn {
		padding: 0.625rem 1.125rem;
		border-radius: 8px;
		border: 1px solid #1d4ed8;
		background: #1d4ed8;
		color: white;
		font-size: 0.9375rem;
		font-weight: 600;
		font-family: inherit;
		cursor: pointer;
	}

	.btn:hover {
		background: #1e40af;
		border-color: #1e40af;
	}

	.btn-ghost {
		background: white;
		border-color: #cbd5e1;
		color: #0f172a;
	}

	.btn-ghost:hover {
		background: #f1f5f9;
		border-color: #cbd5e1;
	}

	.error {
		color: #b91c1c;
		font-size: 0.875rem;
		margin: 0;
	}
</style>
