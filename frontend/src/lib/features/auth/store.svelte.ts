// features/auth/store.svelte.ts
// Auth session state using Svelte 5 runes ($state object store).
//
// This module owns the whole signed-in lifecycle: it persists the token pair,
// resolves the current user from GET /auth/me, and clears everything on
// logout. Pages call the do* actions and read authState; they never touch
// tokens or storage directly.

import type { MeResponse, TokenResponse, User } from '$lib/shared/types';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { Routes } from '$lib/shared/constants/routes';
import { withMinDuration } from '$lib/shared/utils/timing';
import {
	changePassword,
	disableMfa,
	login,
	me,
	register,
	resendLoginOtp,
	resetPassword,
	verifyLoginOtp,
	verifyMfa,
} from '$lib/features/auth/service';
import {
	clearTokens,
	hasTokens,
	hydrateTokens,
	setTokens,
} from '$lib/features/auth/tokens';
import { refreshFaceCache } from '$lib/features/student/face.svelte';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'anonymous';

// Auth state (rune-store)
// Single reactive object holding the current user, the session status, any
// pending MFA challenge, and the last error.
export const authState = $state({
	user: null as User | null,
	status: 'idle' as AuthStatus,
	// True while a do* action is in flight, for button/spinner state.
	loading: false,
	// True when login succeeded at the password step but MFA is still required.
	mfaPending: false,
	// Single-use token that /auth/mfa/verify exchanges for a real session.
	preauthToken: null as string | null,
	// True when the password step passed but the emailed login OTP is still
	// required. Students/professors with MFA never see this — their TOTP path
	// mfaPending above replaces the email step.
	otpPending: false,
	// Single-use grant that /auth/login/verify exchanges for tokens (or an
	// MFA challenge, for admins with MFA). Never touches storage.
	otpToken: null as string | null,
	mustChangePassword: false,
	error: null as string | null,
});

// Derived role helpers
// Plain functions (module-scope $derived cannot be exported) used to guard UI.
export const isAuthenticated = () => authState.status === 'authenticated' && !!authState.user;
export const isStudent = () => authState.user?.role === 'student';
export const isProfessor = () => authState.user?.role === 'professor';
export const isAdmin = () =>
	authState.user?.role === 'admin' || authState.user?.role === 'super_admin';

// Super-admin only gate for /admin/users (backend require_role(SUPER_ADMIN)).
// Plain admins share the rest of the admin portal via isAdmin().
export const isSuperAdmin = () => authState.user?.role === 'super_admin';

// Where to send a freshly authenticated user.
//
// Students and professors go to their portals; admins go to the admin
// dashboard (Phase 3 MVP shell + roster).
export const defaultRouteFor = (user: User | null): string => {
	switch (user?.role) {
		case 'student':
			return Routes.DASHBOARD;
		case 'professor':
			return Routes.PROFESSOR_DASHBOARD;
		case 'admin':
		case 'super_admin':
			return Routes.ADMIN_DASHBOARD;
		default:
			return Routes.HOME;
	}
};

const toMessage = (error: unknown, fallback: string): string =>
	error instanceof Error && error.message ? error.message : fallback;

// Minimum time authState.loading stays true, so the submit-button spinner is
// always perceivable. A fast response — a mock fixture, a cached token, a local
// API — settles inside a single frame, and a spinner that appears for less than
// one frame reads as "there is no spinner at all". This pads the flag, not the
// request, so the underlying call is unaffected.
const MIN_LOADING_MS = 400;

// Runs `action` with authState.loading raised for at least MIN_LOADING_MS.
// Callers keep their own try/catch for setting authState.error; only the
// loading bookkeeping lives here.
const withLoading = async <T>(action: () => Promise<T>): Promise<T> => {
	authState.loading = true;
	try {
		return await withMinDuration(MIN_LOADING_MS, action);
	} finally {
		authState.loading = false;
	}
};

// Map a /auth/me payload onto the view-model the UI holds. Lives here rather
// than in the service so the wire types stay confined to the API layer.
const toUser = (me: MeResponse): User => ({
	id: String(me.id),
	email: me.email,
	role: me.role,
	firstName: me.first_name,
	lastName: me.last_name,
	mfaEnabled: me.mfa_enabled,
	mustChangePassword: me.must_change_password,
	securityQuestionSet: me.security_question_set,
});

const reset = () => {
	authState.user = null;
	authState.status = 'anonymous';
	authState.mfaPending = false;
	authState.preauthToken = null;
	authState.otpPending = false;
	authState.otpToken = null;
	authState.mustChangePassword = false;
	authState.error = null;
};

