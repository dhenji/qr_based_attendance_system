from __future__ import annotations

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
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    security_question_hash: Mapped[str | None] = mapped_column(String(255))
    security_answer_hash: Mapped[str | None] = mapped_column(String(255))
    mfa_enabled: Mapped[bool] = mapped_column(server_default=false())
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(server_default=false())
    is_active: Mapped[bool] = mapped_column(server_default=true())

    is_locked: Mapped[bool] = mapped_column(server_default=false())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Session revocation: incremented to invalidate all outstanding JWTs for
    # this account (logout, password change/reset, MFA disable, admin
    # deactivation). Tokens carry the value at issuance and are rejected
    # when it no longer matches.
    token_version: Mapped[int] = mapped_column(Integer, server_default="0")

    # Last meaningful activity, used for server-side idle enforcement.
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Break-glass recovery code (Super Admin only): Argon2id hash of a
    # single-use, offline-stored code that can replace the security question
    # on the recovery path. NULL means "use the security question instead".
    recovery_code_hash: Mapped[str | None] = mapped_column(String(255))
    recovery_code_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Incremental lockout state (consecutive lockout count + decay anchor).
    lockout_level: Mapped[int] = mapped_column(Integer, server_default="0")
    last_lockout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Temporary admin override: while now < this timestamp the locked gate is
    # bypassed. NULL means no active override.
    lockout_override_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class OtpCodes(CreatedAtMixin, Base):
    __tablename__ = "otp_codes"
    __table_args__ = (Index("ix_otp_codes_email_purpose", "email", "purpose"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(
        String(20), server_default=OtpPurpose.CLAIM.value
    )
    otp_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # JTI of the recovery grant that authorised this OTP (FORGET_PASSWORD only).
    # Lets the reset step bind the OTP to the grant that minted it.
    recovery_grant_jti: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User | None] = relationship()


class MfaBackupCodes(CreatedAtMixin, Base):
    __tablename__ = "mfa_backup_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    # Keyed digest of the normalized code. Lets verify_backup_code resolve the one
    # candidate row with an indexed lookup instead of Argon2id-verifying all ten,
    # which kept ~10 sequential 64MB/t=3 hashes on the MFA login path. code_hash
    # remains the authoritative Argon2id check (ADR-054); this is lookup sugar.
    code_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
