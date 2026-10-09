<script lang="ts">
	// QRScanner
	// Show/hide of the camera view is driven by the `active` prop; every
	// successful decode hands the raw code back via the `onScanned` callback.
	import { onDestroy } from 'svelte';
	import { Html5Qrcode } from 'html5-qrcode';

	let { active, onScanned, id: idProp }: {
		active: boolean;
		onScanned: (code: string) => void;
		id?: string;
	} = $props();

	// Unique reader id per instance so two mounted scanners never share one
	// DOM id (Html5Qrcode binds by id). Caller may pass an explicit id.
	const readerId = $derived(
		idProp ?? `qr-reader-${Math.random().toString(36).slice(2, 10)}`
	);

	let scanError = $state<string | null>(null);
	let qrCode: Html5Qrcode | null = null;
	// Epoch + timer handle make the delayed start cancellable: a Stop,
	// effect re-run, or destroy invalidates any pending start so the camera
	// can never start after teardown.
	let startEpoch = 0;
	let startTimer: ReturnType<typeof setTimeout> | null = null;

	// React to the `active` prop: start the camera when shown, release it when hidden.
	$effect(() => {
		if (active) {
			void startScanning();
		} else {
			void stopScanning();
		}
	});

	// Clean up the camera when the component is destroyed.
	onDestroy(() => {
		startEpoch++;
		if (startTimer) clearTimeout(startTimer);
		startTimer = null;
		void stopScanning();
	});

	const startScanning = async () => {
		scanError = null;
		const epoch = ++startEpoch;
		if (startTimer) clearTimeout(startTimer);

		// Small wait for the DOM element to render (cancellable).
		await new Promise<void>((resolve) => {
			startTimer = setTimeout(() => {
				startTimer = null;
				resolve();
			}, 100);
		});
		if (epoch !== startEpoch || !active) return;

		try {
			if (!qrCode) {
				qrCode = new Html5Qrcode(readerId);
			}
			// Rear camera, 10fps, 250x250 scan box. The first decoded string
			// stops the scanner and reports the code to the parent page.
			await qrCode.start(
				{ facingMode: 'environment' },
				{ fps: 10, qrbox: { width: 250, height: 250 } },
				(decodedText) => {
					// Release the camera first, then hand the code back — liveness
					// only mounts once the QR stream is fully closed.
					void stopScanning().finally(() => onScanned(decodedText));
				},
				() => {
					// Ignore frame-read errors (happens between successful scans)
				}
			);
		} catch (err) {
			const raw = err instanceof Error ? err.message : 'Failed to start camera';
			const lower = raw.toLowerCase();
			if (lower.includes('permission') || lower.includes('denied') || lower.includes('notallowed')) {
				scanError =
					'Camera blocked — allow camera access in the browser site settings, then press Start Camera again.';
			} else if (lower.includes('notfound') || lower.includes('no camera') || lower.includes('devices')) {
				scanError = 'No camera found on this device. Enter the session code manually instead.';
			} else {
				scanError = raw;
			}
		}
	};

	// Stop the stream and wipe any rendered overlay from the DOM.
	// Resolves once the camera is actually released. `qrCode` is cleared
	// synchronously so repeat stop calls (effect re-run, onDestroy) are no-ops —
	// html5-qrcode throws "Cannot stop" if stop() is called while not scanning.
	// Also invalidates any pending delayed start.
	const stopScanning = () => {
		startEpoch++;
		if (startTimer) clearTimeout(startTimer);
		startTimer = null;
		const scanner = qrCode;
		qrCode = null;
		if (!scanner) return Promise.resolve();
		let stopPromise: Promise<void> | null = null;
		try {
			stopPromise = Promise.resolve(scanner.stop());
		} catch {
			stopPromise = Promise.resolve();
		}
		return stopPromise.catch(() => undefined).then(() => {
			try {
				scanner.clear();
			} catch {
				// Already stopped — nothing left to tear down.
			}
		});
	};
</script>

<div class="qr-scanner">
	<div id={readerId} class="qr-reader-box"></div>
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
		border: none;
	}

	.qr-reader-box :global(video) {
		width: 100% !important;
		height: 100% !important;
		object-fit: cover;
	}

	.qr-reader-box :global(.qr-canvas) {
		display: none;
	}

	.error {
		color: var(--danger);
		font-size: 0.875rem;
		margin: 0;
		text-align: center;
	}
</style>