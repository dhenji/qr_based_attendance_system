// features/auth/tokens.ts
// Owns JWT persistence and transparent access-token renewal.
//
// The backend issues short-lived access tokens (15 min by default) alongside a
// 7-day refresh token, so every authenticated request has to be able to renew
// silently. This module registers itself as the client's 401 handler: when a
// request comes back unauthorized we exchange the refresh token once, push the
// new access token into the api client, and let the caller retry.

import { APIError, post, setAuthToken, setUnauthorizedHandler } from '$lib/api/client';
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
};

export const clearTokens = (): void => {
	if (!browser) return;
	localStorage.removeItem(ACCESS_KEY);
	localStorage.removeItem(REFRESH_KEY);
	setAuthToken(null);
};

// Re-arm the api client from storage on first load so a page refresh keeps the
// session. Safe to call more than once.
export const hydrateTokens = (): void => {
	if (!browser) return;
	setAuthToken(getAccessToken());
};

// In-flight refresh, shared so parallel 401s trigger exactly one round trip.
let refreshInFlight: Promise<string | null> | null = null;

// Guards against re-entrancy: the refresh request itself goes through the api
// client, so a 401 on it would call straight back into here. See
// refreshAccessToken for why this is checked ahead of refreshInFlight.
let isRefreshing = false;

const exchangeRefreshToken = async (): Promise<string | null> => {
	const refreshToken = getRefreshToken();
	if (!refreshToken) return null;

	isRefreshing = true;

	try {
		const response = await post<TokenResponse>('authRefresh', {
			refresh_token: refreshToken,
		});

		if (!response.access_token) return null;

		setTokens({
			access: response.access_token,
			refresh: response.refresh_token ?? refreshToken,
		});

		return response.access_token;
	} catch (error) {
		// A rejected refresh token means the session is genuinely over, so clear
		// it. A network blip (no APIError) leaves the tokens alone so the next
		// attempt can still succeed.
		if (error instanceof APIError) {
			clearTokens();
		}
		return null;
	} finally {
		isRefreshing = false;
		refreshInFlight = null;
	}
};

// Returns a new access token, or null when the session cannot be recovered.
//
// `isRefreshing` is tested *before* `refreshInFlight` on purpose. The refresh
// request itself goes through this client, so a 401 on it re-enters here — and
// by then `refreshInFlight` is already set to the promise we are inside.
// Returning that promise would await itself and hang forever, so a re-entrant
// call must bail out immediately with null and let the 401 propagate.
export const refreshAccessToken = (): Promise<string | null> => {
	if (isRefreshing) return Promise.resolve(null);
	if (refreshInFlight) return refreshInFlight;
	refreshInFlight = exchangeRefreshToken();
	return refreshInFlight;
};

setUnauthorizedHandler(refreshAccessToken);

hydrateTokens();
