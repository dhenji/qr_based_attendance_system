from __future__ import annotations

import builtins
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.system import service as system_service
from features.system.exceptions import (
    BackupFailedException,
    BackupInProgressException,
    BackupStorageUnconfiguredException,
)
from features.system.model import BackupLog
from features.system.service import (
    SystemService,
    build_backup_filename,
    build_pg_dump_args,
    is_backup_running,
    is_monthly_anchor,
    libpq_url,
    select_prune_candidates,
    sha256_file,
)
from shared.enums import BackupStatus
from shared.storage import StorageUnconfiguredException


def _local_settings(
    settings: Settings, tmp_path: Path, **overrides: object
) -> Settings:
    return settings.model_copy(
        update={
            "backup_storage_type": "local",
            "backup_local_dir": str(tmp_path),
            "backup_encryption_key": "test-key-0123456789abcdef",
            **overrides,
        }
    )


def _row(**overrides: object) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    base = {
        "filename": "backup_20200101_000000.sql.gz.enc",
        "kind": "full",
        "size_bytes": 10,
        "sha256": "x" * 64,
        "storage_backend": "local",
        "encryption_key_version": 1,
        "started_at": now,
        "finished_at": now,
        "status": BackupStatus.COMPLETED.value,
        "error": None,
    }
    return SimpleNamespace(**{**base, **overrides})


def test_build_backup_filename_format() -> None:
    name = build_backup_filename(now=datetime(2026, 8, 25, 2, 0, tzinfo=timezone.utc))
    assert name == "backup_20260825_020000.sql.gz.enc"


def test_libpq_url_strips_asyncpg_driver() -> None:
    assert (
        libpq_url(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys"
        )
        == "postgresql://postgres:postgres@localhost:5432/attendance_sys"
    )


def test_pg_dump_args_default(settings: Settings) -> None:
    args = build_pg_dump_args(settings=settings)
    assert args[:4] == ["pg_dump", "-Fc", "--no-owner", "--no-privileges"]
    assert "--exclude-table-data=otp_codes" not in args


def test_pg_dump_args_excludes_otp_when_opted_in(settings: Settings) -> None:
    cfg = settings.model_copy(update={"backup_exclude_otp_codes": True})
    assert "--exclude-table-data=otp_codes" in build_pg_dump_args(settings=cfg)


def test_sha256_file(tmp_path: Path) -> None:
    target = tmp_path / "blob.enc"
    target.write_bytes(b"backup-bytes")
    import hashlib

    assert sha256_file(target) == hashlib.sha256(b"backup-bytes").hexdigest()


def test_is_monthly_anchor() -> None:
    assert is_monthly_anchor(datetime(2026, 8, 1, tzinfo=timezone.utc)) is True
    assert is_monthly_anchor(datetime(2026, 8, 15, tzinfo=timezone.utc)) is False


def test_prune_drops_stale_daily_but_keeps_monthly_anchor() -> None:
    now = datetime.now(timezone.utc)
    stale_daily = _row(finished_at=(now - timedelta(days=40)).replace(day=15))
    fresh_daily = _row(finished_at=now - timedelta(days=3))
    anchor_month = (now.replace(day=1).month - 2) % 12 or 12
    anchor_year = now.year if now.month > 2 else now.year - 1
    fresh_anchor = _row(
        finished_at=datetime(anchor_year, anchor_month, 1, tzinfo=timezone.utc)
    )
    doomed = select_prune_candidates(
        [stale_daily, fresh_daily, fresh_anchor],  # type: ignore[list-item]
        now=now,
        daily=30,
        monthly=12,
    )
    assert doomed == [stale_daily]


def test_prune_drops_stale_monthly_anchor() -> None:
    now = datetime.now(timezone.utc)
    total_months = now.year * 12 + now.month - 14
    old_anchor = _row(
        finished_at=datetime(
            total_months // 12, total_months % 12 or 12, 1, tzinfo=timezone.utc
        )
    )
    keeper = _row(finished_at=now)
    other = _row(finished_at=now - timedelta(days=2))
    doomed = select_prune_candidates(
        [old_anchor, keeper, other],  # type: ignore[list-item]
        now=now,
        daily=30,
        monthly=12,
    )
    assert doomed == [old_anchor]


