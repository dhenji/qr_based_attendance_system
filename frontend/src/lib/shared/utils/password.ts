// password.ts
// Single home for the password-strength policy (mirrors backend
// shared/validators.password_strength plus the 8-char minimum): 8+ chars
// with an uppercase, a lowercase, a digit and a symbol. A space is not a
// symbol server-side, so it is excluded here too. Every signup/recovery
// form (login must-change, register, forgot-password, admin profile) derives
// its checklist from evaluatePassword so a policy tweak is one edit.

export const PASSWORD_MIN_LENGTH = 8;

export interface PasswordRequirements {
	length: boolean;
	upper: boolean;
	lower: boolean;
	number: boolean;
	symbol: boolean;
}

export const evaluatePassword = (value: string): PasswordRequirements => ({
	length: value.length >= PASSWORD_MIN_LENGTH,
	upper: /[A-Z]/.test(value),
	lower: /[a-z]/.test(value),
	number: /\d/.test(value),
	symbol: /[^A-Za-z0-9\s]/.test(value),
});

export const isPasswordStrong = (req: PasswordRequirements): boolean =>
	req.length && req.upper && req.lower && req.number && req.symbol;
