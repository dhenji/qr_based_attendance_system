// features/admin/audit/service.ts
// Admin audit-log service.
//
// Rows come from two sources merged here, both in the api-contracts
// GET /admin/audit-logs shape ({ id, action, entity_type, entity_id,
// old_value, new_value, performed_by, performed_at }):
//
// - Trail rows straight from `adminAuditLogs`: every recorded action. This is
//   the audit trail proper.
// - Record-creation rows derived client-side from roster `created_at`
//   (students, professors, programs, courses) because the rosters expose no
//   updater or updated-at, so creations are the only rows derivable from them.
//
// `origin` tells the two apart, and the UI shows them as two different
// things: the trail is what was audited, the roster rows are what a record's
// creation date implies. They are not the same evidence, so they are not
// presented as one list.
//
// The trail rows are the stored contract row, unaltered (ADR-064): the actor
// is a `users.id`, the subject is `entity_type` + `entity_id`, and
// `old_value`/`new_value` are the raw JSON snapshots. Turning those into
// names and readable changes is the reader's job and lives in `present.ts`.
//
// The merged feed sorts by timestamp desc with one client-side pager (both
// sources are requested at full page size and sliced locally, so they share a
// single total).

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import { downloadCsv } from '$lib/features/admin/analytics/service';
import type {
	AuditAction,
	AuditEntityType,
	AuditLogFilters,
	AuditLogItemResponse,
	Program,
	StructureChangeResponse,
} from '$lib/shared/types';
import type { AdminCourse } from '$lib/shared/types';
import { listCourses } from '$lib/features/admin/courses/service';
import { listProfessors, listStudents } from '$lib/features/admin/service';
import { listPrograms } from '$lib/features/admin/programs/service';

export interface AuditLogRow extends AuditLogItemResponse {
	/**
	 * Where the row came from.
	 *
	 * `'trail'` — written by the server's `record_audit`; the audit trail.
	 * `'roster'`  — derived here from a roster's `created_at`; an inference,
	 *   not an audited event. The UI labels the two differently and never
	 *   counts them as one.
	 */
	origin: 'trail' | 'roster';
}

export interface AuditFeed {
	/**
	 * Every merged row the feed holds, newest first.
	 *
	 * The whole set is returned, not a page of it, so the reader can sort
	 * across everything it has loaded. Slicing happens in the view.
	 */
	all: AuditLogRow[];
	/** Rows available across the merged feed. */
	total: number;
	/** The server's own count for the filtered trail — the audited rows. */
	trailTotal: number;
	/** Derived roster rows included in this feed. */
	rosterCount: number;
	/** True when the derived rows hit the scan cap, so the count is partial. */
	rosterTruncated: boolean;
	/** The number of trail rows actually fetched (the page size cap). */
	trailLoaded: number;
}

export const AUDIT_ENTITY_TYPES: { id: AuditEntityType; label: string }[] = [
	{ id: 'program', label: 'Program' },
	{ id: 'year_level', label: 'Year level' },
	{ id: 'course', label: 'Course' },
	{ id: 'course_offering', label: 'Course offering' },
	{ id: 'student', label: 'Student' },
	{ id: 'professor', label: 'Professor' },
	{ id: 'enrollment', label: 'Enrollment' },
	{ id: 'course_professor', label: 'Assignment' },
	{ id: 'excuse', label: 'Excuse' },
	{ id: 'session', label: 'Session' },
	{ id: 'face_enrollment', label: 'Face enrollment' },
	{ id: 'attendance_record', label: 'Attendance record' },
	{ id: 'backup', label: 'Backup' },
	{ id: 'app_setting', label: 'Setting' },
	{ id: 'user', label: 'User' },
	{ id: 'maintenance', label: 'Maintenance' },
];

export const AUDIT_ACTIONS: { id: AuditAction; label: string }[] = [
	{ id: 'create', label: 'Create' },
	{ id: 'update', label: 'Update' },
	{ id: 'archive', label: 'Archive' },
	{ id: 'delete', label: 'Delete' },
	{ id: 'import', label: 'Import' },
	{ id: 'enroll', label: 'Enroll' },
	{ id: 'unenroll', label: 'Unenroll' },
	{ id: 'assign', label: 'Assign' },
	{ id: 'reassign', label: 'Reassign' },
	{ id: 'reopen', label: 'Reopen' },
	{ id: 'unassign', label: 'Unassign' },
	{ id: 'open', label: 'Open' },
	{ id: 'close', label: 'Close' },
	{ id: 'approve', label: 'Approve' },
	{ id: 'reject', label: 'Reject' },
	{ id: 'revoke', label: 'Revoke' },
	{ id: 'lock', label: 'Lock' },
	{ id: 'unlock', label: 'Unlock' },
	{ id: 'login_failed', label: 'Login failed' },
	{ id: 'password_reset', label: 'Password reset' },
];

const auditParams = (f: AuditLogFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.entity_type) params.entity_type = f.entity_type;
	if (f.action) params.action = f.action;
	// The backend types `performed_by` as `int | None`
	// (`backend/src/features/system/router.py:81`), so it is sent as a number.
	// A free-text value here is a 422, which is why the filter control is
	// id-valued rather than a search box.
	if (f.performed_by !== undefined && f.performed_by !== null) {
		params.performed_by = String(f.performed_by);
	}
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	params.page = '1';
	params.size = '100';
	return params;
};

