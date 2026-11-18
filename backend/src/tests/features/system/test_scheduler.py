"""The cron scheduler: job registration, lifecycle, and the two job adapters.

The adapter tests all point `database.get_session()` at `test_db_session`,
because that is the one thing a job does that a request never does - it owns
its own transaction. `_get_db` commits for HTTP handlers; a cron run has no
handler, so if either adapter forgot its commit every row it wrote would vanish
when the connection closed. Committing for real is therefore the thing to
assert, not a detail: the tests read rows back through a fresh query after the
adapter returns, and the session fixture's teardown rollback would otherwise
mask a missing commit.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.database import database
from core.scheduler import (
    JOB_BACKUP,
    JOB_RISK_BATCH,
    BackgroundScheduler,
    drain_in_flight,
    in_flight_jobs,
    resolve_timezone,
    scheduled_job_running,
    track,
)

from shared.enums import BackupKind, BackupStatus, BackupStorage

from features.analytics import batch as analytics_batch
from features.analytics.batch import run_scheduled_risk_batch
from features.analytics.constants import RISK_BATCH_RUNTIME_BUDGET_MS
from features.analytics.model import StudentRiskScore
from features.system import service as system_service
from features.system.exceptions import BackupFailedException
from features.system.model import BackupLog
from features.system.service import SystemService, run_scheduled_backup


def _cron_settings(settings: Settings, **overrides: Any) -> Settings:
    return settings.model_copy(
        update={
            "risk_batch_cron": "0 2 * * *",
            "backup_cron": "0 3 * * *",
            "scheduler_timezone": "UTC",
            **overrides,
        }
    )


async def _noop() -> None:
    return None


def _use_test_session(monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
    """Point every `database.get_session()` at the test session."""

    @asynccontextmanager
    async def _fake_get_session() -> AsyncIterator[AsyncSession]:
        yield session

    monkeypatch.setattr(database, "get_session", _fake_get_session)


# --- timezone resolution ---------------------------------------------------


def test_resolve_timezone_accepts_a_known_zone() -> None:
    assert str(resolve_timezone("UTC")) == "UTC"


def test_resolve_timezone_falls_back_to_utc(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="core.scheduler"):
        resolved = resolve_timezone("Not/AZone")

    assert str(resolved) == "UTC"
    assert "falling back to UTC" in caplog.text


# --- registration ----------------------------------------------------------


async def test_register_schedules_both_jobs_from_settings(
    settings: Settings,
) -> None:
    scheduler = BackgroundScheduler(_cron_settings(settings))

    scheduler.register(JOB_RISK_BATCH, "0 2 * * *", _noop)
    scheduler.register(JOB_BACKUP, "0 3 * * *", _noop)

    assert scheduler.job_ids() == [JOB_RISK_BATCH, JOB_BACKUP]

    await scheduler.shutdown()


def test_a_malformed_cron_raises_at_registration(
    settings: Settings,
) -> None:
    """Fail while an operator is watching the boot, not silently at 02:00."""
    scheduler = BackgroundScheduler(_cron_settings(settings))

    with pytest.raises(ValueError):
        scheduler.register(JOB_RISK_BATCH, "every tuesday", _noop)

    assert scheduler.job_ids() == []


async def test_start_is_idempotent(settings: Settings) -> None:
    """The double-instantiation guard: `uvicorn --reload` re-enters the lifespan."""
    scheduler = BackgroundScheduler(_cron_settings(settings))
    scheduler.register(JOB_BACKUP, "0 3 * * *", _noop)

    scheduler.start()
    scheduler.start()

    assert scheduler.running is True
    assert scheduler.job_ids() == [JOB_BACKUP]

    await scheduler.shutdown()


async def test_shutdown_stops_and_empties(settings: Settings) -> None:
    scheduler = BackgroundScheduler(_cron_settings(settings))
    scheduler.register(JOB_BACKUP, "0 3 * * *", _noop)
    scheduler.start()

    await scheduler.shutdown()

    assert scheduler.running is False
    assert scheduler.job_ids() == []

    # A second shutdown is a no-op, not an error.
    await scheduler.shutdown()


async def test_reregistering_the_same_name_replaces_rather_than_stacks(
    settings: Settings,
) -> None:
    scheduler = BackgroundScheduler(_cron_settings(settings))
    scheduler.register(JOB_BACKUP, "0 3 * * *", _noop)

    scheduler.register(JOB_BACKUP, "30 4 * * *", _noop)

    assert scheduler.job_ids() == [JOB_BACKUP]

    await scheduler.shutdown()


# --- in-flight tracking ----------------------------------------------------


async def test_track_reports_a_running_job() -> None:
    assert scheduled_job_running(JOB_BACKUP) is False

    async with track(JOB_BACKUP):
        assert scheduled_job_running(JOB_BACKUP) is True
        assert scheduled_job_running() is True
        assert in_flight_jobs() == {JOB_BACKUP: 1}

    assert scheduled_job_running(JOB_BACKUP) is False
    assert scheduled_job_running() is False


async def test_track_clears_when_the_body_raises() -> None:
    with pytest.raises(RuntimeError):
        async with track(JOB_RISK_BATCH):
            raise RuntimeError("boom")

    assert scheduled_job_running(JOB_RISK_BATCH) is False


async def test_shutdown_cancels_a_job_still_running() -> None:
    """Shutdown must not return with a task still holding the engine."""
    started = asyncio.Event()
    released = False

    async def _hang() -> None:
        nonlocal released
        async with track(JOB_BACKUP):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                released = True
                raise

    task = asyncio.create_task(_hang())
    await started.wait()
    try:
        assert await drain_in_flight(timeout=5.0) == set()
    finally:
        await asyncio.gather(task, return_exceptions=True)

    assert released is True
    assert scheduled_job_running(JOB_BACKUP) is False


async def test_drain_never_cancels_its_own_caller() -> None:
    """A caller already inside `track()` must survive its own drain."""
    reached = asyncio.Event()

    async def _sibling() -> None:
        async with track(JOB_BACKUP):
            reached.set()
            await asyncio.sleep(30)

    async with track(JOB_BACKUP):
        sibling = asyncio.create_task(_sibling())
        await reached.wait()
        try:
            pending = await drain_in_flight(timeout=5.0)
        finally:
            await asyncio.gather(sibling, return_exceptions=True)

    assert pending == set()
    assert asyncio.current_task() is not None
    assert not asyncio.current_task().cancelled()


async def test_drain_reports_a_task_that_will_not_unwind() -> None:
    """A wedged job is abandoned rather than allowed to hang the process."""
    unwound = False

    async def _wedged() -> None:
        nonlocal unwound
        async with track(JOB_BACKUP):
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                # Swallow the cancellation, standing in for a subprocess that
                # refuses to die.
                await asyncio.sleep(30)
            finally:
                unwound = True

    task = asyncio.create_task(_wedged())
    await asyncio.sleep(0)
    try:
        assert len(await drain_in_flight(timeout=0.05)) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert unwound is True


# --- risk batch adapter ----------------------------------------------------


async def test_scheduled_risk_batch_commits_its_scores(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    factories: Any,
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year, is_active=True)
    student = await factories.student(year)
    await factories.enrollment(student, offering)

    async def _one_target(*args: Any, **kwargs: Any) -> list[tuple[int, int, str]]:
        return [(student.id, offering.id, offering.semester)]

    monkeypatch.setattr(analytics_batch, "_load_active_targets", _one_target)
    _use_test_session(monkeypatch, test_db_session)

    summary = await run_scheduled_risk_batch(settings)

    assert summary["processed"] == 1

    await test_db_session.commit()
    rows = (await test_db_session.scalars(select(StudentRiskScore))).all()
    assert len(rows) == 1
    assert rows[0].student_id == student.id


async def test_scheduled_risk_batch_swallows_a_failure(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed batch must not escape and take the scheduler down with it."""

    async def _explode(*args: Any, **kwargs: Any) -> list[tuple[int, int, str]]:
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(analytics_batch, "_load_active_targets", _explode)
    _use_test_session(monkeypatch, test_db_session)

    with caplog.at_level("ERROR", logger="features.analytics.batch"):
        summary = await run_scheduled_risk_batch(settings)

    assert summary["processed"] == 0
    assert "Risk batch failed" in caplog.text
    assert scheduled_job_running(JOB_RISK_BATCH) is False


