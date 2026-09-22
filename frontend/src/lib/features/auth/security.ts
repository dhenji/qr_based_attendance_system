// features/auth/security.ts
// Shared security-question helpers for the mock-first flow.

// Security questions
// Bank of pre-defined questions (backend mirrors this via constants.py).
// The mock flow stores the chosen Q&A per email in localStorage, keyed by email.
export const SECURITY_QUESTIONS = [
	"What was your first pet's name?",
	'In what city were you born?',
	"What is your mother's maiden name?",
	'What was the name of your first school?',
	'What is the name of your favorite teacher?',
	'What was your childhood nickname?',
] as const;

export const DEFAULT_QUESTION = SECURITY_QUESTIONS[0];
export const DEFAULT_ANSWER = 'fluffy';

export type SecurityQA = { question: string; answer: string };

const STORAGE_KEY = 'security_qa';

type StoredQA = Record<string, SecurityQA>;

// localStorage persistence
// Store shape: { "<email>": { question, answer } }. readAll() is safe against
// corrupt JSON (falls back to an empty map).
const readAll = (): StoredQA => {
	try {
		return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as StoredQA;
	} catch {
		return {};
	}
};

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