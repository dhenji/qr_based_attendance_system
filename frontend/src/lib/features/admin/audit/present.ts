// features/admin/audit/present.ts
// The read side of the audit trail: raw row in, readable row out.
//
// The endpoint returns the stored row unaltered (ADR-064) — a `users.id` for
// the actor, `entity_type` + `entity_id` for the subject, and the JSON
// snapshots for the change. An administrator cannot read that, so this module
// derives what they need:
//
//   - WHO   → a name and a role, not an id.
//   - WHAT  → a verb, not a snake_case token.
//   - WHICH → a record name, not `course_offering #12`.
//   - HOW   → a field-level diff, not a JSON blob.
//
// Every function here is pure: no I/O, no runes, no globals. The lookups it
// needs arrive as an `AuditLabelContext` (see `labels.ts`).
//
// Two rules the rest of the codebase already knows and this module follows:
//   - `schedule_days` letters are this system's, not the conventional ones:
//     M=Monday T=Tuesday W=Wednesday H=Thursday F=Friday S=Saturday U=Sunday
//     (`backend/src/features/student/service.py:159-167`). T is Tuesday
//     because "T" was already taken by Thursday in the source system.
//   - A snapshot is the surviving record of a row that no longer exists, so
//     it is read BEFORE any lookup.

import type { AuditAction, AuditEntityType } from '$lib/shared/types';
import {
	adminCourse,
	adminOffering,
	adminProgram,
	adminProfessor,
	adminStudent,
	Routes,
} from '$lib/shared/constants/routes';
import { formatBytes } from '$lib/shared/utils/format';
import { buildCsv } from '$lib/features/report/service';
import type { AuditLogRow } from '$lib/features/admin/audit/service';
import {
	emptyLabelContext,
	offeringTitle,
	type AuditLabelContext,
	type AuditOfferingRef,
} from '$lib/features/admin/audit/labels';
import {
	AUDIT_ACTION_LABELS,
	AUDIT_ACTION_TONES,
	AUDIT_ENTITY_LABELS,
	FIELD_LABELS,
	dateText,
	formatAuditValue,
	roleText,
	statusText,
	timeOnly,
	type AuditTone,
} from '$lib/features/admin/audit/present-fields';

export {
	AUDIT_ACTION_LABELS,
	AUDIT_ACTION_TONES,
	AUDIT_ENTITY_LABELS,
	FIELD_LABELS,
	formatAuditValue,
};
export type { AuditTone };

// --- The row view -----------------------------------------------------------

export interface AuditActorView {
	kind: 'user' | 'system' | 'anonymous';
	id: number | null;
	name: string;
	role: string | null;
	/** False when the name is the "User #<id>" fallback. */
	resolved: boolean;
}

export interface AuditEntityView {
	type: AuditEntityType;
	id: number | null;
	label: string;
	sublabel: string | null;
	href: string | null;
	/**
	 * True when the entity id alone is ambiguous.
	 *
	 * `course_offering` covers both an offering and one of its schedule
	 * components, and both write the offering's id
	 * (`backend/src/features/course/service.py:1754, 1824, 1849`), so the
	 * snapshot shape is the only thing that tells them apart.
	 */
	ambiguous: boolean;
}

export interface AuditChangeView {
	field: string;
	label: string;
	before: string;
	after: string;
}

export interface AuditRowView {
	id: number;
	occurredAt: string;
	origin: 'trail' | 'roster';
	actor: AuditActorView;
	action: { id: AuditAction; label: string; tone: AuditTone };
	entity: AuditEntityView;
	summary: string;
	changes: AuditChangeView[];
	raw: {
		old_value: Record<string, unknown> | null;
		new_value: Record<string, unknown> | null;
	};
}

const str = (value: unknown): string =>
	typeof value === 'string' && value.length > 0 ? value : '';
const num = (value: unknown): number | null => {
	const parsed = typeof value === 'number' ? value : Number(value);
	return Number.isFinite(parsed) ? parsed : null;
};

