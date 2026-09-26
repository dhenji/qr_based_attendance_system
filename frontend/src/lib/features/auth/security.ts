// features/auth/security.ts
// Security-question bank for the registration dropdown.
//
// Kept in sync with SECURITY_QUESTION_POOL in
// backend/src/features/auth/constants.py — that pool doubles as the decoy pool
// for forgot-password step 1, so answers chosen from here are indistinguishable
// from recovery responses. The backend does not reject questions outside this
// list, but matching it keeps the two portals consistent.
export const SECURITY_QUESTIONS = [
	'What was the name of your first pet?',
	'What was your childhood nickname?',
	'What street did you grow up on?',
	'What was the name of your first school?',
	"What is your mother's maiden name?",
	"What was your favourite teacher's name?",
	'What city were you born in?',
	'What was the name of your first car?',
	'What is the name of your favourite childhood book?',
	"What was your grandmother's favourite flower?",
] as const;

export const DEFAULT_QUESTION = SECURITY_QUESTIONS[0];

export type SecurityQA = { question: string; answer: string };

// --- Local persistence (forgot-password only) ------------------------------
//
// NOTE: this mirrors the security question into localStorage in plaintext. It
// exists solely for the not-yet-rewritten forgot-password wizard, which still
// runs entirely client-side. Once that flow is moved onto
// POST /auth/forgot-password (which returns the question from the server), this
// whole section should be deleted along with its two callers.

const STORAGE_KEY = 'security_qa';

type StoredQA = Record<string, SecurityQA>;

// Store shape: { "<email>": { question, answer } }. readAll() is safe against
// corrupt JSON (falls back to an empty map).
const readAll = (): StoredQA => {
	try {
		return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as StoredQA;
	} catch {
		return {};
	}
};

/** @deprecated Fallback answer for the legacy client-only forgot-password wizard.
 *  It lets any email "pass" step 2. Delete together with that page once it is
 *  moved onto POST /auth/forgot-password. */
export const DEFAULT_ANSWER = 'fluffy';

// Save or overwrite the Q&A pair for an email (emails normalized to lowercase).
export const saveSecurityQA = (email: string, question: string, answer: string): void => {
	const all = readAll();
	all[email.toLowerCase().trim()] = { question, answer: answer.trim() };
	localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
};

// Look up the stored Q&A for an email, or null if none exists.
export const loadSecurityQA = (email: string): SecurityQA | null => {
	return readAll()[email.toLowerCase().trim()] ?? null;
};