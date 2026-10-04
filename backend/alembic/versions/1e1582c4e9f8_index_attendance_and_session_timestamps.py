"""index the timestamp columns the date-range filters already use

Revision ID: 1e1582c4e9f8
Revises: b1c4e7f0a2d6
Create Date: 2026-10-04

`attendance_records.timestamp` and `sessions.created_at` both carried every
date-range filter in the codebase while having no index, even though every
foreign-key column on those tables has one. Anything filtering a window was a
sequential scan of the whole table.

Two consumers made that worse rather than better. `SessionService._sessions_stmt`
keys on `created_at` -- not `scheduled_start_time` -- so the professor dashboard,
the professor reports and the admin reports all filtered an unindexed column, and
the student/professor dashboards added three more such queries when Phase 12
landed (`scans_today` twice, plus today's session tiles). The admin dashboard's
`scans_today` is a full scan of `attendance_records` on every page load.

Three indexes, because there are two distinct query shapes:

- `ix_attendance_records_timestamp` serves the all-students window scan
  (`timestamp >= start AND timestamp < end`), which is what the admin dashboard
  and the reports trend buckets run.
- `ix_attendance_records_student_id_timestamp` serves the per-student window
  (`student_id = ? AND timestamp BETWEEN ...`). The single-column index can only
  help that after filtering on `student_id`, and a composite is what Postgres
  needs to treat it as one range lookup.
- `ix_sessions_created_at` serves every session-scoped window.

Fixing forward rather than by editing an applied revision: the model is the
authoritative shape, and there is no earlier revision to correct -- these columns
simply never got an index. Per ADR-065 an applied revision is never edited.

Safe on existing data: `CREATE INDEX` does not read or rewrite user rows into a
new shape, only builds the index alongside them, so there is nothing to conflict
and no way for this to fail partway on bad data.

One operational note, because it is a real trade-off rather than a free win.
Plain `CREATE INDEX` takes a lock that blocks writes to the table for the
duration of the build. That is milliseconds-to-seconds at current row counts but
would be felt on a large `attendance_records`, and `CREATE INDEX CONCURRENTLY`
is the alternative -- it cannot run inside a transaction, so adopting it means
this migration moving to an `autocommit_block()` and giving up the transactional
guarantee the rest of this chain relies on. Kept transactional here: the
alternative trades a brief write pause for a migration that cannot be rolled
back atomically, and that is the worse default for a schema change.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e1582c4e9f8"
down_revision: Union[str, None] = "b1c4e7f0a2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_attendance_records_student_id_timestamp",
        "attendance_records",
        ["student_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attendance_records_timestamp"),
        "attendance_records",
        ["timestamp"],
        unique=False,
    )
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_index(
        op.f("ix_attendance_records_timestamp"), table_name="attendance_records"
    )
    op.drop_index(
        "ix_attendance_records_student_id_timestamp", table_name="attendance_records"
    )
