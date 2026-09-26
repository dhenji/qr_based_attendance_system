"""add mfa_backup_codes code_fingerprint

Adds an indexed keyed digest of the normalized backup code so
AuthService.verify_backup_code can resolve the single candidate row instead of
Argon2id-verifying all ten unused codes on every MFA login. code_hash remains
the authoritative Argon2id value (ADR-054); this column is lookup sugar only.

Added with a temporary server_default so the migration is safe even if
mfa_backup_codes already has rows. Any pre-existing row is backfilled with the
empty string, which no fingerprint can ever match, so a backup code issued
before this migration can no longer be redeemed and the user must regenerate.
That is acceptable here because the table was introduced in the immediately
preceding revision (2a437ca93c53) and has not been released.

Revision ID: 33eabbfbfa6a
Revises: 2a437ca93c53
Create Date: 2026-09-26 12:30:14.138222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33eabbfbfa6a'
down_revision: Union[str, None] = '2a437ca93c53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mfa_backup_codes',
        sa.Column(
            'code_fingerprint',
            sa.String(length=64),
            nullable=False,
            server_default='',
        ),
    )
    op.create_index(
        op.f('ix_mfa_backup_codes_code_fingerprint'),
        'mfa_backup_codes',
        ['code_fingerprint'],
        unique=False,
    )
    op.alter_column('mfa_backup_codes', 'code_fingerprint', server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f('ix_mfa_backup_codes_code_fingerprint'), table_name='mfa_backup_codes'
    )
    op.drop_column('mfa_backup_codes', 'code_fingerprint')
