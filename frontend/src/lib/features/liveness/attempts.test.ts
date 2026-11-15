import { describe, it, expect } from 'vitest';
import { APIError } from '$lib/api/client';
import {
	attemptsFromDetails,
	attemptUpdateFromError,
	remainingFromError,
	remainingFromMessage
} from './attempts';

const CONSUMING_DETAILS = {
	attempt_limit: 3,
	attempts_used: 1,
	attempts_remaining: 2,
	attempt_consumed: true
};

describe('attemptsFromDetails', () => {
	it('parses authoritative metadata from the error envelope', () => {
		expect(attemptsFromDetails(CONSUMING_DETAILS)).toEqual({ limit: 3, remaining: 2 });
	});

	it('reads non-consuming metadata the same way (remaining already post-op)', () => {
		// verify_code exhaustion raises with consumed=false; the client
		// interpretation is identical: remaining is authoritative as-is.
		expect(
			attemptsFromDetails({
				attempt_limit: 2,
				attempts_used: 5,
				attempts_remaining: 0,
				attempt_consumed: false
			})
		).toEqual({ limit: 2, remaining: 0 });
	});

	it('returns null for missing metadata', () => {
		expect(attemptsFromDetails(undefined)).toBeNull();
		expect(attemptsFromDetails({})).toBeNull();
	});

	it('returns null when fields are not trusted numbers', () => {
		expect(attemptsFromDetails({ ...CONSUMING_DETAILS, attempts_remaining: '2' })).toBeNull();
		expect(attemptsFromDetails({ ...CONSUMING_DETAILS, attempt_limit: '3' })).toBeNull();
	});

	it('returns null for an unlimited session payload (limit 0)', () => {
		expect(
			attemptsFromDetails({
				attempt_limit: 0,
				attempts_used: 0,
				attempts_remaining: null,
				attempt_consumed: false
			})
		).toBeNull();
	});
});

describe('remainingFromMessage / remainingFromError (legacy fallback)', () => {
	it('parses the "(N attempts remaining)" suffix', () => {
		expect(remainingFromMessage('Persist failed (1 attempts remaining)')).toBe(1);
		expect(remainingFromMessage('gone (0 attempts remaining)')).toBe(0);
		expect(remainingFromMessage('no count here')).toBeNull();
	});

	it('reads the legacy message off an APIError and nothing else', () => {
		expect(remainingFromError(new APIError('face_mismatch', 'rejected (2 attempts remaining)'))).toBe(
			2
		);
		expect(remainingFromError(new APIError('face_mismatch', 'no suffix'))).toBeNull();
		expect(remainingFromError(new Error('plain'))).toBeNull();
	});
});

describe('attemptUpdateFromError (client-side priority policy)', () => {
	it('metadata wins over the legacy message when both are present', () => {
		const error = new APIError(
			'face_mismatch',
			'stale text (9 attempts remaining)',
			undefined,
			403,
			CONSUMING_DETAILS
		);
		// The stale message must NOT become the source of truth.
		expect(attemptUpdateFromError(error)).toEqual({ limit: 3, remaining: 2 });
	});

	it('falls back to the message count only (no fabricated limit)', () => {
		const error = new APIError('face_mismatch', 'rejected (2 attempts remaining)');
		expect(attemptUpdateFromError(error)).toEqual({ remaining: 2 });
	});

	it('returns null when neither carrier is present — keep last-known', () => {
		expect(attemptUpdateFromError(new APIError('duplicate_scan', 'dup'))).toBeNull();
		expect(attemptUpdateFromError(new Error('transport'))).toBeNull();
	});
});
