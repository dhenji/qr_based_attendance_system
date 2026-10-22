"""Record when a session was really opened, and where it moved from (D94).

A session may only be opened while its class is running (D94). When the
professor opens it at a different time anyway, the row has to say so the way
the rest of the system reads it: the scheduled window the session carries,
the start it would have carried without the override, the moment the session
really opened, and the reason the professor gave.

Four columns:

* `actual_start_time` — when the session was opened. The service stamps it
  with its own clock, so it is the same instant the open-window check
  compared against. The server default only covers rows written straight to
  the table (the demo seed); existing rows backfill with the migration's
  `now()`, which is the closest the past allows.
* `original_scheduled_start_time` — the start the session would have carried
  without an override. Null when the session follows the plan, because there
  `scheduled_start_time` already is that start.
* `override_reason` — the professor's own note, optional.
* `created_by` — the account that opened the session. `professor_id` is the
  professor; this is the login behind it, and it is what the audit trail
  records as `performed_by`.

`start_time_override` is not a column: `schedule_overridden` already says
whether the professor moved the class (D93), and a second flag for the same
fact would be a second thing to keep in step.

Fixing forward rather than by editing an applied revision (ADR-065).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "actual_start_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "original_scheduled_start_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("override_reason", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessions_created_by",
        "sessions",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_created_by", table_name="sessions")
    op.drop_column("sessions", "created_by")
    op.drop_column("sessions", "override_reason")
    op.drop_column("sessions", "original_scheduled_start_time")
    op.drop_column("sessions", "actual_start_time")