/** The snapshot that describes the record: the new state, or the old one. */
const snapshotOf = (row: AuditLogRow): Record<string, unknown> =>
	row.new_value ?? row.old_value ?? {};

// --- Actor ------------------------------------------------------------------

export const describeActor = (
	row: AuditLogRow,
	ctx: AuditLabelContext
): AuditActorView => {
	// A derived roster row was not made by anybody — the roster's
	// `created_at` is all we know.
	if (row.origin === 'roster') {
		return { kind: 'system', id: null, name: 'System', role: null, resolved: true };
	}
	// `performed_by` is null when nobody was authenticated: an anonymous
	// lockout, or an unattended run.
	if (row.performed_by === null || row.performed_by === undefined) {
		return {
			kind: 'anonymous',
			id: null,
			name: 'No signed-in user',
			role: null,
			resolved: true,
		};
	}
	const user = ctx.users.get(row.performed_by);
	if (user) {
		return {
			kind: 'user',
			id: row.performed_by,
			name: user.name,
			role: user.role,
			resolved: true,
		};
	}
	// Unresolvable: the users map needs the super-admin-only endpoint, and
	// the account snapshot deliberately carries no email. The id is demoted,
	// never hidden.
	return {
		kind: 'user',
		id: row.performed_by,
		name: `User #${row.performed_by}`,
		role: null,
		resolved: false,
	};
};

// --- Entity -----------------------------------------------------------------

const offeringLabel = (ref: AuditOfferingRef | undefined, fallbackId: unknown): string => {
	if (!ref) return `Offering #${String(fallbackId ?? '?')}`;
	return offeringTitle(ref);
};

