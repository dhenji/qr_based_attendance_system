from __future__ import annotations

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
    components: Mapped[list["OfferingComponent"]] = relationship(
        "OfferingComponent", back_populates="offering"
    )


class OfferingComponent(TimestampMixin, Base):
    """One scheduled component of a course offering (D77).

    An offering with a single component behaves exactly like the pre-D77
    offering (one schedule + one classroom carried on `course_offerings`
    itself). A mixed course — e.g. laboratory on Monday, lecture on
    Wednesday — carries two components with distinct days/times/rooms.
    Sessions reference the offering only; their `session_type` says which
    component they belong to.
    """

    __tablename__ = "offering_components"
    __table_args__ = (
        UniqueConstraint(
            "offering_id",
            "session_type",
            "schedule_days",
            "schedule_start_time",
            name="uq_offering_component",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), index=True
    )
    session_type: Mapped[str] = mapped_column(String(20))
    schedule_days: Mapped[str] = mapped_column(String(10))
    schedule_start_time: Mapped[time] = mapped_column(Time)
    schedule_end_time: Mapped[time] = mapped_column(Time)
    classroom_name: Mapped[str | None] = mapped_column(String(100))
    classroom_lat: Mapped[float | None] = mapped_column(Float)
    classroom_lng: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    offering: Mapped[CourseOffering] = relationship(
        "CourseOffering", back_populates="components"
    )
