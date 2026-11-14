from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Integer,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import CheckConstraint, UniqueConstraint

from core.database import Base
from features.auth.model import User
from features.excuse.model import ExcuseRequest
from features.session.model import Session
from features.student.model import Student
from shared.enums import SyncStatus, ValidationStatus
from shared.mixins import CreatedAtMixin


class Attendance(CreatedAtMixin, Base):
    __tablename__ = "attendance_records"

    # `timestamp` carries the date-range filters that analytics, reports and the
    # three dashboards all run (`>= start AND < end`), and it had no index while
    # every FK column did — so each of those was a sequential scan of the whole
    # table. The composite covers the per-student variant the student dashboard
    # uses (`student_id = ? AND timestamp BETWEEN ...`), which the single-column
    # index can only serve by filtering on student_id afterwards.
    __table_args__ = (
        Index("ix_attendance_records_student_id_timestamp", "student_id", "timestamp"),
        Index("ix_attendance_records_student_session", "student_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="RESTRICT"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lng: Mapped[float | None] = mapped_column(Float)
    validation_status: Mapped[str] = mapped_column(
        String(20), server_default=ValidationStatus.PENDING.value
    )
    sync_status: Mapped[str] = mapped_column(
        String(20), server_default=SyncStatus.PENDING.value
    )
    liveness_evidence: Mapped[dict | None] = mapped_column(JSONB)
    face_match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    scanned_via: Mapped[str | None] = mapped_column(String(20))
    original_status: Mapped[str | None] = mapped_column(String(20))
    excuse_reason: Mapped[str | None] = mapped_column(Text)
    excused_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    excused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excuse_type: Mapped[str | None] = mapped_column(String(30))
    excuse_request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("excuse_requests.id", ondelete="RESTRICT"), index=True
    )

    student: Mapped[Student] = relationship()
    session: Mapped[Session] = relationship()
    excused_by_user: Mapped[User | None] = relationship(foreign_keys=[excused_by])
    excuse_request: Mapped[ExcuseRequest | None] = relationship()


class AttendanceAttemptCounter(Base):
    """Durable per-(student, session) attempt counter.

    Incremented in its own committed transaction so that attempts that fail
    validation (and roll back the main transaction) still count toward the
    per-student attempt cap.
    """

    __tablename__ = "attendance_attempt_counters"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "session_id", name="uq_attendance_attempt_counters_student_session"
        ),
        CheckConstraint(
            "attempts >= 0", name="ck_attendance_attempt_counters_attempts_nonnegative"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="RESTRICT"), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
