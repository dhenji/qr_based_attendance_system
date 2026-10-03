"""add student_risk_scores_staging

Revision ID: d4e5f6a7b8c9
Revises: a562c3f8a6f7
Create Date: 2026-10-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'a562c3f8a6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_risk_scores_staging',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('student_id', sa.BigInteger(), nullable=False),
        sa.Column('offering_id', sa.BigInteger(), nullable=False),
        sa.Column('semester', sa.String(length=20), nullable=False),
        sa.Column('risk_probability', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('risk_level', sa.String(length=10), nullable=False),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('computed_day', sa.Date(), nullable=False),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("risk_level IN('low','medium','high')", name='ck_student_risk_scores_staging_risk_level'),
        sa.ForeignKeyConstraint(['offering_id'], ['course_offerings.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_student_risk_scores_staging_computed_at'), 'student_risk_scores_staging', ['computed_at'], unique=False)
    op.create_index(op.f('ix_student_risk_scores_staging_offering_id'), 'student_risk_scores_staging', ['offering_id'], unique=False)
    op.create_index(op.f('ix_student_risk_scores_staging_student_id'), 'student_risk_scores_staging', ['student_id'], unique=False)
    op.create_index('uq_student_risk_scores_staging_student_offering_semester_day', 'student_risk_scores_staging', ['student_id', 'offering_id', 'semester', 'computed_day'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_student_risk_scores_staging_student_offering_semester_day', table_name='student_risk_scores_staging')
    op.drop_index(op.f('ix_student_risk_scores_staging_student_id'), table_name='student_risk_scores_staging')
    op.drop_index(op.f('ix_student_risk_scores_staging_offering_id'), table_name='student_risk_scores_staging')
    op.drop_index(op.f('ix_student_risk_scores_staging_computed_at'), table_name='student_risk_scores_staging')
    op.drop_table('student_risk_scores_staging')
