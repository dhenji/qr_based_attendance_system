from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.mixins import CreatedAtMixin


class CourseProfessor(CreatedAtMixin, Base):
    __tablename__ = "course_professors"
    __table_args__ = (
        PrimaryKeyConstraint("offering_id", "professor_id", "effective_from"),
    )

    offering_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course_offerings.id", ondelete="RESTRICT"),
    )
    professor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("professors.id", ondelete="RESTRICT"),
    )
    effective_from: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=false())
    effective_to: Mapped[date | None] = mapped_column(Date)
    semester: Mapped[str] = mapped_column(String(20))
    assigned_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
