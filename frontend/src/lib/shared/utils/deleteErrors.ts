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
	schedule_mismatch:
		'Cannot activate this offering — its weekly scheduled hours do not match the course units requirement. Fix the meetings on its detail page first.',
	student_not_found: 'Student record not found. Refresh the list and try again.',
	professor_not_found: 'Professor record not found. Refresh the list and try again.',
	program_not_found: 'Program record not found. Refresh the list and try again.',
	program_has_offerings:
		'Cannot permanently delete this program — course offerings still use it. Move or delete those first.',
	program_has_students:
		'Cannot permanently delete this program — students are still enrolled under it. Move those students first.',
	course_not_found: 'Course record not found. Refresh the list and try again.',
	course_has_offerings:
		'Cannot permanently delete this course — offerings still use it. Move or delete those first.',
	offering_not_found: 'Offering record not found. Refresh the list and try again.',
	offering_has_enrollments:
		'Cannot permanently delete this offering — students are still enrolled. Unenroll them first.',
	offering_has_sessions:
		'Cannot permanently delete this offering — class sessions were already opened for it. Session history is kept, so keep the offering archived instead.',
	offering_has_assignments:
		'Cannot permanently delete this offering — professor assignments still reference it. End those assignments and remove the history first.',
	assignment_not_ended:
		'This assignment is still active. End it first, then remove it permanently.',
	assignment_has_sessions:
		'This assignment has attendance sessions and cannot be permanently removed. End it instead so its history stays attributed.',
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
	offering_exists: "That course is already offered for this program, term, and academic year — the year level doesn't disambiguate.",
	invalid_schedule_window: 'End time must be after start time.',
	component_exists:
		'That meeting duplicates an existing one for this offering. Change the type, days, or time.',
	program_code_exists: 'That program code already exists. Pick a different code.',
	year_number_exists: 'That year level already exists for this program.',
};

// 422 codes whose backend message is already user-facing (crafted with the
// tailored numbers — scheduled/limit/over/short plus course code, no row
// ids). Callers render `e.message` verbatim for these instead of the generic
// fallback, so the numbers are never swallowed.
export const WEEKLY_HOURS_CODES: ReadonlySet<string> = new Set([
	'weekly_hours_exceed_units',
	'weekly_hours_below_units',
]);

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
