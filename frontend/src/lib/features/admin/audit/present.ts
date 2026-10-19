// features/admin/audit/present.ts
// The export of the audit trail.
//
// The trail is READ on the server: `features/system/audit_labels.py` derives
// the actor's name, the subject's name, the summary and the field-level
// change from the stored snapshot, and the endpoint returns both. This module
// only exports what came back, so the file answers the same question the
// screen does without the screen.

import { buildCsv } from '$lib/features/report/service';
import type { AuditLogRow } from '$lib/features/admin/audit/service';
import { AUDIT_ENTITY_TYPES } from '$lib/features/admin/audit/service';

const entityLabel = (type: string): string =>
	AUDIT_ENTITY_TYPES.find((entry) => entry.id === type)?.label ?? type;

export const auditCsv = (rows: AuditLogRow[]): string =>
	buildCsv(
		[
			'when',
			'actor',
			'actor_role',
			'action',
			'record_type',
			'record',
			'change',
			'entry_id',
		],
		rows.map((row) => [
			row.performed_at,
			row.actor.name,
			row.actor.role ?? '',
			row.action_label,
			entityLabel(row.subject.type),
			row.subject.label,
			row.changes
				.map((change) =>
					change.before === '—'
						? `${change.label}: ${change.after}`
						: change.after === '—'
							? `${change.label}: ${change.before} (removed)`
							: `${change.label}: ${change.before} → ${change.after}`
				)
				.join('; '),
			row.id,
		])
	);
