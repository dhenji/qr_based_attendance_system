// features/liveness/attempts.ts
// Deriving attempt state from error responses (attempt-metadata contract).
//
// The backend is the authoritative source of remaining-attempt counts. A
// consuming outcome (post-increment failure, exhaustion, success) reports
// machine-readable metadata in the error envelope (`detail.details`); a
// pre-increment failure reports none, which by contract means "nothing was
// consumed" — so the client keeps its last-known count and never guesses.
// The message-text reader below exists only for backends predating the
// contract and must never be the primary source.

import { APIError } from '$lib/api/client';

export interface AttemptInfo {
	/** Per-session attempt cap (always > 0 when metadata is present). */
	limit: number;
	/** Attempts left after this request's own consumption; clamped ≥ 0. */
	remaining: number;
}

// Authoritative metadata from the error envelope. Numeric-typed fields only:
// a malformed payload is treated as absent rather than trusted.
export const attemptsFromDetails = (
	details: Record<string, unknown> | undefined
): AttemptInfo | null => {
	if (!details || typeof details !== 'object') return null;
	const limit = details.attempt_limit;
	const remaining = details.attempts_remaining;
	if (typeof limit !== 'number' || !(limit > 0)) return null;
	if (typeof remaining !== 'number') return null;
	return { limit, remaining };
};

// Legacy carrier (pre-contract backends): "(N attempts remaining)" appended
// to the human-readable error message. Fallback only.
export const remainingFromMessage = (message: string): number | null => {
	const match = message.match(/\((\d+)\s+attempts?\s+remaining\)/i);
	if (!match) return null;
	const value = Number(match[1]);
	return Number.isFinite(value) ? value : null;
};

export const remainingFromError = (error: unknown): number | null => {
	if (!(error instanceof APIError) || !error.message) return null;
	return remainingFromMessage(error.message);
};

export interface AttemptUpdate {
	/** Present only when authoritative envelope metadata carries the cap. */
	limit?: number;
	remaining?: number;
}

// The client-side policy in one pure function: envelope metadata wins;
// the legacy message suffix is a fallback that updates the count only
// (it carries no limit); with neither, null means "keep last-known" —
// by contract a metadata-absent response consumed nothing, so the
// last-known value stands and is never optimistically decremented.
export const attemptUpdateFromError = (error: unknown): AttemptUpdate | null => {
	const fromDetails =
		error instanceof APIError ? attemptsFromDetails(error.details) : null;
	if (fromDetails) {
		return { limit: fromDetails.limit, remaining: fromDetails.remaining };
	}
	const remaining = remainingFromError(error);
	if (remaining === null) return null;
	return { remaining };
};
