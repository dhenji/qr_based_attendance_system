"""add super-admin recovery fields

Revision ID: h9i0j1k2l3m4
Revises: c2d3e4f5a6b7
Create Date: 2026-11-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h9i0j1k2l3m4'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('recovery_code_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('recovery_code_used_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('otp_codes', sa.Column('recovery_grant_jti', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('otp_codes', 'recovery_grant_jti')
    op.drop_column('users', 'recovery_code_used_at')
    op.drop_column('users', 'recovery_code_hash')