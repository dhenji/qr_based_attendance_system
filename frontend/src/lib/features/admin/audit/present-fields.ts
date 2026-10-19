// features/admin/audit/present-fields.ts
// How an audit row is PRESENTED, as opposed to what it SAYS.
//
// The wording — the verb, the record's name, the field labels, the change
// list — comes from the server, in `features/system/audit_labels.py`. It is
// derived there because that is where the snapshots live, and because a
// vocabulary kept in two places drifts.
//
// What is left here is presentation the server has no business knowing
// about: the colour of a chip, and where a record's link points.

import type { AuditAction, AuditEntityType } from '$lib/shared/types';
import {
	adminCourse,
	adminOffering,
	adminProgram,
	adminProfessor,
	adminStudent,
	Routes,
} from '$lib/shared/constants/routes';

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

/**
 * Where a record's name links to.
 *
 * A detail page where one exists, and the list page where the subject has
 * no page of its own. `null` means the record is not somewhere an
 * administrator can go — a class session, for instance, has no admin screen.
 */
const SUBJECT_LINKS: Partial<Record<AuditEntityType, (id: number) => string>> = {
	program: (id) => adminProgram(id),
	course: (id) => adminCourse(id),
	course_offering: (id) => adminOffering(id),
	student: (id) => adminStudent(id),
	professor: (id) => adminProfessor(id),
	// A year level lives under its program and a schedule component under
	// its offering, so both go to the list their parent is listed in.
	year_level: () => Routes.ADMIN_PROGRAMS,
	offering_component: () => Routes.ADMIN_OFFERINGS,
	user: () => Routes.ADMIN_USERS,
	excuse: () => Routes.ADMIN_EXCUSES,
	backup: () => Routes.ADMIN_SYSTEM_SETTINGS,
};

export const subjectHref = (
	type: AuditEntityType,
	id: number | null
): string | null => {
	if (id === null) return null;
	const link = SUBJECT_LINKS[type];
	return link ? link(id) : null;
};
