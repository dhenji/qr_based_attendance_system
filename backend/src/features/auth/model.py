from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from shared.enums import OtpPurpose, UserRole
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
    security_question_hash: Mapped[str | None] = mapped_column(String(255))
    security_answer_hash: Mapped[str | None] = mapped_column(String(255))
    mfa_enable: Mapped[bool] = mapped_column(server_default=false())
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(server_default=false())
    is_active: Mapped[bool] = mapped_column(server_default=true())


class OtpCodes(CreatedAtMixin, Base):
    __tablename__ = "otp_codes"
    __table_args = (Index("ix_otp_codes_email_purpose", "email", "purpose"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(
        String(20), server_default=OtpPurpose.CLAIM.value
    )
    otp_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    user: Mapped[User | None] = relationship()
