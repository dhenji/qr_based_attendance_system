"""index the audit trail's action column

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-20

`audit_logs.action` was the one audited column carrying no index, so an
action filter — and an action sort — was a sequential scan of the whole
table. ADR-064 named it as the first thing to add if the table grew, and
it grew: the trail now records every roster creation (ADR-088) as well as
every structural change, and nothing in it is ever deleted (ADR-089).

The index is COMPOSITE rather than a bare `(action)`, because the read
endpoint filters by action and orders by `performed_at DESC, id DESC`. A
single-column index would find the matching rows and then still have to
sort them; the composite returns them already in order, so the sort
disappears with the scan.

`entity_type` keeps its own single-column index and does not get a
composite here. It is not the same case: an entity type is not selective
(a structural change is common), so the planner prefers the `performed_at`
range scan and filters the rest — which is already index-assisted. `action`
had NO index at all, which is why it is the one that is named.

Fixing forward rather than by editing an applied revision (ADR-065): the
model is the authoritative shape, and there is no earlier revision to
correct — this index simply never existed.

Safe on existing data: `CREATE INDEX` builds the index alongside the rows
rather than rewriting them, so there is nothing to conflict and no way for
it to fail partway on bad data.

One operational note, because it is a real trade-off rather than a free
win. Plain `CREATE INDEX` takes a lock that blocks writes to the table for
the duration of the build. That is milliseconds at current row counts but
would be felt on a table this size if it were much larger, and
`CREATE INDEX CONCURRENTLY` is the alternative — it cannot run inside a
transaction, so adopting it means this migration moving to an
`autocommit_block()` and giving up the transactional guarantee the rest of
this chain relies on. Kept transactional here: the alternative trades a
brief write pause for a migration that cannot be rolled back atomically,
and that is the worse default for a schema change.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_action_performed_at",
        "audit_logs",
        ["action", "performed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action_performed_at", table_name="audit_logs")
