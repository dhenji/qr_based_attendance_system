// features/auth/idle.ts
// Client-side idle-session watcher. Tracks user activity and fires a warning
// shortly before the idle timeout, then logs out when the timeout elapses.
//
// This is UX + defense in depth only; the server remains authoritative via
// token expiry. No server-side idle tracking is performed.

import { browser } from '$app/environment';

export interface IdleWatcherOptions {
	timeoutMs: number;
	warningMs: number;
	onWarning: () => void;
	onIdle: () => void;
}

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'visibilitychange'] as const;

export function startIdleWatcher(options: IdleWatcherOptions): () => void {
	if (!browser) return () => {};

	const { timeoutMs, warningMs, onWarning, onIdle } = options;

	let lastActivity = Date.now();
	let warningTimer: ReturnType<typeof setTimeout> | null = null;
	let idleTimer: ReturnType<typeof setTimeout> | null = null;
	let warned = false;

	const clearTimers = () => {
		if (warningTimer) clearTimeout(warningTimer);
		if (idleTimer) clearTimeout(idleTimer);
		warningTimer = null;
		idleTimer = null;
	};

	const reset = () => {
		lastActivity = Date.now();
		warned = false;
		clearTimers();
		const warnDelay = Math.max(timeoutMs - warningMs, 0);
		warningTimer = setTimeout(() => {
			if (!warned) {
				warned = true;
				onWarning();
			}
		}, warnDelay);
		idleTimer = setTimeout(() => {
			onIdle();
		}, timeoutMs);
	};

	const onActivity = () => {
		if (document.visibilityState !== 'visible') return;
		// Reset only if the user actually interacted after a warning; always
		// reset timers on any activity before idle elapses.
		reset();
	};

	for (const event of ACTIVITY_EVENTS) {
		window.addEventListener(event, onActivity, { passive: true });
	}
	document.addEventListener('visibilitychange', onActivity);

	reset();

	const cleanup = () => {
		clearTimers();
		for (const event of ACTIVITY_EVENTS) {
			window.removeEventListener(event, onActivity);
		}
		document.removeEventListener('visibilitychange', onActivity);
	};
	(cleanup as { reset?: () => void }).reset = reset;
	return cleanup;
}