export const describeEntity = (
	row: AuditLogRow,
	ctx: AuditLabelContext
): AuditEntityView => {
	const s = snapshotOf(row);
	const id = row.entity_id;
	const base = { type: row.entity_type, id, sublabel: null as string | null, href: null as string | null, ambiguous: false };

	switch (row.entity_type) {
		case 'program': {
			// A program import has no id — it describes a batch.
			if (id === null) {
				const imported = num(s.imported);
				return {
					...base,
					label: 'Program import',
					sublabel:
						imported === null
							? null
							: `${imported} imported · ${num(s.duplicates) ?? 0} already existed · ${num(s.errors) ?? 0} errors`,
				};
			}
			const code = str(s.code);
			const name = str(s.name);
			return {
				...base,
				label: code && name ? `${code} · ${name}` : code || name || `Program #${id}`,
				sublabel: str(s.description) || null,
				href: id === null ? null : adminProgram(id),
			};
		}
		case 'year_level': {
			const programId = num(s.program_id);
			const program = programId === null ? undefined : ctx.programs.get(programId);
			const label = str(s.label);
			return {
				...base,
				label: program ? `${program.code} · ${label}` : label || `Year level #${id}`,
				sublabel:
					program && label
						? program.name
						: programId === null
							? null
							: `Program #${programId}`,
				href: programId === null ? null : adminProgram(programId),
			};
		}
		case 'course': {
			if (id === null) {
				const imported = num(s.imported);
				return {
					...base,
					label: 'Course import',
					sublabel:
						imported === null
							? null
							: `${imported} imported · ${num(s.duplicates) ?? 0} already existed · ${num(s.errors) ?? 0} errors`,
				};
			}
			const code = str(s.course_code);
			const name = str(s.course_name);
			return {
				...base,
				label: code && name ? `${code} · ${name}` : code || name || `Course #${id}`,
				sublabel: s.units === undefined ? null : `${String(s.units)} units`,
				href: id === null ? null : adminCourse(id),
			};
		}
		case 'course_offering': {
			// An offering and one of its schedule components share this
			// entity type AND the offering's id, so the snapshot shape is
			// what tells them apart: a component carries `session_type` and
			// no `semester`; an offering carries `semester`.
			const isComponent = s.session_type !== undefined && s.semester === undefined;
			if (isComponent) {
				const offeringId = num(s.offering_id);
				const offering = offeringId === null ? undefined : ctx.offerings.get(offeringId);
				const kind = s.session_type === 'lab' ? 'Laboratory' : 'Lecture';
				return {
					...base,
					label: offering
						? `${offering.course} — ${kind} component`
						: `Schedule component of offering #${String(offeringId ?? id ?? '?')}`,
					sublabel: [
						formatAuditValue('schedule_days', s.schedule_days),
						`${timeOnly(s.schedule_start_time)}–${timeOnly(s.schedule_end_time)}`,
						str(s.classroom_name),
					]
						.filter((part) => part.length > 0 && part !== '—')
						.join(' · '),
					href: id === null ? null : adminOffering(id),
					ambiguous: true,
				};
			}
			const courseId = num(s.course_id);
			const programId = num(s.program_id);
			const yearLevelId = num(s.year_level_id);
			const course = courseId === null ? undefined : ctx.courses.get(courseId);
			const program = programId === null ? undefined : ctx.programs.get(programId);
			const yearLevel = yearLevelId === null ? undefined : ctx.yearLevels.get(yearLevelId);
			const head = course ? `${course.code} · ${course.name}` : `Course #${String(courseId ?? '?')}`;
			const tail = [
				program ? program.code : programId === null ? null : `Program #${programId}`,
				yearLevel ? yearLevel.label : yearLevelId === null ? null : `Year level #${yearLevelId}`,
				str(s.semester) ? `${s.semester} Sem` : null,
				str(s.academic_year),
			]
				.filter((part): part is string => !!part)
				.join(' · ');
			return {
				...base,
				label: head,
				sublabel: tail.length > 0 ? tail : null,
				href: id === null ? null : adminOffering(id),
			};
		}
		case 'student': {
			if (id === null) {
				const imported = num(s.imported);
				return {
					...base,
					label: 'Student import',
					sublabel:
						imported === null
							? null
							: `${imported} imported · ${num(s.duplicates) ?? 0} already existed · ${num(s.errors) ?? 0} errors`,
				};
			}
			const number = str(s.student_id);
			const name = [str(s.first_name), str(s.last_name)].filter(Boolean).join(' ');
			return {
				...base,
				label: number && name ? `${number} · ${name}` : number || name || `Student #${id}`,
				sublabel: str(s.email) || str(s.program_code) || null,
				href: id === null ? null : adminStudent(id),
			};
		}
		case 'professor': {
			if (id === null) {
				const imported = num(s.imported);
				return {
					...base,
					label: 'Professor import',
					sublabel:
						imported === null
							? null
							: `${imported} imported · ${num(s.duplicates) ?? 0} already existed · ${num(s.errors) ?? 0} errors`,
				};
			}
			const name = [str(s.first_name), str(s.last_name)].filter(Boolean).join(' ');
			return {
				...base,
				label: name || `Professor #${id}`,
				sublabel: str(s.email) || str(s.department) || null,
				href: id === null ? null : adminProfessor(id),
			};
		}
		case 'enrollment': {
			const offeringId = num(s.offering_id);
			const offering = offeringId === null ? undefined : ctx.offerings.get(offeringId);
			// A bulk enroll has no id — it describes a batch of students.
			if (id === null) {
				return {
					...base,
					label: offering ? `Enrolled students in ${offering.course}` : 'Bulk enrollment',
					sublabel: offering
						? offeringTitle(offering)
						: `${num(s.enrolled) ?? 0} enrolled · ${num(s.skipped) ?? 0} skipped`,
				};
			}
			// A single removal names the student by number.
			const number = str(s.student_id);
			return {
				...base,
				label: number
					? `${number} in ${offering?.course ?? `offering #${String(offeringId ?? '?')}`}`
					: `Enrollment #${id}`,
				sublabel: offering ? offeringTitle(offering) : null,
			};
		}
		case 'course_professor': {
			const offeringId = num(s.offering_id);
			const professorId = num(s.professor_id);
			const offering = offeringId === null ? undefined : ctx.offerings.get(offeringId);
			const professor = professorId === null ? undefined : ctx.professors.get(professorId);
			const role = s.is_primary === true ? 'Primary' : 'Assistant';
			const from = str(s.effective_from);
			const to = str(s.effective_to);
			return {
				...base,
				label: `${professor?.name ?? `Professor #${String(professorId ?? '?')}`} → ${
					offering?.course ?? `offering #${String(offeringId ?? '?')}`
				}`,
				sublabel: [
					role,
					from ? `from ${dateText(from)}` : null,
					to ? `to ${dateText(to)}` : null,
				]
					.filter((part): part is string => !!part)
					.join(' · '),
			};
		}
		case 'excuse': {
			const studentId = num(s.student_id);
			const student = studentId === null ? undefined : ctx.students.get(studentId);
			return {
				...base,
				label: student
					? `${student.name} (${student.studentId})`
					: `Excuse request #${id ?? '?'}`,
				sublabel: str(s.reason) || null,
			};
		}
		case 'session': {
			const offeringId = num(s.offering_id);
			const offering = offeringId === null ? undefined : ctx.offerings.get(offeringId);
			const code = str(s.session_code);
			return {
				...base,
				label: code || `Session #${id ?? '?'}`,
				sublabel: offering
					? offeringTitle(offering)
					: s.session_type === 'lab'
						? 'Laboratory'
						: s.session_type === 'lecture'
							? 'Lecture'
							: null,
			};
		}
		case 'face_enrollment': {
			// The id here is a STUDENT id, not a face-template id.
			const student = id === null ? undefined : ctx.students.get(id);
			return {
				...base,
				label: student
					? `Face template — ${student.name}`
					: `Face template #${id ?? '?'}`,
				sublabel: student ? student.studentId : null,
			};
		}
		case 'attendance_record': {
			return {
				...base,
				label: `Attendance record #${id ?? '?'}`,
				sublabel: s.validation_status === undefined ? null : statusText(s.validation_status),
			};
		}
		case 'backup': {
			const filename = str(s.filename);
			return {
				...base,
				label: filename || `Backup #${id ?? '?'}`,
				sublabel: [
					s.kind === 'full' ? 'Full database' : s.kind === 'analytics' ? 'Analytics' : null,
					s.size_bytes === undefined ? null : formatBytes(Number(s.size_bytes)),
					s.status === undefined ? null : statusText(s.status),
				]
					.filter((part): part is string => !!part)
					.join(' · '),
				href: Routes.ADMIN_SYSTEM_SETTINGS,
			};
		}
		case 'app_setting': {
			const names = Object.keys(s);
			return {
				...base,
				label: 'System settings',
				sublabel:
					names.length > 0
						? names.map((name) => FIELD_LABELS[name] ?? name).join(', ')
						: null,
			};
		}
		case 'user': {
			const email = str(s.email);
			return {
				...base,
				label: email || `User #${id ?? '?'}`,
				sublabel: s.role === undefined ? null : roleText(s.role),
				href: Routes.ADMIN_USERS,
			};
		}
		case 'maintenance': {
			const isSync = s.processed !== undefined;
			const isCleanup = s.removed !== undefined;
			return {
				...base,
				label: isSync
					? 'Offline sync reconciliation'
					: isCleanup
						? 'Expired-data cleanup'
						: 'Maintenance run',
				sublabel: Object.entries(s)
					.map(
						([key, value]) =>
							`${FIELD_LABELS[key] ?? key}: ${formatAuditValue(key, value, ctx)}`
					)
					.join(' · '),
			};
		}
	}
};

