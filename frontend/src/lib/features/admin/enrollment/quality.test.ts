import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { validateFacePhoto } from './quality';

describe('validateFacePhoto', () => {
	it('rejects an empty file', async () => {
		const file = new File([new Uint8Array(0)], 'empty.jpg', { type: 'image/jpeg' });
		const result = await validateFacePhoto(file);
		expect(result.ok).toBe(false);
		expect(result.reason).toBe('Photo is empty');
	});

	it('rejects a file that cannot be decoded', async () => {
		vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('decode fail')));
		const file = new File([new Uint8Array([1, 2, 3])], 'bad.jpg', { type: 'image/jpeg' });
		const result = await validateFacePhoto(file);
		expect(result.ok).toBe(false);
		expect(result.reason).toBe('Photo could not be decoded. Use JPG, PNG, or WebP.');
		vi.unstubAllGlobals();
	});
});