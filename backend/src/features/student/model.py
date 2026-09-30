from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
from features.program.model import YearLevel
from shared.mixins import TimestampMixin


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    student_id: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    year_level_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("year_levels.id", ondelete="RESTRICT"),
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    face_embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    face_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    face_embedding_version: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )

    user: Mapped[User | None] = relationship()
    year_level: Mapped[YearLevel | None] = relationship()
