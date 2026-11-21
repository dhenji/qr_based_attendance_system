// errors.ts
// Safe, user-facing error descriptions.
//
// This is the generic "get a message out of an unknown thrown value" helper.
// It deliberately does not replace the code-aware copy in
// shared/utils/deleteErrors.ts or features/auth/errors.ts: those map stable
// backend codes to curated strings before falling back to a message.

const messageOf = (error: unknown): string | null => {
	try {
		if (typeof error === 'string') return error;
		// APIError extends Error, so the API client's typed errors are covered
		// by the same branch as any other thrown Error.
		if (error instanceof Error) {
			return typeof error.message === 'string' ? error.message : null;
		}
		return null;
	} catch {
		// A hostile getter or Proxy must never turn error reporting into a
		// second failure.
		return null;
	}
};

export const describeError = (error: unknown, fallback: string): string => {
	const message = messageOf(error)?.trim();
	return message ? message : fallback;
};
