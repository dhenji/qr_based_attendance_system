from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.course.model import Course
from features.student.model import Student


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "academic_year"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    academic_year: Mapped[str | None] = mapped_column(String(20))

    student: Mapped[Student] = relationship()
    course: Mapped[Course] = relationship()
