// features/liveness/errors.ts
// Maps scan rejection codes to copy a student can act on.
//
// The backend raises AppException subclasses with stable `code` values and
// generally readable messages. Branching on the code rather than the message
// keeps the UI stable if the wording changes, and lets us add guidance the
// API doesn't send (e.g. what to do about an expired session).

import { APIError } from '$lib/api/client';

export const SCAN_ERROR_MESSAGES: Record<string, string> = {
	duplicate_scan: 'Your attendance has already been recorded for this session. Check your attendance record.',
	outside_geofence: 'You are outside the permitted attendance area. Move closer to the designated location and try again.',
	liveness_failed: 'Liveness check failed. Try again in good lighting.',
	face_mismatch: 'Face did not match the enrolled record. Try again.',
	face_not_enrolled: 'Face enrollment is required before you can proceed. Contact your administrator to complete your face enrollment.',
	not_enrolled: 'You are not enrolled in this course offering.',
	student_number_mismatch: 'That ID number does not match your account.',
	student_not_found: 'No student record found for your account. Contact an administrator.',
	session_expired: 'This attendance session has expired. Ask your professor whether a new session is available.',
	session_not_started: 'This attendance session has not started yet. Please wait until the scheduled start time.',
	session_not_found: 'We could not find the session associated with this QR code. Ask your professor to verify the session.',
	offering_not_found: 'We could not find the session associated with this QR code. Ask your professor to verify the session.',
	stub_embedding: 'Your face enrollment needs to be updated. Contact your administrator to re-enroll.',
	rate_limited: 'Too many attendance attempts have been made. Wait for the indicated time before trying again.',
	invalid_token: 'Your login session has expired. Sign in again and retry the scan.',
	insufficient_permissions: 'You are not authorized to submit attendance for this session. Verify you are using the correct account.',
	forbidden: 'You are not authorized to submit attendance for this session. Verify you are using the correct account.',
	not_found: 'We could not find the session associated with this QR code. Ask your professor to verify the session.',
	validation_error: 'Some of the submitted attendance data was invalid. Rescan the QR code and try again.',
	network_error: 'We could not connect to the attendance service. Check your internet connection and try again.',
	request_timeout: 'The request timed out. Check your connection and try again.',
	request_cancelled: 'The request was cancelled. Try again.',
	request_failed: 'We could not process your attendance right now. Try again later. If the problem persists, contact support.',
	internal_error: 'We could not process your attendance right now. Try again later. If the problem persists, contact support.',
	location_permission_denied: 'Location permission is required to verify your attendance. Enable location access in your device settings.',
	location_timeout: 'We could not determine your current location in time. Move to an area with a clearer signal and try again.',
	location_unavailable: 'We could not determine your current location. Enable location services and try again.'
};

export const toScanMessage = (error: unknown, fallback: string): string => {
	if (error instanceof APIError) {
		if (error.code && SCAN_ERROR_MESSAGES[error.code]) {
			return SCAN_ERROR_MESSAGES[error.code];
		}
		if (error.status === 410) {
			return 'This session has closed for scanning.';
		}
		return fallback;
	}
	return error instanceof Error && error.message ? error.message : fallback;
};
