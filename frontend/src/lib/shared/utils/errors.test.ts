import { describe, it, expect } from 'vitest';
import { APIError } from '$lib/api/client';
import { describeError } from './errors';

describe('describeError', () => {
	it('returns a standard Error message', () => {
		expect(describeError(new Error('boom'), 'fallback')).toBe('boom');
	});

	it('returns an APIError message', () => {
		expect(describeError(new APIError('conflict', 'Already exists'), 'fallback')).toBe(
			'Already exists'
		);
	});

	it('returns a trimmed string error', () => {
		expect(describeError('  nope  ', 'fallback')).toBe('nope');
	});

	it('falls back for an empty message', () => {
		expect(describeError(new Error('   '), 'fallback')).toBe('fallback');
	});

	it('falls back for null and undefined', () => {
		expect(describeError(null, 'fallback')).toBe('fallback');
		expect(describeError(undefined, 'fallback')).toBe('fallback');
	});

	it('falls back for an empty string', () => {
		expect(describeError('', 'fallback')).toBe('fallback');
	});

	it('falls back for unexpected object values', () => {
		expect(describeError({ message: 'not an Error' }, 'fallback')).toBe('fallback');
		expect(describeError(42, 'fallback')).toBe('fallback');
		expect(describeError(false, 'fallback')).toBe('fallback');
	});

	it('never throws for a hostile message getter', () => {
		const hostile = new Error('ignored');
		Object.defineProperty(hostile, 'message', {
			get() {
				throw new Error('getter exploded');
			},
		});

		expect(() => describeError(hostile, 'fallback')).not.toThrow();
		expect(describeError(hostile, 'fallback')).toBe('fallback');
	});
});
