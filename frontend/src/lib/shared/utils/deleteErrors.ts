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
	year_level_not_found: 'Year level not found. Refresh and try again.',
	year_has_courses:
		'Cannot delete this year level — course offerings still use it. Move or delete those first.',
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
