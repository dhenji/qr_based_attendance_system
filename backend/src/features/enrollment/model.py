from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.course.model import CourseOffering
from features.student.model import Student
from shared.mixins import CreatedAtMixin


class Enrollment(CreatedAtMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "offering_id",
            "academic_year",
            name="uq_enrollment_student_offering_academic_year",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("students.id", ondelete="RESTRICT"),
        index=True,
    )

    offering_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course_offerings.id", ondelete="RESTRICT"),
        index=True,
    )
    semester: Mapped[str] = mapped_column(String(20))
    academic_year: Mapped[str] = mapped_column(String(20))

    student: Mapped[Student] = relationship()
    offering: Mapped[CourseOffering] = relationship()
