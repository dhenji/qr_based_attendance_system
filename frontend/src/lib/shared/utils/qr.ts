// shared/utils/qr.ts
// html5-qrcode initialization helpers

import { Html5Qrcode } from 'html5-qrcode';

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

export const handleScanSuccess = (payload: string): void => {
	console.log('Scan successful:', payload);
};

export const handleScanError = (error: string): void => {
	console.error('Scan failed:', error);
};
