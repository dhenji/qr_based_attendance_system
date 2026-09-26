// features/auth/service.ts
// Auth calls against the real backend (mounted under /api/auth).
//
// Every function maps camelCase in, camelCase out, and translates the backend's
// snake_case on the wire — the same pattern features/liveness/service.ts uses.
// Domain errors arrive as APIError with a stable `code` (e.g. 'otp_expired',
// 'user_exists'); callers branch on that rather than on the message.

import { APIError, get, isMockMode, post } from '$lib/api/client';
import type {
	ChangePasswordRequest,
	LoginRequest,
	MeResponse,
	MfaVerifyRequest,
	OtpRequest,
	OtpVerifyRequest,
	OtpPurpose,
	RegisterRequest,
	TokenResponse,
} from '$lib/shared/types';
import {
	mockLogin,
	mockMe,
	mockMfaVerify,
	mockNoop,
	mockRegister,
} from '$lib/features/auth/mock';

// Send a 6-digit OTP. `claim` proves ownership of a roster email before the
// account is created; `forget_password` additionally requires a recovery grant
// obtained from the security-question step.
export const requestOtp = async (email: string, purpose: OtpPurpose = 'claim'): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: OtpRequest = { email: email.trim().toLowerCase(), purpose };
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
	username: string;
	password: string;
	securityQuestion: string;
	securityAnswer: string;
}): Promise<TokenResponse> => {
	if (isMockMode()) return mockRegister();

	const body: RegisterRequest = {
		email: input.email.trim().toLowerCase(),
		purpose: 'claim',
		otp_code: input.otpCode.trim(),
		username: input.username.trim(),
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

export const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
	if (isMockMode()) return mockNoop();

	const body: ChangePasswordRequest = {
		current_password: currentPassword,
		new_password: newPassword,
	};
	await post<void>('authChangePassword', body);
};