// --- Changes ----------------------------------------------------------------

const deepEqual = (a: unknown, b: unknown): boolean => {
	if (a === b) return true;
	if (a === null || b === null || a === undefined || b === undefined) return false;
	if (typeof a !== 'object' || typeof b !== 'object') return false;
	return JSON.stringify(a) === JSON.stringify(b);
};

/**
 * The field-level difference between two snapshots.
 *
 * A create has no `old_value` and a delete has no `new_value`; both are
 * reported as one-sided changes rather than as a diff against nothing, so
 * the "before" or "after" column reads as a dash instead of an empty cell.
 */
export const diffSnapshots = (
	oldValue: Record<string, unknown> | null,
	newValue: Record<string, unknown> | null,
	ctx: AuditLabelContext = emptyLabelContext()
): AuditChangeView[] => {
	const before = oldValue ?? {};
	const after = newValue ?? {};
	const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
	const changes: AuditChangeView[] = [];
	for (const key of keys) {
		const from = before[key];
		const to = after[key];
		if (oldValue !== null && newValue !== null && deepEqual(from, to)) continue;
		// On a create there is no "before" and on a delete there is no
		// "after", so a field that was never set reads as "— → —" and says
		// nothing. It is left out.
		if (oldValue === null && (to === null || to === undefined)) continue;
		if (newValue === null && (from === null || from === undefined)) continue;
		changes.push({
			field: key,
			label: FIELD_LABELS[key] ?? key.replace(/_/g, ' '),
			before: oldValue === null ? '—' : formatAuditValue(key, from, ctx),
			after: newValue === null ? '—' : formatAuditValue(key, to, ctx),
		});
	}
	return changes;
};

