// file.ts
// Browser download helpers for generated text/CSV exports and binary blobs.
//
// Every download goes through one anchor + object-URL lifecycle so cleanup is
// identical everywhere. The object URL is revoked late on success (revoking
// synchronously can abort a large download in Safari) and immediately when the
// click never happened, so a failed DOM operation cannot leak it.

export const OBJECT_URL_REVOKE_DELAY_MS = 60_000;

const DEFAULT_TEXT_MIME_TYPE = 'text/csv;charset=utf-8';

const triggerDownload = (url: string, filename: string): void => {
	let anchor: HTMLAnchorElement | null = null;
	let clicked = false;
	try {
		anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = filename;
		document.body.appendChild(anchor);
		anchor.click();
		clicked = true;
	} finally {
		try {
			anchor?.remove();
		} finally {
			if (clicked) {
				setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_REVOKE_DELAY_MS);
			} else {
				URL.revokeObjectURL(url);
			}
		}
	}
};

export const downloadBlob = (blob: Blob, filename: string): void => {
	const url = URL.createObjectURL(blob);
	triggerDownload(url, filename);
};

export const downloadTextFile = (
	text: string,
	filename: string,
	mimeType: string = DEFAULT_TEXT_MIME_TYPE
): void => {
	downloadBlob(new Blob([text], { type: mimeType }), filename);
};
