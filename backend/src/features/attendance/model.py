from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
from features.excuse.model import ExcuseRequest
from features.session.model import Session
from features.student.model import Student
from shared.enums import SyncStatus, ValidationStatus
from shared.mixins import CreatedAtMixin


class Attendance(CreatedAtMixin, Base):
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="RESTRICT"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