// Live-derivable rows: record creations from roster lists. Negative ids keep
// them distinct from backend ids. All are `create` actions with no actor
// (`performed_by` is null — nobody was recorded as making them), so an
// action/entity filter that excludes creates yields no live rows.
//
// The scan is bounded multi-page: a single roster page (100) hides every
// creation beyond it; three pages (~300 rows per entity) keep the live feed
// representative without hammering the roster endpoints on every audit load.
const MAX_ROSTER_PAGES = 3;
const MAX_LIVE_ROWS = 300;

interface RosterScan {
	rows: AuditLogRow[];
	truncated: boolean;
}

const listPages = async <T>(
	fetchPage: (page: number) => Promise<T[]>,
	pageSize: number
): Promise<T[]> => {
	const out: T[] = [];
	for (let pageNumber = 1; pageNumber <= MAX_ROSTER_PAGES; pageNumber += 1) {
		const items = await fetchPage(pageNumber);
		if (items.length === 0) break;
		out.push(...items);
		if (out.length >= MAX_LIVE_ROWS || items.length < pageSize) break;
	}
	return out;
};

const liveCreationRows = async (f: AuditLogFilters): Promise<RosterScan> => {
	if (f.action && f.action !== 'create') return { rows: [], truncated: false };
	// The derived rows carry no actor, so an actor filter cannot match them.
	if (f.performed_by !== undefined && f.performed_by !== null) {
		return { rows: [], truncated: false };
	}
	const rows: AuditLogRow[] = [];
	let cursor = -1;
	let truncated = false;
	const inRange = (iso: string): boolean => {
		const day = iso.slice(0, 10);
		if (f.date_from && day < f.date_from) return false;
		if (f.date_to && day > f.date_to) return false;
		return true;
	};
	const wants = (entity: AuditEntityType): boolean =>
		!f.entity_type || f.entity_type === entity;
	try {
		if (wants('student')) {
			const students = await listPages(
				(page) => listStudents({ page, size: 100 }).then((res) => res.items),
				100
			);
			for (const s of students) {
				if (!inRange(s.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'student',
					entity_id: s.id,
					old_value: null,
					// The same field names the server's own snapshot uses, so
					// the reader renders a derived row and a real one the
					// same way.
					new_value: {
						student_id: s.studentId,
						first_name: s.firstName,
						last_name: s.lastName,
						program_code: s.programCode,
					},
					performed_by: null,
					performed_at: s.createdAt,
					origin: 'roster',
				});
			}
		}
	} catch {
		// Roster unreachable — trail rows still render below.
	}
	try {
		if (wants('professor')) {
			const professors = await listPages(
				(page) => listProfessors({ page, size: 100 }).then((res) => res.items),
				100
			);
			for (const p of professors) {
				if (!inRange(p.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'professor',
					entity_id: p.id,
					old_value: null,
					new_value: {
						first_name: p.firstName,
						last_name: p.lastName,
						email: p.email,
					},
					performed_by: null,
					performed_at: p.createdAt,
					origin: 'roster',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	try {
		if (wants('program')) {
			const programs: Program[] = await listPages(
				(page) => listPrograms({ page, size: 50 }).then((res) => res.items),
				50
			);
			for (const p of programs) {
				if (!inRange(p.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'program',
					entity_id: p.id,
					old_value: null,
					new_value: { code: p.code, name: p.name },
					performed_by: null,
					performed_at: p.createdAt,
					origin: 'roster',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	try {
		if (wants('course')) {
			const courses: AdminCourse[] = await listPages(
				(page) => listCourses({ page, size: 100 }).then((res) => res.items),
				100
			);
			for (const c of courses) {
				if (!inRange(c.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'course',
					entity_id: c.id,
					old_value: null,
					new_value: { course_code: c.courseCode, course_name: c.courseName },
					performed_by: null,
					performed_at: c.createdAt,
					origin: 'roster',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	if (rows.length >= MAX_LIVE_ROWS) truncated = true;
	return { rows, truncated };
};

export const listAuditLogs = async (
	filters: AuditLogFilters = {}
): Promise<AuditFeed> => {
	const [trail, live] = await Promise.all([
		get<Paginated<AuditLogItemResponse>>('adminAuditLogs', auditParams(filters)),
		liveCreationRows(filters),
	]);
	const trailRows: AuditLogRow[] = (trail.items ?? []).map((r) => ({
		...r,
		origin: 'trail' as const,
	}));
	// The backend trail is authoritative: when it already carries a create
	// row for an entity, the derived live row for the same entity is a
	// duplicate of it, not a second event feeding the feed.
	const seen = new Set(trailRows.map((r) => `${r.action}:${r.entity_type}:${r.entity_id}`));
	const merged: AuditLogRow[] = [
		...trailRows,
		...live.rows.filter((r) => !seen.has(`${r.action}:${r.entity_type}:${r.entity_id}`)),
	];
	merged.sort((a, b) => (a.performed_at < b.performed_at ? 1 : -1));
	return {
		all: merged,
		total: merged.length,
		// The server's own count for the filtered trail. It is kept separate
		// from `total` because the two are not the same set of events.
		trailTotal: trail.total ?? trailRows.length,
		rosterCount: live.rows.length,
		rosterTruncated: live.truncated,
		trailLoaded: trailRows.length,
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
