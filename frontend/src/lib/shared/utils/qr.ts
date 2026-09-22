// shared/utils/qr.ts
// html5-qrcode initialization helpers

import { Html5Qrcode } from 'html5-qrcode';

// initQRScanner
// Attach html5-qrcode to the #qr-reader element using the rear camera. Decoded
// codes are forwarded via onScan and the scanner stops itself on success.
export const initQRScanner = (onScan: (data: string) => void): void => {
	const html5QrCode = new Html5Qrcode('qr-reader');

	html5QrCode
		.start(
			{ facingMode: 'environment' },
			{ fps: 10, qrbox: { width: 250, height: 250 } },
			(decodedText) => {
				onScan(decodedText);
				html5QrCode.stop().catch(() => undefined);
			},
			() => {
				// Ignore decode-frame errors (happens between successful scans)
			}
		)
		.catch((err) => {
			console.error('QR scanner initialization failed:', err);
		});
};

// Debug stub hooks for scan outcomes (replace with real UI messaging later).
export const handleScanSuccess = (payload: string): void => {
	console.log('Scan successful:', payload);
};

export const handleScanError = (error: string): void => {
	console.error('Scan failed:', error);
};
