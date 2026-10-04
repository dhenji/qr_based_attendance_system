// features/admin/audit/service.ts
// Admin audit-log service.
//
// The audit backend is live (Phase 8, `GET /admin/audit-logs` on
// features/system/router.py, fed by shared/audit.py::record_audit), so rows come
// from two live sources merged here:
//
// - Trail rows straight from `adminAuditLogs`: every recorded action, with its
//   real actor, action, entity and detail.
// - Record-creation rows derived client-side from roster `created_at`
//   (students, professors, programs, courses) because the rosters expose no
//   updater or updated-at, so creations are the only rows derivable from them.
//
// `origin` labels the two sources and is rendered in the feed and the CSV
// export. The label `'seed'` on the trail rows is a legacy name from when they
// really were deterministic fixtures — they are not seeded now, and the
// endpoint def's `mock` is only consulted under PUBLIC_MOCK_MODE=true. Renaming
// it would touch the store, the page and the CSV header, so it is left as-is
// rather than half-migrated.
//
// The merged feed sorts by timestamp desc with one client-side pager (both
// sources are requested at full page size and sliced locally, so they share a
// single total). Category values are the ten logged families from
// security-model §Audit-Log-Coverage.

import { get } from '$lib/api/client';
import type { Paginated } from '$lib/api/endpoints';
import { buildCsv } from '$lib/features/report/service';
import { downloadCsv } from '$lib/features/admin/analytics/service';
import type {
	AdminCourse,
	AuditCategory,
	AuditLogFilters,
	AuditLogItemResponse,
	Program,
	StructureChangeResponse,
} from '$lib/shared/types';
import { listCourses } from '$lib/features/admin/courses/service';
import { listProfessors, listStudents } from '$lib/features/admin/service';
import { listPrograms } from '$lib/features/admin/programs/service';

export interface AuditLogRow extends AuditLogItemResponse {
	origin: 'system' | 'seed';
}

export const AUDIT_CATEGORIES: { id: AuditCategory; label: string }[] = [
	{ id: 'enrollment', label: 'Enrollment' },
	{ id: 'assignment', label: 'Assignment' },
	{ id: 'excuse', label: 'Excuse' },
	{ id: 'session', label: 'Session' },
	{ id: 'face_enrollment', label: 'Face enrollment' },
	{ id: 'backup', label: 'Backup' },
	{ id: 'structure', label: 'Structure' },
	{ id: 'settings', label: 'Settings' },
	{ id: 'lockout', label: 'Lockout' },
	{ id: 'login', label: 'Login' },
];

const auditParams = (f: AuditLogFilters): Record<string, string> => {
	const params: Record<string, string> = {};
	if (f.date_from) params.date_from = f.date_from;
	if (f.date_to) params.date_to = f.date_to;
	if (f.category) params.category = f.category;
	if (f.search) params.search = f.search;
	params.page = '1';
	params.size = '100';
	return params;
};

// Live-derivable rows: record creations from roster lists. Negative ids keep
// them distinct from backend ids when the real trail lands.
const liveCreationRows = async (f: AuditLogFilters): Promise<AuditLogRow[]> => {
	const rows: AuditLogRow[] = [];
	let cursor = -1;
	const inRange = (iso: string): boolean => {
		const day = iso.slice(0, 10);
		if (f.date_from && day < f.date_from) return false;
		if (f.date_to && day > f.date_to) return false;
		return true;
	};
	try {
		const students = (await listStudents({ page: 1, size: 100 })).items;
		for (const s of students) {
			if (!inRange(s.createdAt)) continue;
			rows.push({
				id: cursor--,
				occurred_at: s.createdAt,
				actor_name: 'System',
				actor_role: 'system',
				action: `Student record created ${s.studentId}`,
				category: 'enrollment',
				entity: `students:${s.id}`,
				detail: `${s.firstName} ${s.lastName} · ${s.programCode}`,
				origin: 'system',
			});
		}
	} catch {
		// Roster unreachable — operational rows still render below.
	}
	try {
		const professors = (await listProfessors({ page: 1, size: 100 })).items;
		for (const p of professors) {
			if (!inRange(p.createdAt)) continue;
			rows.push({
				id: cursor--,
				occurred_at: p.createdAt,
				actor_name: 'System',
				actor_role: 'system',
				action: `Professor roster record created`,
				category: 'enrollment',
				entity: `professors:${p.id}`,
				detail: `${p.firstName} ${p.lastName} · ${p.email}`,
				origin: 'system',
			});
		}
	} catch {
		// Same fallback as above.
	}
	try {
		const programs: Program[] = (await listPrograms({ page: 1, size: 50 })).items;
		for (const p of programs) {
			if (!inRange(p.createdAt)) continue;
			rows.push({
				id: cursor--,
				occurred_at: p.createdAt,
				actor_name: 'System',
				actor_role: 'system',
				action: `Program created ${p.code}`,
				category: 'structure',
				entity: `programs:${p.id}`,
				detail: p.name,
				origin: 'system',
			});
		}
	} catch {
		// Same fallback as above.
	}
	try {
		const courses: AdminCourse[] = (await listCourses({ page: 1, size: 100 })).items;
		for (const c of courses) {
			if (!inRange(c.createdAt)) continue;
			rows.push({
				id: cursor--,
				occurred_at: c.createdAt,
				actor_name: 'System',
				actor_role: 'system',
				action: `Course created ${c.courseCode}`,
				category: 'structure',
				entity: `courses:${c.id}`,
				detail: c.courseName,
				origin: 'system',
			});
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
	const [seed, live] = await Promise.all([
		get<Paginated<AuditLogItemResponse>>('adminAuditLogs', auditParams(filters)),
		liveCreationRows(filters),
	]);
	const merged: AuditLogRow[] = [
		...(seed.items ?? []).map((r) => ({ ...r, origin: 'seed' as const })),
		...live,
	];
	merged.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
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

export const auditCsv = (rows: AuditLogRow[]): string =>
	buildCsv(
		['occurred_at', 'actor_name', 'actor_role', 'action', 'category', 'entity', 'detail', 'origin'],
		rows.map((r) => [
			r.occurred_at,
			r.actor_name,
			r.actor_role,
			r.action,
			r.category,
			r.entity,
			r.detail ?? '',
			r.origin,
		])
	);

export { downloadCsv };
