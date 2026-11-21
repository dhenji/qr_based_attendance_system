import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { downloadBlob, downloadTextFile, OBJECT_URL_REVOKE_DELAY_MS } from './file';

describe('file download', () => {
	const originalCreateObjectURL = URL.createObjectURL;
	const originalRevokeObjectURL = URL.revokeObjectURL;

	let createObjectURL: ReturnType<typeof vi.fn>;
	let revokeObjectURL: ReturnType<typeof vi.fn>;
	let capturedBlob: Blob | undefined;
	let capturedDownload: string | undefined;
	let capturedHref: string | undefined;

	beforeEach(() => {
		capturedBlob = undefined;
		capturedDownload = undefined;
		capturedHref = undefined;

		createObjectURL = vi.fn((blob: Blob) => {
			capturedBlob = blob;
			return 'blob:test-url';
		});
		revokeObjectURL = vi.fn();
		URL.createObjectURL = createObjectURL as typeof URL.createObjectURL;
		URL.revokeObjectURL = revokeObjectURL as typeof URL.revokeObjectURL;

		vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
			this: HTMLAnchorElement
		) {
			capturedDownload = this.download;
			capturedHref = this.href;
		});
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
		URL.createObjectURL = originalCreateObjectURL;
		URL.revokeObjectURL = originalRevokeObjectURL;
	});

	it('downloads text with the default CSV MIME type and filename', async () => {
		downloadTextFile('a,b\n1,2', 'rows.csv');

		expect(createObjectURL).toHaveBeenCalledTimes(1);
		expect(capturedBlob).toBeInstanceOf(Blob);
		expect(capturedBlob?.type).toBe('text/csv;charset=utf-8');
		await expect(capturedBlob?.text()).resolves.toBe('a,b\n1,2');
		expect(capturedDownload).toBe('rows.csv');
		expect(capturedHref).toBe('blob:test-url');
	});

	it('honours an explicit MIME type', async () => {
		downloadTextFile('{}', 'backup.json', 'application/json;charset=utf-8');

		expect(capturedBlob?.type).toBe('application/json;charset=utf-8');
		await expect(capturedBlob?.text()).resolves.toBe('{}');
	});

	it('downloads a binary blob unchanged', () => {
		const blob = new Blob(['binary'], { type: 'application/octet-stream' });

		downloadBlob(blob, 'backup.bin');

		expect(capturedBlob).toBe(blob);
		expect(capturedDownload).toBe('backup.bin');
	});

	it('removes the temporary anchor after the click', () => {
		downloadTextFile('x', 'x.csv');

		expect(document.body.querySelectorAll('a')).toHaveLength(0);
	});

	it('revokes the object URL after the delayed cleanup window', () => {
		vi.useFakeTimers();

		downloadTextFile('x', 'x.csv');
		expect(revokeObjectURL).not.toHaveBeenCalled();

		vi.advanceTimersByTime(OBJECT_URL_REVOKE_DELAY_MS - 1);
		expect(revokeObjectURL).not.toHaveBeenCalled();

		vi.advanceTimersByTime(1);
		expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-url');
	});

	it('revokes immediately when the anchor cannot be created', () => {
		vi.spyOn(document, 'createElement').mockImplementationOnce(() => {
			throw new Error('createElement failed');
		});

		expect(() => downloadTextFile('x', 'x.csv')).toThrow('createElement failed');
		expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-url');
		expect(document.body.querySelectorAll('a')).toHaveLength(0);
	});

	it('removes the anchor and revokes immediately when the click fails', () => {
		vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementationOnce(() => {
			throw new Error('click failed');
		});

		expect(() => downloadTextFile('x', 'x.csv')).toThrow('click failed');
		expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-url');
		expect(document.body.querySelectorAll('a')).toHaveLength(0);
	});

	it('revokes immediately when the anchor cannot be appended to the body', () => {
		vi.spyOn(document.body, 'appendChild').mockImplementationOnce(() => {
			throw new Error('appendChild failed');
		});

		expect(() => downloadTextFile('x', 'x.csv')).toThrow('appendChild failed');
		expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-url');
		expect(document.body.querySelectorAll('a')).toHaveLength(0);
	});
});
