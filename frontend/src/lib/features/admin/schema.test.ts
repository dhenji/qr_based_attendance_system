import { describe, it, expect } from 'vitest';
import { facePhotoSchema } from './schema';

describe('facePhotoSchema', () => {
	it('rejects a non-File value', () => {
		const parsed = facePhotoSchema.safeParse(null);
		expect(parsed.success).toBe(false);
	});

	it('rejects an unsupported extension', () => {
		const file = new File([new Uint8Array([1])], 'photo.gif', { type: 'image/gif' });
		const parsed = facePhotoSchema.safeParse(file);
		expect(parsed.success).toBe(false);
	});

	it('rejects an empty file', () => {
		const file = new File([new Uint8Array(0)], 'photo.jpg', { type: 'image/jpeg' });
		const parsed = facePhotoSchema.safeParse(file);
		expect(parsed.success).toBe(false);
	});

	it('rejects an oversized file', () => {
		const big = new Uint8Array(5 * 1024 * 1024 + 1);
		const file = new File([big], 'photo.jpg', { type: 'image/jpeg' });
		const parsed = facePhotoSchema.safeParse(file);
		expect(parsed.success).toBe(false);
	});

	it('accepts a valid jpg under the size limit', () => {
		const file = new File([new Uint8Array([1, 2, 3])], 'photo.jpg', { type: 'image/jpeg' });
		const parsed = facePhotoSchema.safeParse(file);
		expect(parsed.success).toBe(true);
	});
});