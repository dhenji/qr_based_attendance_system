"""remove the unused users.username display handle

Revision ID: c9d4e5f6a7b8
Revises: 1e1582c4e9f8
Create Date: 2026-10-11

Email is the sole login/roster identity; `username` was a user-picked
display handle with its own UNIQUE guard and two 409s (`username_exists`,
`admin_user_username_exists`) but no functional consumer. Per the linked
issue it is removed rather than kept as an optional display field.

Fixing forward per ADR-065 (never edit an applied revision).

Safe on existing data: every row already has a value, and nothing else
references the column (no FK, no index besides the unique constraint), so
dropping the constraint + column cannot orphan rows. Downgrade re-adds a
NOT NULL column with a temporary server default so it succeeds on rows
created while the column was gone; the default is dropped immediately
after the backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d4e5f6a7b8"
down_revision: Union[str, None] = "1e1582c4e9f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("users_username_key", "users", type_="unique")
    op.drop_column("users", "username")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "username", sa.String(length=20), nullable=False, server_default=""
        ),
    )
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.alter_column("users", "username", server_default=None)
