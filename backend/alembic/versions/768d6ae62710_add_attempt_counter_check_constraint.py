"""add attempt counter check constraint

Revision ID: 768d6ae62710
Revises: 150e539828ad
Create Date: 2026-11-14 11:41:13.199011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '768d6ae62710'
down_revision: Union[str, None] = '150e539828ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_attendance_attempt_counters_attempts_nonnegative",
        "attendance_attempt_counters",
        "attempts >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_attendance_attempt_counters_attempts_nonnegative",
        "attendance_attempt_counters",
        type_="check",
    )
