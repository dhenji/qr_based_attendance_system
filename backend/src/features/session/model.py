from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.course.model import CourseOffering
from features.professor.model import Professor
from shared.mixins import CreatedAtMixin


class Session(CreatedAtMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "present_window_minutes + late_window_minutes <= duration_minutes",
            name="ck_session_window_sum_lte_duration",
        ),
        CheckConstraint(
            "session_type IN ('lecture', 'lab')",
            name="ck_sessions_session_type",
        ),
        # Every session-scoped date filter keys on `created_at` rather than
        # `scheduled_start_time` (see `SessionService._sessions_stmt`), including
        # the UTC day bounds the dashboards and reports build. It was unindexed.
        # Declared here rather than as `index=True` because the column is
        # inherited from `CreatedAtMixin`.
        Index("ix_sessions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), index=True
    )

    professor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("professors.id", ondelete="RESTRICT"), index=True
    )
    session_code: Mapped[str] = mapped_column(String(50), unique=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    present_window_minutes: Mapped[int] = mapped_column(Integer)
    late_window_minutes: Mapped[int] = mapped_column(Integer)
    scheduled_start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # D93: the scheduled start/end above carry the offering's plan, so a
    # session that was rescheduled differs from the plan it departed from.
    # This flag keeps the two distinguishable — in the read DTO, in the audit
    # trail, and in the professor's form.
    schedule_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    classroom_radius_meters: Mapped[int] = mapped_column(server_default=text("50"))
    classroom_name: Mapped[str | None] = mapped_column(String(100))
    classroom_lat: Mapped[float | None] = mapped_column(Float)
    classroom_lng: Mapped[float | None] = mapped_column(Float)
    # Lecture vs laboratory (D77). Defaults to lecture so pre-existing rows
    # and callers that do not send a type keep working.
    session_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'lecture'")
    )

    @property
    def computed_expires_at(self) -> datetime:
        """LEAST(created_at + duration_minutes, scheduled_end_time) - 12, D49."""

        return min(
            self.created_at + timedelta(minutes=self.duration_minutes),
            self.scheduled_end_time,
        )

    offering: Mapped[CourseOffering] = relationship()
    professor: Mapped[Professor] = relationship()
