// shared/utils/revalidateOnFocus.ts
// Refetch-on-return for admin pages (issue #221).
//
// A stale tab has no other signal that records changed elsewhere: there is
// no polling, no WebSocket/SSE, and no backend push endpoint. Re-running the
// page's own refresh when the tab becomes visible again closes that gap with
// zero idle requests — hidden tabs never fetch. Same convention as the
// student/professor layout badge polling (focus + visibilitychange,
// fail-soft), minus the interval timer.
//
// Guards live in two places: this helper skips hidden documents and swallows
// listener errors; the page callback skips while its store is loading (every
// admin init* sets loading synchronously before its first await, so a rapid
// focus burst still costs one request) and reuses stored filters/page via
// the existing refresh*().

import { browser } from '$app/environment';

export const onFocusRevalidate = (cb: () => void): (() => void) => {
	// Pages only call this inside onMount (client-only), but the guard keeps
	// the module safe if that ever changes.
	if (!browser) return () => {};

	const run = () => {
		if (document.hidden) return;
		try {
			cb();
		} catch {
			// Fail-soft: a focus return must never break the visible page.
		}
	};
	const onFocus = () => run();
	const onVisibility = () => {
		if (document.visibilityState === 'visible') run();
	};
	window.addEventListener('focus', onFocus);
	document.addEventListener('visibilitychange', onVisibility);
	return () => {
		window.removeEventListener('focus', onFocus);
		document.removeEventListener('visibilitychange', onVisibility);
	};
};
