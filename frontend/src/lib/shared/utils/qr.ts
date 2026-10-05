// shared/utils/qr.ts
// html5-qrcode initialization helpers

import { Html5Qrcode } from 'html5-qrcode';

// initQRScanner
// Attach html5-qrcode to the #qr-reader element using the rear camera. Decoded
// codes are forwarded via onScan and the scanner stops itself on success.
// Start failures go to onError (e.g. no camera, permission denied) so the
// caller can render them inline. Returns a stop() cleanup for unmount.
export const initQRScanner = (
	onScan: (data: string) => void,
	onError?: (message: string) => void
): (() => void) => {
	const html5QrCode = new Html5Qrcode('qr-reader');
	let stopped = false;

	const stop = (): void => {
		if (stopped) return;
		stopped = true;
		html5QrCode.stop().catch(() => undefined);
	};

	html5QrCode
		.start(
			{ facingMode: 'environment' },
			{ fps: 10, qrbox: { width: 250, height: 250 } },
			(decodedText) => {
				onScan(decodedText);
				stop();
			},
			() => {
				// Ignore decode-frame errors (happens between successful scans)
			}
		)
		.catch((err: unknown) => {
			onError?.(
				err instanceof Error && err.message
					? err.message
					: 'Could not start the QR scanner. Check camera permission and try again.'
			);
		});

	return stop;
};
