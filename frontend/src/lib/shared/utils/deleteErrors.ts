// deleteErrors.ts
// Human-friendly messages for permanent-delete failures.
//
// The backend reports these as 409/404 AppExceptions with stable `code`
// values (e.g. `student_has_records`) and technical messages that name
// internal row ids ("Student 42 has records..."). Showing either the status
// code or the raw message leaks implementation detail, so delete flows map
// `APIError.code` here and never render `e.message` for known codes.

import { APIError } from '$lib/api/client';

const DELETE_ERROR_MESSAGES: Record<string, string> = {
	student_has_records:
		'Cannot permanently delete this student — enrollment, attendance, or excuse history is still linked. Keep the record archived instead.',
	professor_has_records:
		'Cannot permanently delete this professor — class sessions are still linked. Keep the record archived instead.',
	not_archived:
		'This record is still active. Deactivate it first, then delete from the Archive.',
	student_not_found: 'Student record not found. Refresh the list and try again.',
	professor_not_found: 'Professor record not found. Refresh the list and try again.',
	program_not_found: 'Program record not found. Refresh the list and try again.',
	program_has_offerings:
		'Cannot permanently delete this program — course offerings still use it. Move or delete those first.',
	program_has_students:
		'Cannot permanently delete this program — students are still enrolled under it. Move those students first.',
	year_level_not_found: 'Year level not found. Refresh and try again.',
	year_has_courses:
		'Cannot delete this year level — course offerings still use it. Move or delete those first.',
};

// 409 conflict codes surfaced by create/update/archive/toggle writes. Same
// rule as deletes: never render the raw backend message (row ids, codes).
const ACTION_ERROR_MESSAGES: Record<string, string> = {
	...DELETE_ERROR_MESSAGES,
	user_exists: 'An account already exists for that email. Try a different email.',
	admin_user_email_exists: 'An account already exists for that email. Try a different email.',
	student_id_exists: 'That student ID is already in use. Check the roster and try again.',
	student_email_exists: 'That email is already on the roster. Try a different email.',
	professor_email_exists: 'That email is already on the roster. Try a different email.',
	course_code_exists: 'That course code already exists. Pick a different code.',
	offering_exists: 'That offering already exists for this term. Adjust the schedule or term.',
	program_code_exists: 'That program code already exists. Pick a different code.',
	year_number_exists: 'That year level already exists for this program.',
};

// Map a delete failure to user-facing copy. Known backend `code`s return the
// friendly string above; unknown APIErrors fall back (raw messages can carry
// status codes and row ids, so they are never shown); non-API errors keep
// their message when present.
export const friendlyDeleteError = (e: unknown, fallback: string): string => {
	if (e instanceof APIError) {
		if (e.code && DELETE_ERROR_MESSAGES[e.code]) return DELETE_ERROR_MESSAGES[e.code];
		return fallback;
	}
	return e instanceof Error && e.message ? e.message : fallback;
};

// Map any archive/toggle/create/update failure to user-facing copy. Covers
// the delete codes plus 409 conflict codes (user_exists,
// course_code_exists, offering_exists, …) so pages never render raw
// `e.message` for known backend codes.
export const friendlyActionError = (e: unknown, fallback: string): string => {
	if (e instanceof APIError) {
		if (e.code && ACTION_ERROR_MESSAGES[e.code]) return ACTION_ERROR_MESSAGES[e.code];
		return fallback;
	}
	return e instanceof Error && e.message ? e.message : fallback;
};
