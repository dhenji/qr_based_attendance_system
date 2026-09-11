from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.session.model import Session
from features.student.model import Student
from shared.enums import ExcuseStatus


class ExcuseRequest(Base):
    __tablename__ = "excuse_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="RESTRICT"), index=True
    )
    initiated_by: Mapped[str] = mapped_column(String(20))
    initiated_via: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    attachment_urls: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), server_default=ExcuseStatus.PENDING.value
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    student: Mapped[Student] = relationship()
    session: Mapped[Session] = relationship()
