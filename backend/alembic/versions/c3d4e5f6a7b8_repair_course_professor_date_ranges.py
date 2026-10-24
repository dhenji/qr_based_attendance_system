"""Repair inverted course professor date ranges.

Ending a future-dated assignment used to write ``effective_to = today`` even
when ``effective_from`` was in the future, producing an inverted interval.
Delete those never-started rows (their audit trail keeps the record) and add a
database-level guard against the same bug class.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-19
"""

from __future__ import annotations

from alembic import op


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These intervals are invalid by definition; they can only be the result
    # of the future-end bug. The row never took effect, so deleting it is safe.
    op.execute(
        "DELETE FROM course_professors "
        "WHERE effective_to IS NOT NULL AND effective_to < effective_from"
    )
    op.create_check_constraint(
        "ck_course_professors_date_order",
        "course_professors",
        "effective_to IS NULL OR effective_to >= effective_from",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_course_professors_date_order",
        "course_professors",
        type_="check",
    )
