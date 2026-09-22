<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';
	import { initiateQRScan } from '$lib/features/liveness/service';

	let { active, onScanned } = $props<{
		active: boolean;
		onScanned: (code: string) => void;
	}>();

	let scanError = $state<string | null>(null);
	let qrCode: Html5Qrcode | null = null;

	$effect(() => {
		if (active) {
			startScanning();
		} else {
			stopScanning();
		}
	});

	onDestroy(() => {
		stopScanning();
	});

	const startScanning = async () => {
		scanError = null;

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
					stopScanning();
					onScanned(decodedText);
				},
				() => {
					// Ignore frame-read errors (happens between successful scans)
				}
			);
		} catch (err) {
			scanError = err instanceof Error ? err.message : 'Failed to start camera';
		}
	};

	const stopScanning = () => {
		qrCode?.stop().catch(() => undefined);
		qrCode?.clear();
	};
</script>

<div class="qr-scanner">
	<div id="qr-reader" class="qr-reader-box"></div>
	{#if scanError}
		<p class="error">{scanError}</p>
	{/if}
</div>

<style>
	.qr-scanner {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.qr-reader-box {
		width: 100%;
		height: 100%;
		overflow: hidden;
	}

	:global(#qr-reader) {
		border: none;
	}

	:global(#qr-reader video) {
		width: 100% !important;
		height: 100% !important;
		object-fit: cover;
	}

	:global(#qr-reader .qr-canvas) {
		display: none;
	}

	.error {
		color: #dc2626;
		font-size: 0.875rem;
		margin: 0;
		text-align: center;
	}
</style>