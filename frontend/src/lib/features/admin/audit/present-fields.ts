// features/admin/audit/present-fields.ts
// The vocabulary of the audit trail, and how a stored value is read.
//
// Split out of `present.ts` so the WORDING lives apart from the RENDERING:
// the maps below are the single source of what an action is called, what a
// snapshot field is called, and how a raw value becomes something an
// administrator can read. The chip, the diff, the summary sentence and the
// CSV export all read from here, so they cannot drift apart.
//
// Every map is keyed by the field name the server's `_snapshot` methods use
// (`backend/src/features/*/service.py`). A field the maps do not know yet
// renders under its own name — visible, not silent.

import type { AuditAction, AuditEntityType } from '$lib/shared/types';
import { formatBytes } from '$lib/shared/utils/format';
import {
	emptyLabelContext,
	offeringTitle,
	type AuditLabelContext,
} from '$lib/features/admin/audit/labels';

// --- Vocabulary -------------------------------------------------------------

/**
 * The controlled verb vocabulary.
 *
 * One map, so the action chip, the CSV export and the summary sentence can
 * never disagree about what an action is called.
 */
export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
	create: 'Created',
	update: 'Updated',
	archive: 'Archived',
	delete: 'Deleted',
	import: 'Imported',
	enroll: 'Enrolled',
	unenroll: 'Removed',
	assign: 'Assigned',
	reassign: 'Reassigned',
	reopen: 'Reopened',
	unassign: 'Assignment ended',
	open: 'Opened',
	close: 'Closed',
	approve: 'Approved',
	reject: 'Rejected',
	revoke: 'Revoked',
	lock: 'Locked',
	unlock: 'Unlocked',
	login_failed: 'Sign-in failed',
	password_reset: 'Password reset',
};

/**
 * What colour a chip gets.
 *
 * `create` — something new. `update` — a change to something existing.
 * `remove` — it went away. `security` — the account itself.
 * `automation` — a bulk or unattended run.
 */
export type AuditTone = 'create' | 'update' | 'remove' | 'security' | 'automation';

export const AUDIT_ACTION_TONES: Record<AuditAction, AuditTone> = {
	create: 'create',
	update: 'update',
	archive: 'remove',
	delete: 'remove',
	import: 'automation',
	enroll: 'update',
	unenroll: 'remove',
	assign: 'update',
	reassign: 'update',
	reopen: 'update',
	unassign: 'remove',
	open: 'update',
	close: 'update',
	approve: 'update',
	reject: 'remove',
	revoke: 'remove',
	lock: 'security',
	unlock: 'security',
	login_failed: 'security',
	password_reset: 'security',
};

export const AUDIT_ENTITY_LABELS: Record<AuditEntityType, string> = {
	program: 'Program',
	year_level: 'Year level',
	course: 'Course',
	course_offering: 'Course offering',
	student: 'Student',
	professor: 'Professor',
	enrollment: 'Enrollment',
	course_professor: 'Teaching assignment',
	excuse: 'Excuse request',
	session: 'Class session',
	face_enrollment: 'Face template',
	attendance_record: 'Attendance record',
	backup: 'Backup',
	app_setting: 'System setting',
	user: 'User account',
	maintenance: 'Maintenance run',
};

// --- Field labels and value formatting --------------------------------------

/**
 * The human name of each snapshot field.
 *
 * Keyed by the field name the server's `_snapshot` methods use, so a new
 * snapshot field shows up under its own name until the map learns it — which
 * is visible, not silent.
 */
