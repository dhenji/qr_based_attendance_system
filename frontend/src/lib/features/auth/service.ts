// features/auth/service.ts
// Auth calls against the real backend (mounted under /api/auth).
//
// Every function maps camelCase in, camelCase out, and translates the backend's
// snake_case on the wire — the same pattern features/liveness/service.ts uses.
// Domain errors arrive as APIError with a stable `code` (e.g. 'otp_expired',
// 'user_exists'); callers branch on that rather than on the message.

import { APIError, get, isMockMode, post } from '$lib/api/client';
import type {
	BackupCodesResponse,
	BackupCodesSummaryResponse,
	ChangePasswordRequest,
	LoginOtpResendRequest,
	LoginOtpVerifyRequest,
	LoginRequest,
	MeResponse,
	MfaDisableRequest,
	MfaSetupResponse,
	MfaVerifyRequest,
	OtpRequest,
	OtpVerifyRequest,
	OtpPurpose,
	RegisterRequest,
	TokenResponse,
} from '$lib/shared/types';
import {
	mockForgotPassword,
	mockForgotPasswordVerify,
	mockLogin,
	mockLoginOtpVerify,
	mockMe,
	mockMfaVerify,
	mockNoop,
	mockRegister,
	mockResetPassword,
} from '$lib/features/auth/mock';

// Send a 6-digit OTP. `claim` proves ownership of a roster email before the
// account is created; `forget_password` additionally requires the recovery
// grant minted by forgotPasswordVerify (Step 2 of the recovery wizard).
export const requestOtp = async (
	email: string,
	purpose: OtpPurpose = 'claim',
	recoveryToken?: string
): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: OtpRequest = { email: email.trim().toLowerCase(), purpose };
	if (recoveryToken) body.recovery_token = recoveryToken;
	await post<void>('authOtpRequest', body);
};

// Standalone OTP check. Registration verifies the code itself, so this is only
// needed where a flow wants to confirm an address before continuing.
export const verifyOtp = async (
	email: string,
	code: string,
	purpose: OtpPurpose = 'claim'
): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: OtpVerifyRequest = {
		email: email.trim().toLowerCase(),
		purpose,
		code: code.trim(),
	};
	await post<void>('authOtpVerify', body);
};

// Claim-based registration. The backend verifies the CLAIM OTP, matches the
// email against the student/professor roster and links the account, so the role
// is never sent from here.
//
// Throws APIError: 'unrecognized_email' (404, no roster row), 'user_exists'
// (409), 'otp_invalid' / 'otp_expired' (400).
export const register = async (input: {
	email: string;
	otpCode: string;
	password: string;
	securityQuestion: string;
	securityAnswer: string;
}): Promise<TokenResponse> => {
	if (isMockMode()) return mockRegister();

	const body: RegisterRequest = {
		email: input.email.trim().toLowerCase(),
		purpose: 'claim',
		otp_code: input.otpCode.trim(),
		password: input.password,
		security_question: input.securityQuestion.trim(),
		security_answer: input.securityAnswer.trim(),
	};
	return post<TokenResponse>('authRegister', body);
};

export const login = async (
	email: string,
	password: string,
	turnstileToken?: string | null
): Promise<TokenResponse> => {
	if (isMockMode()) return mockLogin(email);

	const body: LoginRequest = { email: email.trim().toLowerCase(), password };
	// Forwarded only when the page holds a Turnstile token; omitted otherwise
	// so the backend no-ops when its secret is empty. Required once
	// TURNSTILE_SECRET is set (400 invalid_captcha without it).
	if (turnstileToken) body.turnstile_token = turnstileToken;
	return post<TokenResponse>('authLogin', body);
};

