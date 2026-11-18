from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base

from shared.enums import BackupKind, BackupStatus, BackupStorage
from shared.mixins import TimestampMixin


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)


class BackupLog(Base):
    __tablename__ = "backup_log"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{BackupKind.FULL.value}', '{BackupKind.ANALYTICS.value}')",
            name="ck_backup_log_kind",
        ),
        CheckConstraint(
            f"storage_backend IN ('{BackupStorage.LOCAL.value}', '{BackupStorage.S3.value}')",
            name="ck_backup_log_storage_backend",
        ),
        CheckConstraint(
            f"status in ('{BackupStatus.STARTED.value}', '{BackupStatus.COMPLETED.value}', '{BackupStatus.FAILED.value}')",
            name="ck_backup_log_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_backend: Mapped[str] = mapped_column(String(10))
    encryption_key_version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # `action` is the one audited column that carried no index, so an
        # action filter — and an action sort — was a sequential scan of the
        # whole table (ADR-064). The composite serves BOTH: the filter picks
        # the leading column, and `performed_at` is the column the read
        # endpoint orders by, so the rows come back already in order instead
        # of being sorted afterwards.
        Index("ix_audit_logs_action_performed_at", "action", "performed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    performed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
