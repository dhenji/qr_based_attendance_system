"""converge app_settings key on its model

Revision ID: b1c4e7f0a2d6
Revises: f4a9c2b7d103
Create Date: 2026-10-03

`e7f8a9b0c1d2` created `app_settings` with a UNIQUE constraint *and* a separate
non-unique index on the same column. The model declares

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)

which in SQLAlchemy means one unique index and no separate constraint, so
`alembic check` reported three operations against this table from the moment
Phase 12.0 landed until now.

The model is the authoritative shape and the constraint was the redundant half:
Postgres already implements UNIQUE as an index, so the extra `ix_app_settings_key`
was dead weight *and* non-unique. This converges the database onto the model.

Fixing forward rather than by editing `e7f8a9b0c1d2`, which is already applied
in every environment that has run it.

Safe on existing data: the UNIQUE constraint has enforced uniqueness since the
table was created, so no duplicate keys can exist and the new unique index
cannot fail. Postgres DDL is transactional and alembic runs each migration in a
transaction, so the drop-and-recreate has no window in which a concurrent write
could insert a duplicate.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c4e7f0a2d6'
down_revision: Union[str, None] = 'f4a9c2b7d103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('app_settings_key_key', 'app_settings', type_='unique')
    op.drop_index('ix_app_settings_key', table_name='app_settings')
    op.create_index(op.f('ix_app_settings_key'), 'app_settings', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_settings_key'), table_name='app_settings')
    op.create_index('ix_app_settings_key', 'app_settings', ['key'], unique=False)
    op.create_unique_constraint('app_settings_key_key', 'app_settings', ['key'])