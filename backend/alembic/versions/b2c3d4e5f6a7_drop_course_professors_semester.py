"""Drop redundant semester column from course_professors.

`course_professors.semester` duplicated `course_offerings.semester`, which is
the authoritative, immutable identity value. Assignments now derive their
semester from the offering on read.
"""

from __future__ import annotations

from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("course_professors", "semester")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column(
        "course_professors",
        sa.Column("semester", sa.String(length=20), nullable=False),
    )
