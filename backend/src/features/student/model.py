from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
from features.program.model import Program
from shared.mixins import TimestampMixin


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    student_id: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    program_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("programs.id", ondelete="RESTRICT"),
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(20))
    year_level: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())

    user: Mapped[User | None] = relationship("User")
    program: Mapped[Program] = relationship("Program")
