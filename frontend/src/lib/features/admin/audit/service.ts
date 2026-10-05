// features/admin/audit/service.ts
// Admin audit-log service.
//
// Rows come from two sources merged here, both in the api-contracts
// GET /admin/audit-logs shape ({ id, action, entity_type, entity_id,
// old_value, new_value, performed_by, performed_at }):
//
// - Trail rows straight from `adminAuditLogs`: every recorded action.
// - Record-creation rows derived client-side from roster `created_at`
//   (students, professors, programs, courses) because the rosters expose no
//   updater or updated-at, so creations are the only rows derivable from them.
//
// `origin` labels the two sources and is rendered in the feed and the CSV
// export. The label `'seed'` on the trail rows is a legacy name from when they
// really were deterministic fixtures — they are live contract rows now, and
// the endpoint def's `mock` is only consulted under PUBLIC_MOCK_MODE=true.
// Renaming it would touch the store, the page and the CSV header, so it is
// left as-is rather than half-migrated.
//
// The merged feed sorts by timestamp desc with one client-side pager (both
// sources are requested at full page size and sliced locally, so they share a
// single total).

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import { buildCsv } from '$lib/features/report/service';
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
	origin: 'system' | 'seed';
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
	{ id: 'assign', label: 'Assign' },
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

/** Backwards-compatible alias: the audit page's entity dropdown reads this. */
export const AUDIT_CATEGORIES = AUDIT_ENTITY_TYPES;

const auditParams = (f: AuditLogFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.entity_type) params.entity_type = f.entity_type;
	if (f.action) params.action = f.action;
	if (f.performed_by) params.performed_by = f.performed_by;
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	params.page = '1';
	params.size = '100';
	return params;
};

// Live-derivable rows: record creations from roster lists. Negative ids keep
// them distinct from backend ids. All are `create` actions by `system`, so an
// action/entity filter that excludes creates yields no live rows.
const liveCreationRows = async (f: AuditLogFilters): Promise<AuditLogRow[]> => {
	if (f.action && f.action !== 'create') return [];
	if (f.performed_by && !'system'.includes(f.performed_by.trim().toLowerCase())) return [];
	const rows: AuditLogRow[] = [];
	let cursor = -1;
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
			const students = (await listStudents({ page: 1, size: 100 })).items;
			for (const s of students) {
				if (!inRange(s.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'student',
					entity_id: s.id,
					old_value: null,
					new_value: `${s.firstName} ${s.lastName} · ${s.studentId} · ${s.programCode}`,
					performed_by: 'system',
					performed_at: s.createdAt,
					origin: 'system',
				});
			}
		}
	} catch {
		// Roster unreachable — trail rows still render below.
	}
	try {
		if (wants('professor')) {
			const professors = (await listProfessors({ page: 1, size: 100 })).items;
			for (const p of professors) {
				if (!inRange(p.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'professor',
					entity_id: p.id,
					old_value: null,
					new_value: `${p.firstName} ${p.lastName} · ${p.email}`,
					performed_by: 'system',
					performed_at: p.createdAt,
					origin: 'system',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	try {
		if (wants('program')) {
			const programs: Program[] = (await listPrograms({ page: 1, size: 50 })).items;
			for (const p of programs) {
				if (!inRange(p.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'program',
					entity_id: p.id,
					old_value: null,
					new_value: `${p.code} · ${p.name}`,
					performed_by: 'system',
					performed_at: p.createdAt,
					origin: 'system',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	try {
		if (wants('course')) {
			const courses: AdminCourse[] = (await listCourses({ page: 1, size: 100 })).items;
			for (const c of courses) {
				if (!inRange(c.createdAt)) continue;
				rows.push({
					id: cursor--,
					action: 'create',
					entity_type: 'course',
					entity_id: c.id,
					old_value: null,
					new_value: `${c.courseCode} · ${c.courseName}`,
					performed_by: 'system',
					performed_at: c.createdAt,
					origin: 'system',
				});
			}
		}
	} catch {
		// Same fallback as above.
	}
	return rows;
};

export const listAuditLogs = async (
	filters: AuditLogFilters = {},
	page = 1,
	size = 20
): Promise<{ items: AuditLogRow[]; total: number; page: number; size: number }> => {
	const [trail, live] = await Promise.all([
		get<Paginated<AuditLogItemResponse>>('adminAuditLogs', auditParams(filters)),
		liveCreationRows(filters),
	]);
	const merged: AuditLogRow[] = [
		...(trail.items ?? []).map((r) => ({ ...r, origin: 'seed' as const })),
		...live,
	];
	merged.sort((a, b) => (a.performed_at < b.performed_at ? 1 : -1));
	const total = merged.length;
	const totalPages = Math.max(1, Math.ceil(total / size));
	const safePage = Math.min(Math.max(page, 1), totalPages);
	return {
		items: merged.slice((safePage - 1) * size, safePage * size),
		total,
		page: safePage,
		size,
	};
};

export const listStructureChanges = async (): Promise<StructureChangeResponse[]> => {
	const response = await get<{ items: StructureChangeResponse[] }>('adminStructureChanges');
	return response.items ?? [];
};

const valueText = (value: unknown): string => {
	if (value === null || value === undefined) return '';
	if (typeof value === 'string') return value;
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
};

export const auditCsv = (rows: AuditLogRow[]): string =>
	buildCsv(
		['performed_at', 'performed_by', 'action', 'entity_type', 'entity_id', 'old_value', 'new_value', 'origin'],
		rows.map((r) => [
			r.performed_at,
			r.performed_by === null || r.performed_by === undefined ? '' : String(r.performed_by),
			r.action,
			r.entity_type,
			r.entity_id ?? '',
			valueText(r.old_value),
			valueText(r.new_value),
			r.origin,
		])
	);

export { downloadCsv };
