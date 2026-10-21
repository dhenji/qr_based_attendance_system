"""Add sessions.schedule_overridden and the offering's default geofence radius.

Two columns for the session plan (D93): a session now records whether its
scheduled start/end came from the offering's plan or from an explicit
professor override, and the offering carries the geofence radius its sessions
default to.

`sessions.schedule_overridden` is the flag that keeps "the plan" and "the
exception" distinguishable. The scheduled start/end columns already existed,
but they were written as `now` / `now + duration` — the plan was never
copied onto the session, so there was nothing to compare against and no way
to tell a normal session from a rescheduled one. With the plan resolved
server-side (D93) the two can differ, and the audit trail needs to say so.

`course_offerings.default_classroom_radius_meters` puts the geofence radius
next to every other session default the offering already owns (its present
and late windows), instead of leaving it as a global environment value. The
resolution chain becomes payload -> offering -> app setting -> env.

The offering column is NULLABLE, and NULL means "inherit". That is the whole
point: a NOT NULL column defaulting to 50 would be indistinguishable from
"the administrator set 50", and the app setting an administrator actually
edits (Admin -> System Settings -> Geofence radius) could then never apply to
a session — the same shadowing that already affects the radius today,
because `SessionService` reads the environment default and never the
`app_settings` row. NULL keeps both knobs live: no offering value means the
app setting wins, an offering value means the administrator said so
specifically for that offering.

Both columns are additive, so existing rows are valid as they are: every
historical session reads as "not overridden" (it was opened at `now`, which
is what the old code always wrote) and every offering inherits the global
radius rather than carrying a value nobody chose.

Fixing forward rather than by editing an applied revision (ADR-065).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "schedule_overridden",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "course_offerings",
        sa.Column(
            "default_classroom_radius_meters",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("course_offerings", "default_classroom_radius_meters")
    op.drop_column("sessions", "schedule_overridden")
