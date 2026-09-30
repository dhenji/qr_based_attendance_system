from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.course.model import CourseOffering
from features.student.model import Student
from shared.enums import RiskLevel


class StudentRiskScore(Base):
    __tablename__ = "student_risk_scores"
    __table_args__ = (
        CheckConstraint(
            f"risk_level IN('{RiskLevel.LOW.value}',"
            f"'{RiskLevel.MEDIUM.value}',"
            f"'{RiskLevel.HIGH.value}')",
            name="ck_student_risk_scores_risk_level",
        ),
        Index(
            "uq_student_risk_scores_student_offering_semester_day",
            "student_id",
            "offering_id",
            "semester",
            "computed_day",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
    )
    offering_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course_offerings.id", ondelete="CASCADE"),
        index=True,
    )
    semester: Mapped[str] = mapped_column(String(20))
    risk_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    risk_level: Mapped[str] = mapped_column(String(10))
    features: Mapped[dict] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    computed_day: Mapped[date] = mapped_column(Date)

    student: Mapped[Student] = relationship()
    offering: Mapped[CourseOffering] = relationship()

    @property
    def risk_level_enum(self) -> RiskLevel:
        return RiskLevel(self.risk_level)