export const FIELD_LABELS: Record<string, string> = {
	// program
	code: 'Code',
	name: 'Name',
	description: 'Description',
	total_years: 'Years in the program',
	is_active: 'Status',
	program_code: 'Program',
	// year level
	program_id: 'Program',
	year_number: 'Year number',
	label: 'Label',
	term_structure: 'Terms',
	sort_order: 'Order',
	// course
	course_code: 'Course code',
	course_name: 'Course name',
	units: 'Units',
	session_duration_hours: 'Session length (hours)',
	// offering
	course_id: 'Course',
	year_level_id: 'Year level',
	semester: 'Term',
	academic_year: 'Academic year',
	sessions_per_week: 'Sessions per week',
	schedule_days: 'Meeting days',
	schedule_start_time: 'Starts',
	schedule_end_time: 'Ends',
	classroom_name: 'Classroom',
	classroom_lat: 'Latitude',
	classroom_lng: 'Longitude',
	default_present_window_minutes: 'Present window (min)',
	default_late_window_minutes: 'Late window (min)',
	// offering component
	offering_id: 'Offering',
	session_type: 'Session type',
	// student
	student_id: 'Student',
	first_name: 'First name',
	last_name: 'Last name',
	email: 'Email',
	section: 'Section',
	face_enrolled_at: 'Face enrolled at',
	// professor
	department: 'Department',
	// session
	professor_id: 'Professor',
	session_code: 'Session code',
	scheduled_start_time: 'Scheduled start',
	scheduled_end_time: 'Scheduled end',
	expires_at: 'Expires at',
	// account
	failed_login_attempts: 'Failed sign-in attempts',
	is_locked: 'Account locked',
	locked_at: 'Locked at',
	must_change_password: 'Must change password',
	role: 'Role',
	// assignment
	is_primary: 'Role',
	effective_from: 'Effective from',
	effective_to: 'Effective to',
	// excuse
	initiated_by: 'Initiated by',
	initiated_via: 'Submitted via',
	reason: 'Reason',
	attachment_count: 'Attachments',
	status: 'Status',
	reviewed_by: 'Reviewed by',
	review_notes: 'Review notes',
	// backup
	kind: 'Backup type',
	filename: 'File',
	size_bytes: 'File size',
	storage_backend: 'Storage',
	sha256: 'Checksum',
	// batches
	imported: 'Imported',
	duplicates: 'Skipped (already existed)',
	errors: 'Errors',
	enrolled: 'Enrolled',
	skipped: 'Skipped',
	processed: 'Processed',
	succeeded: 'Succeeded',
	failed: 'Failed',
	removed: 'Removed',
	otp_codes: 'Expired sign-in codes',
	sync_queue: 'Finished sync rows',
	// attendance review
	validation_status: 'Attendance status',
	review_note: 'Review note',
	// face template
	face_embedding_version: 'Face template version',
	// system settings
	present_window_default: 'Present window (min)',
	late_window_default: 'Late window (min)',
	geofence_default_radius: 'Geofence radius (m)',
	backup_retention_daily: 'Daily backups kept',
	backup_retention_monthly: 'Monthly backups kept',
};

/**
 * This system's meeting-day letters.
 *
 * `T` is Tuesday and `H` is Thursday — the conventional initials do not
 * apply (`backend/src/features/student/service.py:159-167`). Rendering
 * "MWF" as Mon/Wed/Fri by accident would put every meeting on the wrong day.
 */
export const DAY_INITIALS: Record<string, string> = {
	M: 'Mon',
	T: 'Tue',
	W: 'Wed',
	H: 'Thu',
	F: 'Fri',
	S: 'Sat',
	U: 'Sun',
};

export const titleCase = (value: string): string =>
	value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ');

export const timeOnly = (value: unknown): string => {
	if (typeof value !== 'string' || value.length === 0) return '—';
	const match = value.match(/^(\d{2}:\d{2})/);
	return match ? match[1] : value;
};

export const dateTimeText = (value: unknown): string => {
	if (typeof value !== 'string' || value.length === 0) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	const day = date.toLocaleDateString(undefined, {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
	});
	const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
	return `${day}, ${time}`;
};