def test_prune_never_drops_below_two_rows() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _row(finished_at=(now - timedelta(days=60)).replace(day=15)),
        _row(finished_at=(now - timedelta(days=61)).replace(day=16)),
    ]
    doomed = select_prune_candidates(
        rows,  # type: ignore[arg-type]
        now=now,
        daily=30,
        monthly=12,
    )
    assert doomed == []


def test_prune_skips_non_completed_rows() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _row(status=BackupStatus.STARTED.value, finished_at=None),
        _row(status=BackupStatus.FAILED.value, finished_at=now - timedelta(days=90)),
        _row(finished_at=now),
    ]
    assert (
        select_prune_candidates(
            rows,  # type: ignore[arg-type]
            now=now,
            daily=30,
            monthly=12,
        )
        == []
    )


async def test_run_backup_writes_completed_row_and_files(
    test_db_session: AsyncSession,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _local_settings(settings, tmp_path)

    async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
        tmp_enc.write_bytes(b"encrypted-backup-bytes")

    monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)
    row = await SystemService(test_db_session, cfg).run_backup()

    assert row.status == BackupStatus.COMPLETED.value
    assert row.kind == "full"
    assert row.finished_at is not None
    assert row.size_bytes == len(b"encrypted-backup-bytes")
    assert len(row.sha256) == 64
    target = tmp_path / row.filename
    assert target.is_file()
    assert (target.stat().st_mode & 0o777) == 0o600
    assert (tmp_path / f"{row.filename}.sha256").is_file()

    stored = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(stored) == 1


async def test_run_backup_marks_failed_row_on_pipeline_error(
    test_db_session: AsyncSession,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _local_settings(settings, tmp_path)

    async def _boom(self: SystemService, *, tmp_enc: Path) -> None:
        raise BackupFailedException("pg_dump exited 1")

    monkeypatch.setattr(SystemService, "_run_pipeline", _boom)
    with pytest.raises(BackupFailedException):
        await SystemService(test_db_session, cfg).run_backup()

    rows = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(rows) == 1
    assert rows[0].status == BackupStatus.FAILED.value
    assert rows[0].finished_at is not None
    assert "pg_dump" in (rows[0].error or "")


async def test_run_backup_without_key_is_storage_unconfigured(
    test_db_session: AsyncSession, settings: Settings, tmp_path: Path
) -> None:
    cfg = settings.model_copy(
        update={"backup_local_dir": str(tmp_path), "backup_encryption_key": ""}
    )
    with pytest.raises(BackupStorageUnconfiguredException):
        await SystemService(test_db_session, cfg).run_backup()

    rows = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(rows) == 1
    assert rows[0].status == BackupStatus.FAILED.value


async def test_run_backup_refuses_concurrent_run(
    test_db_session: AsyncSession, settings: Settings, tmp_path: Path
) -> None:
    cfg = _local_settings(settings, tmp_path)
    assert is_backup_running() is False
    async with system_service._BACKUP_LOCK:
        assert is_backup_running() is True
        with pytest.raises(BackupInProgressException):
            await SystemService(test_db_session, cfg).run_backup()


async def test_prune_retention_removes_files_and_rows(
    test_db_session: AsyncSession, settings: Settings, tmp_path: Path
) -> None:
    cfg = _local_settings(settings, tmp_path)
    now = datetime.now(timezone.utc)
    stale = BackupLog(
        filename="backup_20000101_000000.sql.gz.enc",
        kind="full",
        size_bytes=8,
        sha256="y" * 64,
        storage_backend="local",
        encryption_key_version=1,
        started_at=now - timedelta(days=400),
        finished_at=(now - timedelta(days=400)).replace(day=15),
        status=BackupStatus.COMPLETED.value,
        error=None,
    )
    fresh = BackupLog(
        filename=build_backup_filename(now=now),
        kind="full",
        size_bytes=8,
        sha256="z" * 64,
        storage_backend="local",
        encryption_key_version=1,
        started_at=now,
        finished_at=now,
        status=BackupStatus.COMPLETED.value,
        error=None,
    )
    fresh_yesterday = BackupLog(
        filename="backup_20000102_000000.sql.gz.enc",
        kind="full",
        size_bytes=8,
        sha256="w" * 64,
        storage_backend="local",
        encryption_key_version=1,
        started_at=now - timedelta(days=1),
        finished_at=now - timedelta(days=1),
        status=BackupStatus.COMPLETED.value,
        error=None,
    )
    test_db_session.add_all([stale, fresh, fresh_yesterday])
    await test_db_session.flush()
    (tmp_path / stale.filename).write_bytes(b"old")
    (tmp_path / f"{stale.filename}.sha256").write_text("old")
    (tmp_path / fresh.filename).write_bytes(b"new")

    summary = await SystemService(test_db_session, cfg).prune_retention()

    assert summary == {"removed": 1}
    remaining = (await test_db_session.scalars(select(BackupLog))).all()
    assert sorted(row.filename for row in remaining) == sorted(
        [fresh.filename, fresh_yesterday.filename]
    )
    assert not (tmp_path / stale.filename).exists()
    assert (tmp_path / fresh.filename).exists()


class _FakeS3Client:
    """Records the put/delete calls the backup S3 branch makes."""

    def __init__(self) -> None:
        self.put: list[dict[str, Any]] = []
        self.deleted: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put.append(kwargs)
        return {}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.deleted.append(kwargs)
        return {}


def _install_fake_boto3(
    monkeypatch: pytest.MonkeyPatch, client: _FakeS3Client
) -> None:
    module = ModuleType("boto3")
    module.client = lambda **kwargs: client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", module)


def _block_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def _guard(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "boto3" or name.startswith("boto3."):
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guard)


def _s3_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "backup_storage_type": "s3",
            "backup_s3_bucket": "test-bucket",
            "backup_s3_prefix": "backups/",
            "backup_encryption_key": "test-key-0123456789abcdef",
        }
    )


