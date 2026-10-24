// features/settings/theme.ts
// Single shared theme helper — device-local only, no backend calls.
// settings/service.ts owns persistence (localStorage `settings_prefs`);
// this module owns DOM application so every entry point behaves the same.

import { browser } from '$app/environment';
import { getPrefs, savePrefs } from '$lib/features/settings/service';

export type Theme = 'light' | 'dark';

export function getTheme(): Theme {
	const prefs = getPrefs();
	return prefs.theme === 'dark' ? 'dark' : 'light';
}

/** Apply a theme to <html>: dataset + color-scheme + theme-color meta. */
export function applyTheme(theme: Theme): void {
	if (!browser) return;
	document.documentElement.dataset.theme = theme;
	document.documentElement.style.colorScheme = theme;
	const meta = document.querySelector('meta[name="theme-color"]');
	if (meta) meta.setAttribute('content', theme === 'dark' ? '#0f172a' : '#1e3a5f');
}

/** Persist + apply. Used by the Settings segmented controls. */
export function setTheme(theme: Theme): void {
	savePrefs({ ...getPrefs(), theme });
	applyTheme(theme);
}

/**
 * Return the device to the light default when a session ends — logout, an
 * expired token, or a session that cannot be verified. Persists as well as
 * applies, so the login page (and the next person who signs in) never inherits
 * the previous session's dark mode. Device prefs are shared, not per-account;
 * this is the one preference that resets with the session.
 */
export function resetTheme(): void {
	setTheme('light');
}

/** Apply the saved preference (default light). Called once from root layout. */
export function initTheme(): void {
	applyTheme(getTheme());
}
