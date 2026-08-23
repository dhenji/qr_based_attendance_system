from sqlalchemy import BigInteger, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
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
    course: Mapped[str] = mapped_column(String(100))
    section: Mapped[str | None] = mapped_column(String(20))
    year_level: Mapped[int] = mapped_column()
    is_active: Mapped[bool] = mapped_column(server_default=true())

    user: Mapped[User | None] = relationship()
