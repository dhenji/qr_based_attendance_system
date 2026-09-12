from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.course.model import CourseOffering
from features.student.model import Student


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "offering_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("students.id", ondelete="RESTRICT"),
        index=True,
    )

    offering_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("course_offerings.id", ondelete="RESTRICT"),
        index=True,
    )
    semester: Mapped[str | None] = mapped_column(String(20))

    student: Mapped[Student] = relationship()
    offering: Mapped[CourseOffering] = relationship()
