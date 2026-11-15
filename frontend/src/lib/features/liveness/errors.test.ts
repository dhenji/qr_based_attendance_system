import { describe, it, expect } from 'vitest';
import { APIError } from '$lib/api/client';
import { toScanMessage, SCAN_ERROR_MESSAGES } from './errors';

describe('toScanMessage', () => {
	const fallback = 'fallback message';

	it('returns mapped message for known code', () => {
		const err = new APIError('duplicate_scan', 'dup');
		expect(toScanMessage(err, fallback)).toBe(SCAN_ERROR_MESSAGES.duplicate_scan);
	});

	it('appends remaining attempts when provided', () => {
		const err = new APIError('face_mismatch', 'nope');
		expect(toScanMessage(err, fallback, 2)).toBe(
			`${SCAN_ERROR_MESSAGES.face_mismatch} (2 attempts remaining)`
		);
	});

	it('does not append remaining attempts when null', () => {
		const err = new APIError('face_mismatch', 'nope');
		expect(toScanMessage(err, fallback, null)).toBe(SCAN_ERROR_MESSAGES.face_mismatch);
	});

	it('returns closed copy for 410 status with unknown code', () => {
		const err = new APIError('some_unknown_code', 'gone', undefined, 410);
		expect(toScanMessage(err, fallback)).toBe('This session has closed for scanning.');
	});

	it('returns fallback for unknown code without 410', () => {
		const err = new APIError('totally_unknown', 'msg');
		expect(toScanMessage(err, fallback)).toBe(fallback);
	});

	it('returns error message for Error instance', () => {
		expect(toScanMessage(new Error('boom'), fallback)).toBe('boom');
	});

	it('returns fallback for empty Error message', () => {
		expect(toScanMessage(new Error(''), fallback)).toBe(fallback);
	});

	it('returns fallback for non-Error unknown', () => {
		expect(toScanMessage(42, fallback)).toBe(fallback);
		expect(toScanMessage(null, fallback)).toBe(fallback);
	});
});