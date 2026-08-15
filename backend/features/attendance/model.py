from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
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

    student: Mapped[Student] = relationship()
    session: Mapped[Session] = relationship()