// --- The row ----------------------------------------------------------------

const summaryFor = (
	action: AuditAction,
	entity: AuditEntityView,
	changes: AuditChangeView[]
): string => {
	const label = AUDIT_ACTION_LABELS[action];
	switch (action) {
		case 'enroll':
			return entity.label.startsWith('Enrolled') ? entity.label : `Enrolled students in ${entity.label}`;
		case 'unenroll':
			return `Removed ${entity.label}`;
		case 'assign':
		case 'reassign':
			return `${label} ${entity.label}`;
		case 'import':
			return entity.label;
		case 'unassign':
			return `Ended ${entity.label}`;
		default: {
			// A one-field change reads better with the field named.
			if (changes.length === 1) {
				return `${label} ${entity.label} — ${changes[0].label}`;
			}
			return `${label} ${entity.label}`;
		}
	}
};

export const buildRowView = (row: AuditLogRow, ctx: AuditLabelContext): AuditRowView => {
	const actor = describeActor(row, ctx);
	const entity = describeEntity(row, ctx);
	const changes = diffSnapshots(row.old_value, row.new_value, ctx);
	const action = {
		id: row.action,
		label: AUDIT_ACTION_LABELS[row.action] ?? row.action.replace(/_/g, ' '),
		tone: AUDIT_ACTION_TONES[row.action] ?? 'update',
	};
	return {
		id: row.id,
		occurredAt: row.performed_at,
		origin: row.origin,
		actor,
		action,
		entity,
		summary: summaryFor(row.action, entity, changes),
		changes,
		raw: { old_value: row.old_value, new_value: row.new_value },
	};
};

// --- Export -----------------------------------------------------------------

/**
 * The readable export.
 *
 * It exports the VIEW model, not the stored row: names, verbs and a
 * field-level diff, so the file answers the same question the screen does
 * without the screen. The raw dump is still one call away
 * (`auditRawCsv`) for anyone who needs the stored values exactly.
 */
export const auditCsv = (views: AuditRowView[]): string =>
	buildCsv(
		[
			'when',
			'actor',
			'actor_role',
			'action',
			'record_type',
			'record',
			'change',
			'source',
		],
		views.map((view) => [
			view.occurredAt,
			view.actor.name,
			view.actor.role ?? '',
			view.action.label,
			AUDIT_ENTITY_LABELS[view.entity.type] ?? view.entity.type,
			view.entity.label,
			view.changes
				.map((change) =>
					change.before === '—'
						? `${change.label}: ${change.after}`
						: change.after === '—'
							? `${change.label}: ${change.before} (removed)`
							: `${change.label}: ${change.before} → ${change.after}`
				)
				.join('; '),
			view.origin === 'trail' ? 'audit trail' : 'roster creation date',
		])
	);
