from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.enums import BackupKind, BackupStatus, BackupStorage


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
