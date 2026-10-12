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

// POST /auth/mfa/setup — mints a TOTP secret for an already-authenticated
// account. Takes no request body.
//
// `secret` and `manual_entry_key` are the same base32 value; the backend
// returns both so a client can render either. `qr_url` is the raw
// `otpauth://totp/...` provisioning URI — NOT an image and NOT a data URI —
// so the browser has to render the QR itself.
//
// Does NOT enable MFA: it only writes `mfa_secret` and returns. `verify_mfa` is
// the only writer of `mfa_enabled = True`, so an abandoned setup leaves a stored
// secret with the flag still False.
export interface MfaSetupResponse {
	secret: string;
	qr_url: string;
	manual_entry_key: string;
}

// POST /auth/mfa/disable — password-verified, 204 on success.
export interface MfaDisableRequest {
	password: string;
}

// POST /auth/mfa/backup-codes — 10 codes, plaintext, returned exactly once.
// Stored server-side as an Argon2id hash plus an HMAC fingerprint; consuming one
// stamps `used_at` rather than deleting it.
export interface BackupCodesResponse {
	codes: string[];
	remaining: number;
}

// GET /auth/mfa/backup-codes — counts only, never hashes or codes. Reports the
// most recent batch alone, so regenerating resets both numbers to 10/10.
export interface BackupCodesSummaryResponse {
	total: number;
	remaining: number;
	last_generated_at: string | null;
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