export const dateText = (value: unknown): string => {
	if (typeof value !== 'string' || value.length === 0) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

export const termText = (value: unknown): string => {
	if (typeof value !== 'object' || value === null) return '—';
	const terms = (value as { terms?: unknown }).terms;
	if (!Array.isArray(terms)) return '—';
	const labels = terms
		.map((term) =>
			typeof term === 'object' && term !== null
				? String((term as { label?: unknown }).label ?? (term as { code?: unknown }).code ?? '')
				: String(term)
		)
		.filter((label) => label.length > 0);
	if (labels.length === 0) return 'No terms';
	return `${labels.length} term${labels.length === 1 ? '' : 's'}: ${labels.join(', ')}`;
};

export const daysText = (value: unknown): string => {
	if (typeof value !== 'string' || value.trim().length === 0) return '—';
	const letters = value
		.trim()
		.toUpperCase()
		.split('')
		.map((letter) => DAY_INITIALS[letter])
		.filter((day): day is string => !!day);
	return letters.length > 0 ? letters.join(', ') : value;
};

export const statusText = (value: unknown): string => {
	if (typeof value !== 'string') return '—';
	switch (value) {
		case 'present':
			return 'Present';
		case 'late':
			return 'Late';
		case 'absent':
			return 'Absent';
		case 'excused':
			return 'Excused';
		case 'pending':
			return 'Pending';
		case 'rejected':
			return 'Rejected';
		case 'approved':
			return 'Approved';
		case 'active':
			return 'Active';
		case 'inactive':
			return 'Inactive';
		case 'completed':
			return 'Completed';
		case 'failed':
			return 'Failed';
		case 'started':
			return 'Started';
		default:
			return titleCase(value);
	}
};

export const roleText = (value: unknown): string => {
	if (typeof value !== 'string') return '—';
	switch (value) {
		case 'super_admin':
			return 'Super admin';
		case 'admin':
			return 'Admin';
		case 'professor':
			return 'Professor';
		case 'student':
			return 'Student';
		case 'system':
			return 'System';
		default:
			return titleCase(value);
	}
};

/**
 * Per-field value formatting, for the fields a raw value would not read.
 *
 * A formatter may take the label context, so an id field can resolve to a
 * name (`offering_id` → "CS101 · Data Structures") instead of staying an id.
 */
export type AuditValueFormatter = (
	value: unknown,
	ctx: AuditLabelContext
) => string;

export const FIELD_FORMATTERS: Record<string, AuditValueFormatter> = {
	is_active: (v) => (v === true ? 'Active' : v === false ? 'Archived' : '—'),
	is_locked: (v) => (v === true ? 'Locked' : v === false ? 'Not locked' : '—'),
	must_change_password: (v) =>
		v === true ? 'Yes — must change at next sign-in' : v === false ? 'No' : '—',
	enrolled: (v) =>
		typeof v === 'number' ? String(v) : v === true ? 'Yes' : v === false ? 'No' : '—',
	validation_status: statusText,
	status: statusText,
	role: roleText,
	reviewed_by: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const user = ctx.users.get(Number(v));
		return user ? user.name : `User #${String(v)}`;
	},
	initiated_by: (v) => (v === 'professor' ? 'Professor' : v === 'student' ? 'Student' : '—'),
	initiated_via: (v) =>
		v === 'quick_excuse'
			? 'Quick excuse'
			: v === 'prof_with_evidence'
				? 'With evidence'
				: v === 'request'
					? 'Request'
					: '—',
	session_type: (v) => (v === 'lecture' ? 'Lecture' : v === 'lab' ? 'Laboratory' : '—'),
	schedule_days: daysText,
	schedule_start_time: timeOnly,
	schedule_end_time: timeOnly,
	scheduled_start_time: dateTimeText,
	scheduled_end_time: dateTimeText,
	expires_at: dateTimeText,
	locked_at: dateTimeText,
	face_enrolled_at: dateTimeText,
	term_structure: termText,
	size_bytes: (v) => (typeof v === 'number' ? formatBytes(v) : '—'),
	sha256: (v) => (typeof v === 'string' && v.length > 16 ? `${v.slice(0, 16)}…` : String(v ?? '—')),
	kind: (v) => (v === 'full' ? 'Full database' : v === 'analytics' ? 'Analytics' : '—'),
	storage_backend: (v) => (v === 'local' ? 'Local' : v === 's3' ? 'S3' : '—'),
	total_years: (v) => (typeof v === 'number' ? `${v} years` : '—'),
	session_duration_hours: (v) =>
		typeof v === 'number' ? `${v} ${v === 1 ? 'hour' : 'hours'}` : '—',
	default_present_window_minutes: (v) =>
		typeof v === 'number' ? `${v} min` : '—',
	default_late_window_minutes: (v) => (typeof v === 'number' ? `${v} min` : '—'),
	present_window_default: (v) => (typeof v === 'number' ? `${v} min` : '—'),
	late_window_default: (v) => (typeof v === 'number' ? `${v} min` : '—'),
	geofence_default_radius: (v) => (typeof v === 'number' ? `${v} m` : '—'),
	is_primary: (v) => (v === true ? 'Primary' : v === false ? 'Assistant' : '—'),
	year_number: (v) => (typeof v === 'number' ? `Year ${v}` : '—'),
	attachment_count: (v) =>
		typeof v === 'number' ? `${v} attachment${v === 1 ? '' : 's'}` : '—',
	failed_login_attempts: (v) => (typeof v === 'number' ? String(v) : '—'),
	face_embedding_version: (v) => (typeof v === 'number' ? `v${v}` : '—'),
	// Id fields, resolved against the lookups when they are available.
	offering_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const offering = ctx.offerings.get(Number(v));
		return offering ? offeringTitle(offering) : `Offering #${String(v)}`;
	},
	professor_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const professor = ctx.professors.get(Number(v));
		return professor ? professor.name : `Professor #${String(v)}`;
	},
	course_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const course = ctx.courses.get(Number(v));
		return course ? `${course.code} · ${course.name}` : `Course #${String(v)}`;
	},
	program_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const program = ctx.programs.get(Number(v));
		return program ? `${program.code} · ${program.name}` : `Program #${String(v)}`;
	},
	year_level_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		const level = ctx.yearLevels.get(Number(v));
		return level ? level.label : `Year level #${String(v)}`;
	},
	student_id: (v, ctx) => {
		if (v === null || v === undefined) return '—';
		// A string here is the student NUMBER (the student and enrollment
		// snapshots); a number is a row id (the excuse snapshot).
		if (typeof v === 'string') return v;
		const student = ctx.students.get(Number(v));
		return student ? `${student.studentId} · ${student.name}` : `Student #${String(v)}`;
	},
	session_id: (v) => (v === null || v === undefined ? '—' : `Session #${String(v)}`),
};

// --- Value formatting -------------------------------------------------------

export const formatAuditValue = (
	field: string,
	value: unknown,
	ctx: AuditLabelContext = emptyLabelContext()
): string => {
	const formatter = FIELD_FORMATTERS[field];
	if (formatter) return formatter(value, ctx);
	if (value === null || value === undefined) return '—';
	if (typeof value === 'boolean') return value ? 'Yes' : 'No';
	if (typeof value === 'number') return String(value);
	if (typeof value === 'string') return value.length > 0 ? value : '—';
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
};