// Login OTP (mandatory second factor). The password step returns
// {otp_pending: true, otp_token} instead of tokens; verify exchanges the
// grant plus the emailed 6-digit code for a session. Admins with MFA enabled
// get an MFA challenge back (OTP then TOTP), which doMfaVerify finishes.
//
// Throws APIError: 'otp_invalid' / 'otp_expired' (400),
// 'login_otp_locked' (423), 'invalid_credentials' (400, grant rejected or
// the account is gone).
export const verifyLoginOtp = async (
	otpToken: string,
	code: string
): Promise<TokenResponse> => {
	if (isMockMode()) return mockLoginOtpVerify();

	const body: LoginOtpVerifyRequest = { otp_token: otpToken, code: code.trim() };
	return post<TokenResponse>('authLoginOtpVerify', body);
};

// Mint a fresh login OTP. The grant proves the password gate was passed, so
// no email is posted; the previous code is burned server-side. Flood control
// lives in the service (5/per minute per IP).
//
// Throws APIError: 'rate_limited' (429), 'invalid_credentials' (400).
export const resendLoginOtp = async (otpToken: string): Promise<void> => {
	if (isMockMode()) return mockNoop();

	await post<void>('authLoginOtpResend', { otp_token: otpToken });
};

// Current identity. Returns null when the token is missing, expired beyond
// refresh, or the account is inactive.
export const me = async (): Promise<MeResponse | null> => {
	if (isMockMode()) return mockMe();

	try {
		return await get<MeResponse>('authMe');
	} catch (error) {
		if (error instanceof APIError && (error.status === 401 || error.status === 403)) {
			return null;
		}
		throw error;
	}
};

// Exchange a preauth token (or a live session) plus a TOTP / backup code for a
// real token pair. Used to finish an MFA-gated login.
export const verifyMfa = async (code: string, preauthToken?: string | null): Promise<TokenResponse> => {
	if (isMockMode()) return mockMfaVerify();

	const body: MfaVerifyRequest = { code: code.trim() };
	if (preauthToken) body.preauth_token = preauthToken;
	return post<TokenResponse>('authMfaVerify', body);
};

// --- MFA enrolment and recovery ------------------------------------------------
//
// `mfa_enabled` has exactly two writers on the backend: `verify_mfa` sets it
// True, `disable_mfa` sets it False. Nothing else may change it — in
// particular `admin_reset_password` deliberately leaves MFA alone, so an admin
// resetting a password cannot strip a second factor. Every function below maps
// to one of those writers and nothing else.
//
// Throws APIError: 'mfa_already_enabled' (409, setup when already on),
// 'mfa_not_enabled' (409, disable when already off), 'current_password_invalid'
// (400), 'invalid_mfa_code' (400).
//
// None of these branch on isMockMode: `apiCall` already consults the endpoint
// def's `mock` when PUBLIC_MOCK_MODE=true.

// Step 1 of enabling. Mints and stores the secret but does NOT enable MFA —
// this returns a `qr_url` (an otpauth:// URI, not an image) plus the same value
// again as `manual_entry_key`. Calling it twice silently overwrites the first
// secret, so the UI must not offer a casual retry.
export const setupMfa = async (): Promise<MfaSetupResponse> =>
	post<MfaSetupResponse>('authMfaSetup');

// The only path back to `mfa_enabled = False`. Password-verified, and it stamps
// `used_at` on every unconsumed backup code so none survives the disable.
export const disableMfa = async (password: string): Promise<void> => {
	const body: MfaDisableRequest = { password };
	await post<void>('authMfaDisable', body);
};

// Regenerating invalidates the whole previous batch (each outstanding code is
// stamped used, then 10 fresh ones are inserted), so this is the only way to
// get a full set back after one is spent.
export const generateBackupCodes = async (): Promise<BackupCodesResponse> =>
	post<BackupCodesResponse>('authMfaBackupCodesGenerate');

// Counts for the most recent batch only — never codes or hashes. Works even
// when MFA is off, which is what makes pre-emptive generation possible.
export const listBackupCodes = async (): Promise<BackupCodesSummaryResponse> =>
	get<BackupCodesSummaryResponse>('authMfaBackupCodesSummary');

export const changePassword = async (
	currentPassword: string,
	newPassword: string,
	securityQuestion?: string,
	securityAnswer?: string
): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: ChangePasswordRequest = {
		current_password: currentPassword,
		new_password: newPassword,
	};
	if (securityQuestion) body.security_question = securityQuestion;
	if (securityAnswer) body.security_answer = securityAnswer;
	await post<void>('authChangePassword', body);
};

