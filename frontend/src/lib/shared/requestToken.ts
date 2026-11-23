// shared/requestToken.ts
// Process-local monotonic guard for async loads that can overlap.
//
// A page may fire several list requests before an earlier one resolves (a
// debounced search, a tab focus, a pagination click). Only the newest request
// may write to state; otherwise a slow older response clobbers the newer one.
// Tokens complement the per-search AbortController: an abort proves a newer
// request exists, while a token covers loads that are not cancellable
// (refreshes triggered by entity events and focus).
//
// Like the in-memory idempotency store and rate limiters, this is
// process-local. Multi-instance deployments would need a shared store.

export interface RequestTokenGuard {
	/** Start a new request and return its token. */
	begin: () => number;
	/** True when `token` is still the newest request for this resource. */
	isCurrent: (token: number) => boolean;
}

export const createRequestTokenGuard = (): RequestTokenGuard => {
	let latest = 0;
	return {
		begin: () => ++latest,
		isCurrent: (token) => token === latest
	};
};
