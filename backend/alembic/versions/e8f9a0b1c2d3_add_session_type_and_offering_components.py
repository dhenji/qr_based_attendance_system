"""Add sessions.session_type and offering_components (D77).

Lecture vs laboratory moves from a frontend-only label to persisted data:
every session carries its type, and each offering carries one scheduled
component per type (days/times/room) so a single course can mix a Monday
laboratory with a Wednesday lecture. Existing sessions backfill to lecture,
and every existing offering gains one lecture component mirroring its
schedule/classroom.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = "c9d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "session_type",
            sa.String(length=20),
            server_default=sa.text("'lecture'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_sessions_session_type",
        "sessions",
        "session_type IN ('lecture', 'lab')",
    )

    op.create_table(
        "offering_components",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("offering_id", sa.BigInteger(), nullable=False),
        sa.Column("session_type", sa.String(length=20), nullable=False),
        sa.Column("schedule_days", sa.String(length=10), nullable=False),
        sa.Column("schedule_start_time", sa.Time(), nullable=False),
        sa.Column("schedule_end_time", sa.Time(), nullable=False),
        sa.Column("classroom_name", sa.String(length=100), nullable=True),
        sa.Column("classroom_lat", sa.Float(), nullable=True),
        sa.Column("classroom_lng", sa.Float(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["offering_id"], ["course_offerings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "offering_id",
            "session_type",
            "schedule_days",
            "schedule_start_time",
            name="uq_offering_component",
        ),
    )
    op.create_index(
        op.f("ix_offering_components_offering_id"),
        "offering_components",
        ["offering_id"],
        unique=False,
    )

    # One lecture component per existing offering, mirroring its schedule and
    # classroom, so every offering has a component to pre-fill sessions from.
    op.execute(
        sa.text(
            "INSERT INTO offering_components "
            "(offering_id, session_type, schedule_days, schedule_start_time, "
            "schedule_end_time, classroom_name, classroom_lat, classroom_lng, "
            "is_active) "
            "SELECT id, 'lecture', schedule_days, schedule_start_time, "
            "schedule_end_time, classroom_name, classroom_lat, classroom_lng, "
            "true FROM course_offerings"
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_offering_components_offering_id"),
        table_name="offering_components",
    )
    op.drop_table("offering_components")
    op.drop_constraint("ck_sessions_session_type", "sessions", type_="check")
    op.drop_column("sessions", "session_type")