async def test_run_backup_s3_uploads_blob(
    test_db_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)

    async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
        tmp_enc.write_bytes(b"encrypted-backup-bytes")

    monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)
    row = await SystemService(test_db_session, _s3_settings(settings)).run_backup()

    assert row.status == BackupStatus.COMPLETED.value
    assert row.storage_backend == "s3"
    assert len(client.put) == 1
    assert client.put[0]["Bucket"] == "test-bucket"
    assert client.put[0]["Key"] == f"backups/{row.filename}"


async def test_run_backup_s3_without_boto3_is_failed(
    test_db_session: AsyncSession,
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_boto3(monkeypatch)

    async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
        tmp_enc.write_bytes(b"encrypted-backup-bytes")

    monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)
    cfg = _s3_settings(settings).model_copy(
        update={"backup_local_dir": str(tmp_path)}
    )
    with pytest.raises(StorageUnconfiguredException):
        await SystemService(test_db_session, cfg).run_backup()

    rows = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(rows) == 1
    assert rows[0].status == BackupStatus.FAILED.value


async def test_prune_retention_s3_deletes_object(
    test_db_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeS3Client()
    _install_fake_boto3(monkeypatch, client)
    cfg = _s3_settings(settings)
    now = datetime.now(timezone.utc)

    def _s3_row(filename: str, finished_at: datetime) -> BackupLog:
        return BackupLog(
            filename=filename,
            kind="full",
            size_bytes=8,
            sha256="y" * 64,
            storage_backend="s3",
            encryption_key_version=1,
            started_at=finished_at,
            finished_at=finished_at,
            status=BackupStatus.COMPLETED.value,
            error=None,
        )

    stale = _s3_row(
        "backup_20000115_000000.sql.gz.enc",
        (now - timedelta(days=400)).replace(day=15),
    )
    fresh = [_s3_row(f"backup_fresh_{i}.sql.gz.enc", now) for i in range(2)]
    test_db_session.add_all([stale, *fresh])
    await test_db_session.flush()

    summary = await SystemService(test_db_session, cfg).prune_retention()

    assert summary == {"removed": 1}
    assert client.deleted == [
        {"Bucket": "test-bucket", "Key": f"backups/{stale.filename}"}
    ]
    remaining = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(remaining) == 2
