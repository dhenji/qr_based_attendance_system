// features/auth/errors.ts
// Maps backend error codes to copy a student can act on.
//
// The backend raises AppException subclasses with stable `code` values (see
// backend/src/features/auth/exceptions.py) and generally readable messages.
// Branching on the code rather than the message keeps the UI stable if the
// wording changes, and lets us add guidance the API doesn't send (e.g. what to
// do about an email that isn't on the roster).

import { APIError } from '$lib/api/client';

const MESSAGES: Record<string, string> = {
	invalid_credentials: 'Email or password is incorrect.',
	// Every router limit is IP-keyed (or IP-fallback), so "this device" is
	// accurate for all of them. Kept distinct from login_otp_locked below:
	// that one is per-account, this one follows the device.
	rate_limited: 'Too many attempts from this device. Wait a moment and try again.',

	unrecognized_email:
		'No student or professor record matches that email. Ask an administrator to add you to the roster.',
	user_exists: 'An account already exists for that email. Try logging in instead.',
	ambiguous_account:
		'This email matches more than one record. Contact an administrator to resolve it.',

	otp_invalid: 'That code is incorrect. Check your email and try again.',
	otp_expired: 'That code has expired. Request a new one.',
	login_otp_locked:
		'Too many incorrect codes. Wait a few minutes before trying again, or start over.',

	invalid_mfa_code: 'Invalid verification code.',
	mfa_already_enabled: 'Two-factor authentication is already enabled.',

	password_policy_violation: 'Password does not meet the required policy.',
	password_reused: 'New password must be different from your current one.',
	current_password_invalid: 'Your current password is incorrect.',

	invalid_captcha: 'Captcha verification failed. Please try again.',

	missing_token: 'Your session has expired. Please sign in again.',
	invalid_token: 'Your session has expired. Please sign in again.',
	user_not_found: 'Your account is no longer active. Contact an administrator.',
};

// "Account is temporarily locked due to too many failed attempts. Try again
// in N minutes" — the count is ceil-rounded in auth/service.py, so "1" means
// "less than a minute left".
const LOCKOUT_MINUTES = /try again in (\d+)\s*minute/i;

const ACCOUNT_LOCKED_FALLBACK = 'This account is temporarily locked. Please try again later.';

// Turn any thrown value into a message worth showing.
//
// Prefers our own copy for known codes, falls back to the server's message for
// unknown ones (validation details, for example), and finally to the caller's
// default.
export const toAuthMessage = (error: unknown, fallback: string): string => {
	if (error instanceof APIError) {
		// The static copy would discard the remaining minutes, which is the one
		// thing a locked-out user needs to know. Parse the count out of the
		// backend message and keep the generic line as a fallback (mock mode,
		// drifted wording).
		if (error.code === 'account_locked') {
			const match = error.message.match(LOCKOUT_MINUTES);
			if (match) {
				const minutes = match[1];
				return `This account is temporarily locked. Try again in ${minutes} minute${minutes === '1' ? '' : 's'}.`;
			}
			return ACCOUNT_LOCKED_FALLBACK;
		}
		return MESSAGES[error.code] ?? error.message ?? fallback;
	}
	return error instanceof Error && error.message ? error.message : fallback;
};