// Forgot-password recovery (ADR-056), mirroring the 4-step wizard:
//  1. forgotPassword(email) -> { question } (decoy for unknown emails).
//  2. forgotPasswordVerify(email, answer) -> { recovery_token } (5-min grant).
//  3. requestOtp(email, 'forget_password', recoveryToken) + verifyOtp.
//  4. resetPassword(email, otpCode, newPassword) -> TokenResponse (the
//     session itself, or an MFA challenge for MFA-enabled accounts).
// Throws APIError: 'security_answer_invalid' (400), 'recovery_locked' (423),
// 'otp_invalid' / 'otp_expired' (400), 'unrecognized_email' (404),
// 'password_policy_violation' (422), 'invalid_captcha' (400).
export interface ForgotPasswordQuestion {
	question: string;
	set: boolean;
}

export const forgotPassword = async (
	email: string,
	turnstileToken?: string | null
): Promise<ForgotPasswordQuestion> => {
	if (isMockMode()) return mockForgotPassword();

	const body: Record<string, string> = { email: email.trim().toLowerCase() };
	// Same Turnstile contract as login: omitted when unconfigured, enforced
	// once TURNSTILE_SECRET is set.
	if (turnstileToken) body.turnstile_token = turnstileToken;
	return post<ForgotPasswordQuestion>('authForgotPassword', body);
};

export const forgotPasswordVerify = async (
	email: string,
	answer: string
): Promise<{ recoveryToken: string }> => {
	if (isMockMode()) return mockForgotPasswordVerify();

	const response = await post<{ recovery_token: string }>('authForgotPasswordVerify', {
		email: email.trim().toLowerCase(),
		answer: answer.trim()
	});
	return { recoveryToken: response.recovery_token };
};

export const resetPassword = async (
	email: string,
	otpCode: string,
	newPassword: string
): Promise<TokenResponse> => {
	if (isMockMode()) return mockResetPassword(email);

	return post<TokenResponse>('authResetPassword', {
		email: email.trim().toLowerCase(),
		otp_code: otpCode.trim(),
		new_password: newPassword
	});
};

// Authenticated password recovery: the backend derives the recipient email from
// the session, so no email is sent from the client.
export const startPasswordRecovery = async (): Promise<{
	recoveryToken: string;
	maskedEmail: string;
}> => {
	if (isMockMode()) {
		return { recoveryToken: 'mock-recovery-token', maskedEmail: 'j***@example.com' };
	}

	const response = await post<{ recovery_token: string; masked_email: string }>(
		'authPasswordRecoveryStart',
		{}
	);
	return { recoveryToken: response.recovery_token, maskedEmail: response.masked_email };
};

export const resetPasswordAuthenticated = async (
	otpCode: string,
	newPassword: string
): Promise<TokenResponse> => {
	if (isMockMode()) return mockResetPassword('mock@example.com');

	return post<TokenResponse>('authPasswordRecoveryReset', {
		otp_code: otpCode.trim(),
		new_password: newPassword
	});
};

// Set/update the signed-in account's security question + answer (the pair
// the forgot-password wizard quizzes). Authenticated; 204, no content back.
export const setSecurityQuestion = async (question: string, answer: string): Promise<void> => {
	if (isMockMode()) return mockNoop();

	await post<void>('authSecurityQuestion', {
		question: question.trim(),
		answer: answer.trim()
	});
};

export const logout = async (): Promise<void> => {
	if (isMockMode()) return mockNoop();
	try {
		await post<void>('authLogout', {});
	} catch {
		// Best-effort: clear locally regardless.
	}
};

export const getSessionPolicy = async (): Promise<{
	idle_timeout_minutes: number;
	idle_warning_minutes: number;
}> => {
	if (isMockMode()) {
		return { idle_timeout_minutes: 45, idle_warning_minutes: 5 };
	}
	return get<{ idle_timeout_minutes: number; idle_warning_minutes: number }>('authSessionPolicy');
};
