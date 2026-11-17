import { afterEach, describe, expect, it, vi } from 'vitest';
import { isMockMode } from '$lib/api/client';
import {
	getAccessToken,
	getRefreshToken,
	refreshAccessToken,
	setSessionEndedHandler,
	setSessionEndedSuppressed,
	setTokens,
} from './tokens';

// These tests exercise the real refresh path (a stubbed fetch). In mock mode
// the refresh call never reaches the network, so they would not test the
// transport branch under test.
const describeReal = describe.skipIf(isMockMode());

// Backend refresh rejection — any non-2xx means the credential is unusable and
// the session ends (tokens cleared + session-ended notification).
const rejectRefresh = () =>
	vi.stubGlobal(
		'fetch',
		vi.fn(
			async () =>
				new Response(
					JSON.stringify({ detail: { code: 'invalid_credentials', message: 'Invalid refresh token' } }),
					{ status: 400 }
				)
		)
	);

describeReal('refresh-token exchange session-ended notification', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		setSessionEndedHandler(null);
		setSessionEndedSuppressed(false);
		localStorage.clear();
	});

	it('notifies the handler and clears tokens when the backend rejects the refresh', async () => {
		let ended = 0;
		setSessionEndedHandler(() => {
			ended += 1;
		});
		setTokens({ access: null, refresh: 'refresh-token-1' });
		rejectRefresh();

		const fresh = await refreshAccessToken();

		expect(fresh).toBeNull();
		expect(ended).toBe(1);
		expect(getRefreshToken()).toBeNull();
		expect(getAccessToken()).toBeNull();
	});

	it('does not notify on a network failure (tokens kept for a retry)', async () => {
		let ended = 0;
		setSessionEndedHandler(() => {
			ended += 1;
		});
		setTokens({ access: null, refresh: 'refresh-token-1' });
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new TypeError('Failed to fetch');
			})
		);

		const fresh = await refreshAccessToken();

		expect(fresh).toBeNull();
		expect(ended).toBe(0);
		expect(getRefreshToken()).toBe('refresh-token-1');
	});

	it('suppresses the notification while an explicit logout runs, then resumes', async () => {
		let ended = 0;
		setSessionEndedHandler(() => {
			ended += 1;
		});
		rejectRefresh();

		setTokens({ access: null, refresh: 'refresh-token-1' });
		setSessionEndedSuppressed(true);
		await refreshAccessToken();
		expect(ended).toBe(0);

		// doLogout clears the suppression in its finally block; a later failure
		// must notify again.
		setSessionEndedSuppressed(false);
		setTokens({ access: null, refresh: 'refresh-token-2' });
		await refreshAccessToken();
		expect(ended).toBe(1);
	});

	it('does not notify on a successful refresh', async () => {
		let ended = 0;
		setSessionEndedHandler(() => {
			ended += 1;
		});
		setTokens({ access: null, refresh: 'refresh-token-1' });
		vi.stubGlobal(
			'fetch',
			vi.fn(
				async () =>
					new Response(
						JSON.stringify({ access_token: 'access-2', refresh_token: 'refresh-token-2' }),
						{ status: 200 }
					)
			)
		);

		const fresh = await refreshAccessToken();

		expect(fresh).toBe('access-2');
		expect(ended).toBe(0);
		expect(getAccessToken()).toBe('access-2');
		expect(getRefreshToken()).toBe('refresh-token-2');
	});
});
