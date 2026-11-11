// features/auth/tokens.ts
// Owns JWT persistence and transparent access-token renewal.
//
// The backend issues short-lived access tokens (15 min by default) alongside a
// 7-day refresh token, so every authenticated request has to be able to renew
// silently. This module registers itself as the client's 401 handler: when a
// request comes back unauthorized we exchange the refresh token once, push the
// new access token into the api client, and let the caller retry.

import { APIError, isMockMode, post, setAuthToken, setUnauthorizedHandler } from '$lib/api/client';
import type { TokenResponse } from '$lib/shared/types';
import { browser } from '$app/environment';

const ACCESS_KEY = 'attendly_access_token';
const REFRESH_KEY = 'attendly_refresh_token';

export const getAccessToken = (): string | null =>
	browser ? localStorage.getItem(ACCESS_KEY) : null;

export const getRefreshToken = (): string | null =>
	browser ? localStorage.getItem(REFRESH_KEY) : null;

export const hasTokens = (): boolean => Boolean(getAccessToken() || getRefreshToken());

// Persist a token pair and arm the api client with the new access token.
// A missing refresh_token keeps the previous one — the backend only rotates the
// pair on some flows, and dropping it would end a still-valid session.
export const setTokens = (tokens: {
	access: string | null;
	refresh?: string | null;
}): void => {
	if (!browser) return;

	if (tokens.access) {
		localStorage.setItem(ACCESS_KEY, tokens.access);
	} else {
		localStorage.removeItem(ACCESS_KEY);
	}

	if (tokens.refresh) {
		localStorage.setItem(REFRESH_KEY, tokens.refresh);
	}

	setAuthToken(tokens.access);
	scheduleProactiveRefresh();
};

export const clearTokens = (): void => {
	if (!browser) return;
	localStorage.removeItem(ACCESS_KEY);
	localStorage.removeItem(REFRESH_KEY);
	setAuthToken(null);
	cancelProactiveRefresh();
};

// Re-arm the api client from storage on first load so a page refresh keeps the
// session. Safe to call more than once.
export const hydrateTokens = (): void => {
	if (!browser) return;
	setAuthToken(getAccessToken());
};

// In-flight refresh, shared so parallel 401s trigger exactly one round trip.
let refreshInFlight: Promise<string | null> | null = null;

const exchangeRefreshToken = async (): Promise<string | null> => {
	const refreshToken = getRefreshToken();
	if (!refreshToken) {
		refreshInFlight = null;
		return null;
	}

	try {
		let response: TokenResponse;

		if (isMockMode()) {
			// Mock mode never hits the network and never returns a 401, so it is
			// safe to go through the normal client (which also serves fixtures).
			response = await post<TokenResponse>('authRefresh', {
				refresh_token: refreshToken,
			});
		} else {
			// Use a raw fetch for the refresh call itself so a 401 on it does NOT
			// re-enter `refreshAccessToken` (which would deadlock on the in-flight
			// promise). Every other request keeps going through the client and its
			// 401-retry handler, so concurrent 401s still await this promise.
			const rawBase = import.meta.env.PUBLIC_API_URL as string | undefined;
			const baseUrl = (
				rawBase ||
				(typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000')
			).replace(/\/+$/, '');
			const url = `${baseUrl}/api/auth/refresh`;

			const res = await fetch(url, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ refresh_token: refreshToken }),
				credentials: 'include',
			});

			if (!res.ok) {
				// Any HTTP failure here means the refresh credential is unusable,
				// so drop the session. (Network failures throw and skip this.)
				clearTokens();
				return null;
			}

			try {
				response = (await res.json()) as TokenResponse;
			} catch {
				clearTokens();
				return null;
			}
		}

		if (!response.access_token) {
			clearTokens();
			return null;
		}

		setTokens({
			access: response.access_token,
			refresh: response.refresh_token ?? refreshToken,
		});

		return response.access_token;
	} catch (error) {
		// A rejected refresh token means the session is genuinely over, so clear
		// it. A network blip (no APIError / fetch rejection) leaves the tokens
		// alone so the next attempt can still succeed.
		if (error instanceof APIError) {
			clearTokens();
		}
		return null;
	} finally {
		refreshInFlight = null;
	}
};

// Returns a new access token, or null when the session cannot be recovered.
//
// Single-flighted via `refreshInFlight`, so parallel 401s all await the same
// refresh and retry afterwards. The refresh request itself uses a raw fetch (see
// above), so it never re-enters this function and cannot deadlock.
export const refreshAccessToken = (): Promise<string | null> => {
	if (refreshInFlight) return refreshInFlight;
	refreshInFlight = exchangeRefreshToken();
	return refreshInFlight;
};

// Proactive refresh: schedule a refresh ~2 minutes before the access token
// expires so active users never hit a request-time 401.
let proactiveTimer: ReturnType<typeof setTimeout> | null = null;

const decodeAccessExp = (token: string): number | null => {
	try {
		const part = token.split('.')[1];
		if (!part) return null;
		const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'));
		const payload = JSON.parse(json) as { exp?: unknown };
		return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
	} catch {
		return null;
	}
};

export const cancelProactiveRefresh = (): void => {
	if (proactiveTimer) {
		clearTimeout(proactiveTimer);
		proactiveTimer = null;
	}
};

export const scheduleProactiveRefresh = (): void => {
	cancelProactiveRefresh();
	if (!browser) return;
	const token = getAccessToken();
	if (!token) return;
	const exp = decodeAccessExp(token);
	if (!exp) return;
	const leadMs = 2 * 60 * 1000;
	const delay = exp - Date.now() - leadMs;
	if (delay <= 0) {
		void refreshAccessToken().then((fresh) => {
			if (fresh) {
				scheduleProactiveRefresh();
			} else if (getAccessToken() || getRefreshToken()) {
				// Transient (network) failure: retry shortly without clearing.
				proactiveTimer = setTimeout(scheduleProactiveRefresh, 60 * 1000);
			}
		});
		return;
	}
	proactiveTimer = setTimeout(() => {
		void refreshAccessToken().then((fresh) => {
			if (fresh) {
				scheduleProactiveRefresh();
			} else if (getAccessToken() || getRefreshToken()) {
				proactiveTimer = setTimeout(scheduleProactiveRefresh, 60 * 1000);
			}
		});
	}, delay);
};

// Cross-tab synchronisation: react to token changes made in another tab.
export const startTokenSync = (handlers: {
	onCleared: () => void;
	onChanged: () => void;
}): (() => void) => {
	if (!browser) return () => {};
	const handler = (event: StorageEvent) => {
		if (event.key !== ACCESS_KEY && event.key !== REFRESH_KEY) return;
		if (!getAccessToken() && !getRefreshToken()) {
			handlers.onCleared();
		} else {
			hydrateTokens();
			handlers.onChanged();
		}
	};
	window.addEventListener('storage', handler);
	return () => window.removeEventListener('storage', handler);
};

setUnauthorizedHandler(refreshAccessToken);

hydrateTokens();
