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