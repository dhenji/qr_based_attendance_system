// features/settings/service.ts
// Device-only display/behaviour prefs persisted in localStorage (no backend
// by design — theme, notifications, GPS/camera toggles are per-device, not
// per-account, so they intentionally never leave the browser).

import { browser } from '$app/environment';

export interface SettingsPrefs {
	theme: 'light' | 'dark';
	pushNotifications: boolean;
	emailNotifications: boolean;
	shareGps: boolean;
	cameraScanning: boolean;
}

export const DEFAULT_PREFS: SettingsPrefs = {
	theme: 'light',
	pushNotifications: true,
	emailNotifications: false,
	shareGps: true,
	cameraScanning: true,
};

const PREFS_KEY = 'settings_prefs';

// localStorage persistence
// Safe against corrupt JSON; server render returns defaults.
const readPrefs = (): SettingsPrefs => {
	if (!browser) return { ...DEFAULT_PREFS };
	try {
		const stored = JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null') as Partial<SettingsPrefs> | null;
		return { ...DEFAULT_PREFS, ...stored };
	} catch {
		return { ...DEFAULT_PREFS };
	}
};

export const getPrefs = (): SettingsPrefs => ({ ...readPrefs() });

export const savePrefs = (prefs: SettingsPrefs): void => {
	if (!browser) return;
	localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
};