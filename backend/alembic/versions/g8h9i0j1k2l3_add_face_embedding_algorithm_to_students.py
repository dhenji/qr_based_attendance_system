"""add face_embedding_algorithm to students

Revision ID: g8h9i0j1k2l3
Revises: 2a3b4c5d6e7f
Create Date: 2026-10-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g8h9i0j1k2l3'
down_revision = '2a3b4c5d6e7f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('students', sa.Column('face_embedding_algorithm', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('students', 'face_embedding_algorithm')
