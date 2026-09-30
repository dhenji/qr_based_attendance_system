from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from features.auth.model import User
from shared.mixins import TimestampMixin


class Professor(TimestampMixin, Base):
    __tablename__ = "professors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(server_default=true())

    user: Mapped[User | None] = relationship()
