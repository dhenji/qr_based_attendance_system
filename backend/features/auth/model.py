from sqlalchemy import BigInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.enums import UserRole
from shared.mixins import CreatedAtMixin


class User(CreatedAtMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(20), server_default=UserRole.STUDENT.value)
    username: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=true())
