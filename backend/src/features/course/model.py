from datetime import time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from shared.mixins import TimestampMixin


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), unique=True)
    course_name: Mapped[str] = mapped_column(String(100))

    units: Mapped[int] = mapped_column(Integer)
    session_duration_hours: Mapped[float] = mapped_column(Numeric(3, 1))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    course_offerings: Mapped[list["CourseOffering"]] = relationship(
        "CourseOffering", back_populates="course"
    )


class CourseOffering(TimestampMixin, Base):
    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "program_id",
            "semester",
            "academic_year",
            name="uq_course_offering",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    program_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programs.id", ondelete="RESTRICT"), index=True
    )
    year_level_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("year_levels.id", ondelete="RESTRICT"), index=True
    )
    semester: Mapped[str] = mapped_column(String(20))
    academic_year: Mapped[str] = mapped_column(String(20))
    sessions_per_week: Mapped[int] = mapped_column(Integer)
    semester_weeks: Mapped[int] = mapped_column(Integer)
    schedule_days: Mapped[str] = mapped_column(String(10))
    schedule_start_time: Mapped[time] = mapped_column(Time)
    schedule_end_time: Mapped[time] = mapped_column(Time)
    classroom_name: Mapped[str | None] = mapped_column(String(100))
    classroom_lat: Mapped[float | None] = mapped_column(Float)
    classroom_lng: Mapped[float | None] = mapped_column(Float)
    default_present_window_minutes: Mapped[int] = mapped_column(
        Integer, server_default=text("5")
    )
    default_late_window_minutes: Mapped[int] = mapped_column(
        Integer, server_default=text("10")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    course: Mapped[Course] = relationship("Course", back_populates="course_offerings")