// Persist a token response and resolve the signed-in user.
//
// The backend's TokenResponse carries no identity, so /auth/me is always the
// source of truth. A null result means the tokens are unusable — clear them
// rather than leaving a half-established session behind.
const establishSession = async (tokens: TokenResponse): Promise<User> => {
	setTokens({ access: tokens.access_token, refresh: tokens.refresh_token });

	const current = await me();
	if (!current) {
		clearTokens();
		reset();
		throw new Error('Your session could not be verified. Please sign in again.');
	}

	const user = toUser(current);
	authState.user = user;
	authState.status = 'authenticated';
	authState.mustChangePassword = tokens.must_change_password || current.must_change_password;
	authState.error = null;
	// Face-embedding pull (D29): background, never blocks the sign-in.
	if (current.role === 'student') {
		void refreshFaceCache(current.email, current.face_enrolled ?? false);
	}
	return user;
};

// Single-flight session restore, so concurrent guards share one /auth/me call.
let restoreInFlight: Promise<User | null> | null = null;

// Re-attach an existing session after a page load.
//
// Deliberately re-fetches /auth/me rather than trusting a cached user blob, so a
// deactivated account or a role change takes effect immediately.
export const restoreSession = (): Promise<User | null> => {
	if (!browser) return Promise.resolve(null);
	if (isAuthenticated()) return Promise.resolve(authState.user);
	if (restoreInFlight) return restoreInFlight;

	hydrateTokens();

	if (!hasTokens()) {
		authState.status = 'anonymous';
		return Promise.resolve(null);
	}

	authState.status = 'loading';
	restoreInFlight = me()
		.then((current) => {
			if (!current) {
				clearTokens();
				reset();
				return null;
			}
			authState.user = toUser(current);
			authState.status = 'authenticated';
			authState.mustChangePassword = current.must_change_password;
			if (current.role === 'student') {
				void refreshFaceCache(current.email, current.face_enrolled ?? false);
			}
			return authState.user;
		})
		.catch(() => {
			// The request itself failed (offline, API down) rather than coming back
			// 401/403 — those resolve to null and clear the tokens above. Keep the
			// token pair here so a later page load can still restore the session,
			// and just report "not signed in" for this attempt.
			authState.status = 'anonymous';
			return null;
		})
		.finally(() => {
			restoreInFlight = null;
		});

	return restoreInFlight;
};

// Actions
//
// doLogin resolves to the signed-in user, or to null when the password was
// accepted but a second factor is still required: either the emailed OTP
// (authState.otpPending holds the grant) or MFA (authState.mfaPending holds
// the preauth token). Real failures reject.
export const doLogin = async (email: string, password: string): Promise<User | null> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			const tokens = await login(email, password);

			if (tokens.otp_pending) {
				// Password accepted but the emailed OTP is still required. Hold the
				// grant and let the caller collect the code; there is no session yet.
				clearTokens();
				authState.otpPending = true;
				authState.otpToken = tokens.otp_token;
				authState.status = 'anonymous';
				return null;
			}

			if (tokens.mfa_pending) {
				// Password accepted but a second factor is required. Hold the preauth
				// token and let the caller collect the code; there is no session yet.
				clearTokens();
				authState.mfaPending = true;
				authState.preauthToken = tokens.preauth_token;
				authState.status = 'anonymous';
				return null;
			}

			return await establishSession(tokens);
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Login failed. Please try again.');
			throw error;
		}
	});
};

// Complete the login-OTP step. Resolves to the signed-in user, or to null
// when the code verified but an MFA challenge follows (admins with MFA
// enabled); authState.mfaPending is then true and holds the preauth token.
export const doLoginOtpVerify = async (code: string): Promise<User | null> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			const tokens = await verifyLoginOtp(authState.otpToken ?? '', code);

			if (tokens.mfa_pending) {
				// OTP done, TOTP now: swap the OTP grant for the preauth one and let
				// the MFA stage of the wizard finish the sign-in.
				authState.otpPending = false;
				authState.otpToken = null;
				authState.mfaPending = true;
				authState.preauthToken = tokens.preauth_token;
				authState.status = 'anonymous';
				return null;
			}

			authState.otpPending = false;
			authState.otpToken = null;
			return await establishSession(tokens);
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Verification failed. Please try again.');
			throw error;
		}
	});
};

// Ask for a fresh login OTP. The previous code is burned server-side, so the
// countdown restarts and any typed digits are cleared by the caller.
export const doLoginOtpResend = async (): Promise<void> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			await resendLoginOtp(authState.otpToken ?? '');
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Could not resend the code. Please try again.');
			throw error;
		}
	});
};

// Complete an MFA-gated login with a 6-digit TOTP or a backup code.
export const doMfaVerify = async (code: string): Promise<User> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			const tokens = await verifyMfa(code, authState.preauthToken);
			authState.mfaPending = false;
			authState.preauthToken = null;
			return await establishSession(tokens);
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Verification failed. Please try again.');
			throw error;
		}
	});
};

