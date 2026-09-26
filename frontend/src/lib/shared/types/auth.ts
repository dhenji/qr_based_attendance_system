// auth.ts
// Wire types for the shared auth surface. These mirror the backend Pydantic
// schemas in backend/src/features/auth/schema.py exactly (snake_case, no
// renaming) so services can pass them straight through to the API layer.

export type OtpPurpose = 'claim' | 'forget_password';

export type AuthRole = 'super_admin' | 'admin' | 'professor' | 'student';

// POST /auth/otp/request
export interface OtpRequest {
	email: string;
	purpose?: OtpPurpose;
	recovery_token?: string | null;
}

// POST /auth/otp/verify
export interface OtpVerifyRequest extends OtpRequest {
	code: string;
}

// POST /auth/register
// The role is deliberately absent: the backend derives it from the roster match,
// and a client-supplied role is ignored.
export interface RegisterRequest extends OtpRequest {
	otp_code: string;
	username: string;
	password: string;
	security_question: string;
	security_answer: string;
}

// POST /auth/login
export interface LoginRequest {
	email: string;
	password: string;
	turnstile_token?: string | null;
}

// POST /auth/refresh
export interface RefreshRequest {
	refresh_token: string;
}

// POST /auth/mfa/verify
// Accepts a 6-digit TOTP or one of the 10 backup codes (XXXX-XXXX-XX).
export interface MfaVerifyRequest {
	code: string;
	preauth_token?: string | null;
}

// POST /auth/change-password
export interface ChangePasswordRequest {
	new_password: string;
	current_password: string;
}

// POST /auth/login | /auth/register | /auth/refresh | /auth/mfa/verify
//
// Carries no user object — identity is resolved separately via GET /auth/me.
// When mfa_pending is true, access_token/refresh_token are null and the caller
// must exchange preauth_token at /auth/mfa/verify to finish signing in.
export interface TokenResponse {
	access_token: string | null;
	refresh_token: string | null;
	mfa_pending: boolean;
	preauth_token: string | null;
	must_change_password: boolean;
}

// GET /auth/me
export interface MeResponse {
	id: number;
	role: AuthRole;
	first_name: string | null;
	last_name: string | null;
	email: string;
	mfa_enabled: boolean;
	security_question_set: boolean;
	must_change_password: boolean;
	last_login: string | null;
	// student only
	face_enrolled: boolean | null;
	face_enrolled_at: string | null;
	face_embedding_version: number | null;
	// professor only
	claim_status: string | null;
}