async def test_scheduled_risk_batch_warns_past_its_budget(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Over budget is reported, never enforced: partial results still count."""

    async def _one_target(*args: Any, **kwargs: Any) -> list[tuple[int, int, str]]:
        return [(1, 1, "2026-1")]

    monkeypatch.setattr(analytics_batch, "_load_active_targets", _one_target)

    async def _slow(*args: Any, **kwargs: Any) -> dict[str, int]:
        return {
            "processed": 1,
            "high": 0,
            "medium": 0,
            "low": 1,
            "duration_ms": RISK_BATCH_RUNTIME_BUDGET_MS + 1,
        }

    monkeypatch.setattr(analytics_batch, "run_risk_batch", _slow)
    _use_test_session(monkeypatch, test_db_session)

    with caplog.at_level("WARNING", logger="features.analytics.batch"):
        summary = await run_scheduled_risk_batch(settings)

    assert summary["processed"] == 1
    assert "exceeded its" in caplog.text


# --- backup adapter --------------------------------------------------------


def _backup_settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={
            "backup_storage_type": "local",
            "backup_local_dir": str(tmp_path),
            "backup_encryption_key": "test-key-0123456789abcdef",
        }
    )


def _completed_row(filename: str, moment: datetime) -> BackupLog:
    return BackupLog(
        filename=filename,
        kind=BackupKind.FULL.value,
        size_bytes=10,
        sha256="x" * 64,
        storage_backend=BackupStorage.LOCAL.value,
        encryption_key_version=1,
        started_at=moment,
        finished_at=moment,
        status=BackupStatus.COMPLETED.value,
        error=None,
    )


async def test_scheduled_backup_commits_its_log_row(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cfg = _backup_settings(settings, tmp_path)

    async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
        tmp_enc.write_bytes(b"encrypted-backup-bytes")

    monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)
    _use_test_session(monkeypatch, test_db_session)

    backup_id = await run_scheduled_backup(cfg)

    assert backup_id is not None

    await test_db_session.commit()
    row = await test_db_session.get(BackupLog, backup_id)
    assert row is not None
    assert row.status == BackupStatus.COMPLETED.value


async def test_scheduled_backup_skips_without_an_encryption_key(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No key means no pipeline, and no nightly row of noise in `backup_log`."""
    cfg = settings.model_copy(
        update={
            "backup_storage_type": "local",
            "backup_local_dir": str(tmp_path),
            "backup_encryption_key": "",
        }
    )

    async def _never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the pipeline must not run without a key")

    monkeypatch.setattr(SystemService, "_run_pipeline", _never)
    _use_test_session(monkeypatch, test_db_session)

    with caplog.at_level("CRITICAL", logger="features.system.service"):
        backup_id = await run_scheduled_backup(cfg)

    assert backup_id is None
    assert "BACKUP_ENCRYPTION_KEY is not set" in caplog.text

    await test_db_session.commit()
    rows = (await test_db_session.scalars(select(BackupLog))).all()
    assert rows == []


async def test_scheduled_backup_defers_to_a_running_backup(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A manual backup holding the lock wins; the cron run stands down."""
    cfg = _backup_settings(settings, tmp_path)
    _use_test_session(monkeypatch, test_db_session)

    async with system_service._BACKUP_LOCK:
        with caplog.at_level("WARNING", logger="features.system.service"):
            backup_id = await run_scheduled_backup(cfg)

    assert backup_id is None
    assert "already running" in caplog.text


async def test_scheduled_backup_swallows_a_pipeline_failure(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = _backup_settings(settings, tmp_path)

    async def _explode(self: SystemService, *, tmp_enc: Path) -> None:
        raise BackupFailedException("pg_dump missing")

    monkeypatch.setattr(SystemService, "_run_pipeline", _explode)
    _use_test_session(monkeypatch, test_db_session)

    with caplog.at_level("ERROR", logger="features.system.service"):
        backup_id = await run_scheduled_backup(cfg)

    assert backup_id is None
    assert "Scheduled backup failed" in caplog.text
    assert scheduled_job_running(JOB_BACKUP) is False


async def test_scheduled_backup_prunes_under_retention(
    settings: Settings,
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Retention runs inside the scheduled job, on the same transaction.

    Three rows are needed, not two: pruning never leaves fewer than two behind,
    so a lone stale row next to a single recent one is deliberately spared. The
    stale row is dated to a fixed day that is not the first of the month,
    because first-of-month rows are retained on the monthly rule instead.
    """
    cfg = _backup_settings(settings, tmp_path)
    stale = _completed_row(
        "backup_20200315_000000.sql.gz.enc",
        datetime(2020, 3, 15, 2, 0, tzinfo=timezone.utc),
    )
    recent = _completed_row(
        "backup_20260615_000000.sql.gz.enc",
        datetime.now(timezone.utc) - timedelta(days=2),
    )
    test_db_session.add_all([stale, recent])
    await test_db_session.flush()

    async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
        tmp_enc.write_bytes(b"encrypted-backup-bytes")

    monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)
    _use_test_session(monkeypatch, test_db_session)

    backup_id = await run_scheduled_backup(cfg)

    assert backup_id is not None

    await test_db_session.commit()
    filenames = (await test_db_session.scalars(select(BackupLog.filename))).all()
    assert stale.filename not in filenames
    # The two survivors are the recent row and the one this run just wrote.
    assert len(filenames) == 2
    assert recent.filename in filenames