export const doRegister = async (input: {
	email: string;
	otpCode: string;
	password: string;
	securityQuestion: string;
	securityAnswer: string;
}): Promise<User> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			return await establishSession(await register(input));
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Registration failed. Please try again.');
			throw error;
		}
	});
};

// Complete a forgot-password reset. Step 4 returns the session directly
// (like registration, not like login): the recovery already proved inbox
// access plus the security answer, so no second login dance. Resolves to the
// signed-in user, or to null when the account has MFA enabled —
// authState.mfaPending then holds the preauth token and the caller sends the
// user to the login page for their TOTP challenge.
export const doResetPassword = async (
	email: string,
	otpCode: string,
	newPassword: string
): Promise<User | null> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			const tokens = await resetPassword(email, otpCode, newPassword);

			if (tokens.mfa_pending) {
				clearTokens();
				authState.mfaPending = true;
				authState.preauthToken = tokens.preauth_token;
				authState.status = 'anonymous';
				return null;
			}

			return await establishSession(tokens);
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Password reset failed. Please try again.');
			throw error;
		}
	});
};

export const doChangePassword = async (
	currentPassword: string,
	newPassword: string
): Promise<void> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			await changePassword(currentPassword, newPassword);
			if (authState.user) authState.user.mustChangePassword = false;
			authState.mustChangePassword = false;
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Password change failed.');
			throw error;
		}
	});
};

export const doLogout = async (): Promise<void> => {
	clearTokens();
	reset();
	await goto(Routes.HOME);
};

// --- MFA ---------------------------------------------------------------------
//
// `authState.user.mfaEnabled` is a local mirror of a two-writer backend field:
// `verify_mfa` is the only writer of True and `disable_mfa` the only path back
// to False. So neither action below patches the flag on its own — each calls
// the matching endpoint and only then updates the mirror, the same way
// doChangePassword handles mustChangePassword. Reading the mirror to decide
// which button to show is fine; writing it directly is not.

// Step 2 of enabling: confirm a TOTP (or a backup code, if the user generated
// some before enabling) to flip `mfa_enabled` True. Returns fresh tokens, which
// we store so the session survives the swap — verify_mfa mints a new pair even
// when it was called on an already-authenticated session.
export const doMfaConfirmSetup = async (code: string): Promise<void> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			const tokens = await verifyMfa(code);
			if (tokens.access_token || tokens.refresh_token) {
				setTokens({ access: tokens.access_token, refresh: tokens.refresh_token });
			}
			if (authState.user) authState.user.mfaEnabled = true;
		} catch (error: unknown) {
			authState.error = toMessage(error, 'That code was not accepted. Try the next one.');
			throw error;
		}
	});
};

// Disable MFA. Password-verified server-side, and it consumes any unspent
// backup codes in the same request, so there is nothing to clean up here.
export const doMfaDisable = async (password: string): Promise<void> => {
	authState.error = null;
	return withLoading(async () => {
		try {
			await disableMfa(password);
			if (authState.user) authState.user.mfaEnabled = false;
		} catch (error: unknown) {
			authState.error = toMessage(error, 'Could not disable MFA.');
			throw error;
		}
	});
};

// ============================================================================
// OTP window composable — shared by login, register, forgot-password
// ============================================================================

export const CODE_TTL_SECONDS = 300;
export const RESEND_COOLDOWN_SECONDS = 60;

export interface OtpWindow {
	readonly remaining: number;
	readonly resendIn: number;
	restart(): void;
	stop(): void;
}

export function createOtpWindow(
	codeTtl = CODE_TTL_SECONDS,
	cooldown = RESEND_COOLDOWN_SECONDS
): OtpWindow {
	let remaining = $state(codeTtl);
	let resendIn = $state(cooldown);
	let id: number | null = null;

	const stop = () => {
		if (id !== null) {
			window.clearInterval(id);
			id = null;
		}
	};

	const restart = () => {
		stop();
		remaining = CODE_TTL_SECONDS;
		resendIn = RESEND_COOLDOWN_SECONDS;
		id = window.setInterval(() => {
			remaining -= 1;
			if (resendIn > 0) resendIn -= 1;
			if (remaining <= 0 && resendIn <= 0) stop();
		}, 1000);
	};

	return {
		get remaining() {
			return remaining;
		},
		get resendIn() {
			return resendIn;
		},
		restart,
		stop,
	};
}

export function formatClock(seconds: number): string {
	const t = Math.max(seconds, 0);
	const m = Math.floor(t / 60);
	const s = t % 60;
	return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
