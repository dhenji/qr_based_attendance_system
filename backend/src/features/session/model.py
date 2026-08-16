from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
from features.course.model import Course


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    professor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    session_code: Mapped[str] = mapped_column(String(50), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    classroom_radius_meters: Mapped[int] = mapped_column(server_default="50")

    course: Mapped[Course] = relationship()
    professor: Mapped[User] = relationship()
