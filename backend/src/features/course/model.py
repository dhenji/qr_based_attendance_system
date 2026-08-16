from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), unique=True)
    course_name: Mapped[str] = mapped_column(String(200))
    classroom_lat: Mapped[float] = mapped_column(Float)
    classroom_lng: Mapped[float] = mapped_column(Float)
    schedule: Mapped[str | None] = mapped_column(String(200))
