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
	mockMe,
	mockMfaVerify,
	mockNoop,
	mockRegister,
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

export const login = async (email: string, password: string): Promise<TokenResponse> => {
	if (isMockMode()) return mockLogin(email);

	const body: LoginRequest = { email: email.trim().toLowerCase(), password };
	return post<TokenResponse>('authLogin', body);
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

export const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: ChangePasswordRequest = {
		current_password: currentPassword,
		new_password: newPassword,
	};
	await post<void>('authChangePassword', body);
};

// Forgot-password recovery (ADR-056), mirroring the 4-step wizard:
//  1. forgotPassword(email) -> { question } (decoy for unknown emails).
//  2. forgotPasswordVerify(email, answer) -> { recovery_token } (5-min grant).
//  3. requestOtp(email, 'forget_password', recoveryToken) + verifyOtp.
//  4. resetPassword(email, otpCode, newPassword) -> 204.
// Throws APIError: 'security_answer_invalid' (400), 'recovery_locked' (423),
// 'otp_invalid' / 'otp_expired' (400), 'unrecognized_email' (404),
// 'password_policy_violation' (422), 'invalid_captcha' (400).
export interface ForgotPasswordQuestion {
	question: string;
	set: boolean;
}

export const forgotPassword = async (email: string): Promise<ForgotPasswordQuestion> => {
	if (isMockMode()) return mockForgotPassword();

	return post<ForgotPasswordQuestion>('authForgotPassword', {
		email: email.trim().toLowerCase()
	});
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
): Promise<void> => {
	if (isMockMode()) return mockNoop();

	await post<void>('authResetPassword', {
		email: email.trim().toLowerCase(),
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
