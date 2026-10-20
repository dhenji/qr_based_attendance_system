"""Demote duplicate open-ended primary assignments.

Before the service enforced primary uniqueness, an offering could accumulate
multiple open-ended primary professors. Keep the most recently assigned
open-ended primary (latest ``assigned_at``) and demote the rest to assistants.
The service now rejects any new overlapping primary assignment.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-10-19
"""

from __future__ import annotations

from alembic import op


revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                offering_id,
                professor_id,
                effective_from,
                ROW_NUMBER() OVER (
                    PARTITION BY offering_id
                    ORDER BY assigned_at DESC NULLS LAST,
                             effective_from DESC,
                             professor_id DESC
                ) AS rn
            FROM course_professors
            WHERE is_primary IS TRUE
              AND effective_to IS NULL
        )
        UPDATE course_professors AS cp
        SET is_primary = FALSE
        FROM ranked AS r
        WHERE cp.offering_id = r.offering_id
          AND cp.professor_id = r.professor_id
          AND cp.effective_from = r.effective_from
          AND r.rn > 1
        """
    )


def downgrade() -> None:
    # The demoted rows cannot be identified afterwards, and re-promoting them
    # would recreate the invalid state this migration exists to repair.
    pass
