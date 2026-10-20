// features/admin/audit/service.ts
// Admin audit-log service.
//
// The trail is ONE source: the rows the server recorded. There is nothing
// merged in here and nothing inferred.
//
// That used to be otherwise. The client used to fabricate "record
// creation" rows from each roster's `created_at`, because the server
// recorded no `create` row for a student or a professor. An inferred row is
// not evidence, it could not be filtered or paged with the real ones, and
// it needed four roster fetches on every page load. The server now writes
// those rows, so the client does not (ADR-086).
//
// The rows themselves are read, not interpreted: the endpoint returns the
// stored row AND its derived reading (who acted, what the subject is
// called, a summary, the field-level change). The vocabulary that produces
// that reading lives server-side, in `features/system/audit_labels.py`, so
// every client reads the trail the same way.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import { downloadCsv } from '$lib/features/admin/analytics/service';
import type {
	AuditAction,
	AuditEntityType,
	AuditLogFilters,
	AuditLogItemResponse,
	StructureChangeResponse,
} from '$lib/shared/types';

export interface AuditLogRow extends AuditLogItemResponse {}

export interface AuditFeed {
	items: AuditLogRow[];
	total: number;
	page: number;
	size: number;
}

export const AUDIT_ENTITY_TYPES: { id: AuditEntityType; label: string }[] = [
	{ id: 'program', label: 'Program' },
	{ id: 'year_level', label: 'Year level' },
	{ id: 'course', label: 'Course' },
	{ id: 'course_offering', label: 'Course offering' },
	{ id: 'offering_component', label: 'Schedule component' },
	{ id: 'student', label: 'Student' },
	{ id: 'professor', label: 'Professor' },
	{ id: 'enrollment', label: 'Enrollment' },
	{ id: 'course_professor', label: 'Teaching assignment' },
	{ id: 'excuse', label: 'Excuse request' },
	{ id: 'session', label: 'Class session' },
	{ id: 'face_enrollment', label: 'Face template' },
	{ id: 'attendance_record', label: 'Attendance record' },
	{ id: 'backup', label: 'Backup' },
	{ id: 'app_setting', label: 'System setting' },
	{ id: 'user', label: 'User account' },
	{ id: 'maintenance', label: 'Maintenance run' },
];

export const AUDIT_ACTIONS: { id: AuditAction; label: string }[] = [
	{ id: 'create', label: 'Create' },
	{ id: 'update', label: 'Update' },
	{ id: 'archive', label: 'Archive' },
	{ id: 'delete', label: 'Delete' },
	{ id: 'import', label: 'Import' },
	{ id: 'enroll', label: 'Enroll' },
	{ id: 'unenroll', label: 'Remove from offering' },
	{ id: 'assign', label: 'Assign' },
	{ id: 'reassign', label: 'Reassign' },
	{ id: 'reopen', label: 'Reopen' },
	{ id: 'unassign', label: 'End assignment' },
	{ id: 'open', label: 'Open' },
	{ id: 'close', label: 'Close' },
	{ id: 'approve', label: 'Approve' },
	{ id: 'reject', label: 'Reject' },
	{ id: 'revoke', label: 'Revoke' },
	{ id: 'lock', label: 'Lock' },
	{ id: 'unlock', label: 'Unlock' },
	{ id: 'login_failed', label: 'Sign-in failed' },
	{ id: 'password_reset', label: 'Password reset' },
];

const auditParams = (f: AuditLogFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.entity_type) params.entity_type = f.entity_type;
	if (f.action) params.action = f.action;
	// `performed_by` is an exact account id; `actor` is a fragment matched
	// against the id, the email and the name. Both are server-side.
	if (f.performed_by !== undefined && f.performed_by !== null) {
		params.performed_by = String(f.performed_by);
	}
	if (f.actor) params.actor = f.actor;
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	if (f.sort_by) params.sort_by = f.sort_by;
	if (f.sort_dir) params.sort_dir = f.sort_dir;
	params.page = String(f.page ?? 1);
	params.size = String(f.size ?? 20);
	return params;
};

export const listAuditLogs = async (
	filters: AuditLogFilters = {}
): Promise<AuditFeed> => {
	const response = await get<Paginated<AuditLogItemResponse>>(
		'adminAuditLogs',
		auditParams(filters)
	);
	return {
		items: response.items ?? [],
		total: response.total ?? 0,
		page: response.page ?? (filters.page ?? 1),
		size: response.size ?? (filters.size ?? 20),
	};
};

export const listStructureChanges = async (
	filters: { page?: number; size?: number } = {}
): Promise<Paginated<StructureChangeResponse>> => {
	const params: Record<string, string> = {
		page: String(filters.page ?? 1),
		size: String(filters.size ?? 20),
	};
	const response = await get<Paginated<StructureChangeResponse>>(
		'adminStructureChanges',
		params
	);
	return {
		items: response.items ?? [],
		total: response.total ?? 0,
		page: response.page ?? (filters.page ?? 1),
		size: response.size ?? (filters.size ?? 20),
	};
};

export { downloadCsv };
