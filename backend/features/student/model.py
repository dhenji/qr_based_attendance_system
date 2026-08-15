from sqlalchemy import BigInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.mixins import TimestampMixin


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    course: Mapped[str] = mapped_column(String(100))
    year_level: Mapped[int] = mapped_column()
    is_active: Mapped[bool] = mapped_column(server_default=true())
