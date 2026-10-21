"""Let an offering's attendance windows follow the system default (D93).

The offering's present and late windows are the professor-facing source of
truth for a session's scan windows, and they are read as "the offering's own
value, else the system-wide default, else the environment default". That
chain could not actually reach the system default: both columns were
`NOT NULL DEFAULT 5` / `NOT NULL DEFAULT 10`, so every offering carried a
value and the `app_settings` rows an administrator edits in Admin -> System
Settings were dead — the same shadowing the geofence radius had until D93.

NULL now means "follow the system default", exactly like the radius. The
server defaults go with it: a column whose NULL means *inherit* must not
also carry a hidden default for a direct INSERT, or the column has two
meanings and only one of them is reachable through the API.

Existing rows keep their values. The column has always been NOT NULL, so
"the administrator deliberately set 5" and "the column defaulted to 5" are
indistinguishable, and silently re-pointing an offering at the system
default could break a window budget somebody tuned. Inheriting is opt-in: an
administrator blanks the field to put an offering on the system default, and
a new offering inherits by default.

Fixing forward rather than by editing an applied revision (ADR-065).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "course_offerings",
        "default_present_window_minutes",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "course_offerings",
        "default_late_window_minutes",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # A row that was left on the system default has no value to restore, so
    # the downgrade seeds the columns before making them NOT NULL again.
    op.execute(
        sa.text(
            "UPDATE course_offerings "
            "SET default_present_window_minutes = 5 "
            "WHERE default_present_window_minutes IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE course_offerings "
            "SET default_late_window_minutes = 10 "
            "WHERE default_late_window_minutes IS NULL"
        )
    )
    op.alter_column(
        "course_offerings",
        "default_present_window_minutes",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("5"),
    )
    op.alter_column(
        "course_offerings",
        "default_late_window_minutes",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("10"),
    )
