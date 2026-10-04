"""Database backup pipeline: dump, compress, encrypt, store, log, prune.

The pipeline produces full-database dumps of every table (nothing excluded
unless the operator opts out of the ephemeral ``otp_codes`` table):

1. ``pg_dump -Fc`` streams the database in custom format.
2. ``gzip`` compresses the stream (level from settings).
3. ``openssl enc -aes-256-gcm`` encrypts it with the configured key.
4. The encrypted blob plus a SHA-256 sidecar are written to the configured
   backend (local directory, or S3-compatible storage sharing the
   attachments bucket layout).
5. Every run is recorded in ``backup_log``: a ``started`` row first, then
   ``completed`` (or ``failed`` with the error) — a run never leaves a
   ``started`` row open.
6. Retention pruning keeps the last 30 daily plus 12 monthly backups
   (first-of-month rows), and never drops below two remaining rows.

Exports reuse this pipeline with ``kind="analytics"``; the scheduler and
the maintenance endpoints consume ``is_backup_running`` for their
concurrency guard.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
from core.exceptions import DomainException
from core.scheduler import JOB_BACKUP, scheduled_job_running, track
from features.attendance.model import Attendance
from features.auth.model import OtpCodes
from features.system.constants import (
    ERROR_MAX_CHARS,
    EXPORT_FILENAME_PREFIX,
    GZIP_LEVEL_MAX,
    GZIP_LEVEL_MIN,
    LOCAL_FILE_MODE,
    OTP_RETENTION_DAYS,
    READ_CHUNK_BYTES,
    SETTING_GEOFENCE_RADIUS,
    SETTING_LATE_WINDOW,
    SETTING_PRESENT_WINDOW,
    SETTING_RETENTION_DAILY,
    SETTING_RETENTION_MONTHLY,
    S3_PREFIX_FALLBACK,
    SIDECAR_SUFFIX,
    STDERR_TAIL_CHARS,
    STRUCTURAL_ENTITY_TYPES,
    SYNC_FINISHED_RETENTION_DAYS,
    WORK_DUMP_NAME,
    WORK_GZ_NAME,
)
from features.system.exceptions import (
    AuditDateRangeInvalidException,
    AuditFilterInvalidException,
    BackupFailedException,
    BackupInProgressException,
    BackupNotFoundException,
    BackupStorageUnconfiguredException,
    MaintenanceBusyException,
)
from features.system.model import AppSetting, AuditLog, BackupLog
from features.system.schema import (
    AcademicStructureListResponse,
    AcademicStructureRead,
    AuditLogListResponse,
    AuditLogRead,
    BackupListResponse,
    BackupRead,
    CleanupResponse,
    SyncFlushResponse,
    SystemSettingsRead,
    SystemSettingsUpdate,
)
from features.sync.model import SyncQueue
from shared.audit import record_audit
from shared.datetimes import ensure_aware
from shared.enums import (
    AuditAction,
    AuditEntity,
    BackupKind,
    BackupStatus,
    BackupStorage,
    QueueStatus,
)
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.query import apply_if
from shared.storage import StorageUnconfiguredException, s3_client

logger = logging.getLogger(__name__)

_BACKUP_LOCK = asyncio.Lock()

_MAINTENANCE_LOCK = asyncio.Lock()


def is_backup_running() -> bool:
    """Whether a backup currently holds the in-process lock."""
    return _BACKUP_LOCK.locked()


def is_maintenance_running() -> bool:
    """Whether a maintenance run currently holds the in-process lock."""
    return _MAINTENANCE_LOCK.locked()


def maintenance_busy() -> bool:
    """Whether a maintenance run must refuse to start.

    Its own lock plus every exclusive job it must not overlap: a
    scheduled batch (seen through the scheduler tracker) or a backup
    (seen through its lock, which also covers manual triggers).
    """
    return (
        _MAINTENANCE_LOCK.locked()
        or scheduled_job_running()
        or is_backup_running()
    )


def _queue_id(payload: dict[str, Any], key: str) -> int:
    """One id out of a queue payload, or raise when it is missing or
    unparseable. The caller maps both failures to a failed entry."""
    raw = payload.get(key)
    if raw is None:
        raise TypeError(f"sync_queue payload has no {key!r}")
    return int(raw)


def build_backup_filename(*, now: datetime | None = None) -> str:
    """Timestamped blob name shared by the local and S3 layouts."""
    stamp = ensure_aware(now) if now is not None else datetime.now(timezone.utc)
    return f"backup_{stamp:%Y%m%d_%H%M%S}.sql.gz.enc"


def libpq_url(database_url: str) -> str:
    """Translate the SQLAlchemy URL into one ``pg_dump`` accepts."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def build_pg_dump_args(*, settings: Settings) -> list[str]:
    """Dump flags: custom format, no ownership/privilege statements, plus the
    opt-in exclusion of the ephemeral OTP table."""
    args = [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-d",
        libpq_url(settings.database_url),
    ]
    if settings.backup_exclude_otp_codes:
        args.append("--exclude-table-data=otp_codes")
    return args


def sha256_file(path: Path) -> str:
    """Hex digest of the encrypted blob for the sidecar and the log row."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_monthly_anchor(moment: datetime) -> bool:
    """A monthly backup is the first backup of its month."""
    return ensure_aware(moment).day == 1


def select_prune_candidates(
    rows: Sequence[BackupLog],
    *,
    now: datetime,
    daily: int,
    monthly: int,
) -> list[BackupLog]:
    """Apply the retention rule to completed rows.

    Daily rows older than ``daily`` days go, except first-of-month rows,
    which survive ``monthly`` months instead. Only completed rows with a
    finish timestamp are eligible, oldest first, and pruning never leaves
    fewer than two rows behind.
    """
    moment = ensure_aware(now)
    doomed: list[BackupLog] = []
    for row in rows:
        if row.status != BackupStatus.COMPLETED.value or row.finished_at is None:
            continue
        finished = ensure_aware(row.finished_at)
        if is_monthly_anchor(finished):
            age_months = (moment.year - finished.year) * 12 + (
                moment.month - finished.month
            )
            if age_months > monthly:
                doomed.append(row)
        elif (moment - finished).days > daily:
            doomed.append(row)
    doomed.sort(key=lambda row: ensure_aware(row.finished_at))  # type: ignore[arg-type]
    spare = len(rows) - len(doomed)
    if spare < 2:
        doomed = doomed[: max(len(rows) - 2, 0)]
    return doomed


class SystemService:
    """Database backups and retention pruning.

    The class form follows the sanctioned non-CRUD exception (session plus
    settings read by every method): both handles are built per request in
    `__init__` and used throughout. Only `flush()` is used here;
    commit/rollback stays in the request dependency. The concurrency lock is
    process-global (module level) so every instance — request handler,
    scheduler job — sees the same guard.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def run_backup(
        self,
        *,
        kind: str = BackupKind.FULL.value,
        now: datetime | None = None,
        actor_id: int | None = None,
    ) -> BackupLog:
        """Run the full pipeline and return the finished log row.

        Inserts the ``started`` row first so a later listing can poll it, marks
        the row ``completed`` with size/hash/backend on success or ``failed``
        with the error on any failure, then prunes. Refuses to run while
        another backup holds the in-process lock.

        `actor_id` is the admin who asked for the run, or None for the nightly
        cron. `BackupLog` already records the operational outcome; the audit
        row records who asked and how it ended, which is what makes an
        unprompted export visible.
        """
        if kind not in (BackupKind.FULL.value, BackupKind.ANALYTICS.value):
            raise BackupFailedException(f"Unknown backup kind {kind!r}")
        if self._settings.backup_storage_type not in (
            BackupStorage.LOCAL.value,
            BackupStorage.S3.value,
        ):
            raise BackupStorageUnconfiguredException(
                f"BACKUP_STORAGE_TYPE={self._settings.backup_storage_type!r} is not "
                "a supported storage backend"
            )
        if _BACKUP_LOCK.locked():
            raise BackupInProgressException()

        async with _BACKUP_LOCK:
            started_at = (
                ensure_aware(now) if now is not None else datetime.now(timezone.utc)
            )
            filename = build_backup_filename(now=started_at)
            row = BackupLog(
                filename=filename,
                kind=kind,
                size_bytes=0,
                sha256="",
                storage_backend=self._settings.backup_storage_type,
                encryption_key_version=int(
                    self._settings.backup_encryption_key_version
                ),
                started_at=started_at,
                finished_at=None,
                status=BackupStatus.STARTED.value,
                error=None,
            )
            self._session.add(row)
            await self._session.flush()

            with tempfile.TemporaryDirectory(prefix="backup_") as tmpdir:
                tmp_enc = Path(tmpdir) / filename
                try:
                    await self._run_pipeline(tmp_enc=tmp_enc)
                    digest = sha256_file(tmp_enc)
                    match self._settings.backup_storage_type:
                        case BackupStorage.S3.value:
                            self._store_s3(tmp_enc=tmp_enc, filename=filename)
                        case _:
                            self._store_local(
                                tmp_enc=tmp_enc, digest=digest, filename=filename
                            )
                except Exception as exc:  # noqa: BLE001 - failures land on the row
                    row.status = BackupStatus.FAILED.value
                    row.finished_at = datetime.now(timezone.utc)
                    row.error = str(exc)[-ERROR_MAX_CHARS:]
                    await self._session.flush()
                    raise

                row.size_bytes = tmp_enc.stat().st_size
                row.sha256 = digest
                row.finished_at = datetime.now(timezone.utc)
                row.status = BackupStatus.COMPLETED.value
                await self._session.flush()

            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.CREATE,
                entity_type=AuditEntity.BACKUP,
                entity_id=row.id,
                new_value={
                    "kind": row.kind,
                    "filename": row.filename,
                    "status": row.status,
                    "size_bytes": row.size_bytes,
                    "storage_backend": row.storage_backend,
                    "sha256": row.sha256,
                },
            )

            await self.prune_retention()
            return row

    async def prune_retention(self) -> dict[str, int]:
        """Delete expired blobs and their log rows; returns what was removed."""
        rows = list(
            (
                await self._session.scalars(
                    select(BackupLog).order_by(BackupLog.finished_at)
                )
            ).all()
        )
        doomed = select_prune_candidates(
            rows,
            now=datetime.now(timezone.utc),
            daily=int(self._settings.backup_retention_daily),
            monthly=int(self._settings.backup_retention_monthly),
        )
        for row in doomed:
            await self._delete_stored(filename=row.filename)
            await self._session.delete(row)
        if doomed:
            await self._session.flush()
        return {"removed": len(doomed)}

    async def flush_sync_queue(
        self, actor_id: int | None = None
    ) -> SyncFlushResponse:
        """Reconcile every pending offline-sync row and report the outcome.

        Each queued entry mirrors a scan that already landed in
        `attendance_records`: the payload carries ids only, no scan
        evidence, so a run cannot resubmit the scan — and must not, since
        the duplicate guard would reject it. Instead the run confirms
        each entry landed on the row it names: an id match on both sides
        marks the entry done, anything else (orphan, mismatch, payload
        that no longer parses) marks it failed with another retry
        counted. One bad entry never aborts the run. Refuses to start
        while another exclusive job runs.
        """
        if maintenance_busy():
            raise MaintenanceBusyException()
        async with _MAINTENANCE_LOCK:
            queued = list(
                (
                    await self._session.scalars(
                        select(SyncQueue)
                        .where(SyncQueue.status == QueueStatus.PENDING.value)
                        .order_by(SyncQueue.id)
                    )
                ).all()
            )
            succeeded = 0
            for row in queued:
                if await self._reconcile_sync_row(row):
                    row.status = QueueStatus.DONE.value
                    succeeded += 1
                else:
                    row.status = QueueStatus.FAILED.value
                    row.retry_count = (row.retry_count or 0) + 1
            failed = len(queued) - succeeded
            if queued:
                await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.UPDATE,
                entity_type=AuditEntity.MAINTENANCE,
                entity_id=None,
                new_value={
                    "processed": len(queued),
                    "succeeded": succeeded,
                    "failed": failed,
                },
            )
            return SyncFlushResponse(
                processed=len(queued), succeeded=succeeded, failed=failed
            )

    async def _reconcile_sync_row(self, row: SyncQueue) -> bool:
        """True when the queued entry names the attendance row it landed on.

        Ids only, never relationships: the queue row carries no foreign
        keys, so there is nothing to join on, and the attendance row is
        fetched by primary key. A row deleted out from under its queue
        entry reconciles as failed rather than raising, so the run keeps
        going.
        """
        payload = row.record_data
        if not isinstance(payload, dict):
            return False
        try:
            attendance_id = _queue_id(payload, "attendance_id")
            session_id = _queue_id(payload, "session_id")
            student_id = _queue_id(payload, "student_id")
        except (TypeError, ValueError):
            return False
        record = await self._session.get(Attendance, attendance_id)
        if record is None:
            return False
        return (
            record.session_id == session_id
            and record.student_id == student_id
        )

    async def cleanup_expired(
        self, actor_id: int | None = None
    ) -> CleanupResponse:
        """Delete expired login artifacts and finished sync rows.

        OTP codes older than `OTP_RETENTION_DAYS` and finished (`done`
        or `failed`) sync-queue rows older than
        `SYNC_FINISHED_RETENTION_DAYS`, both measured on `created_at`.
        Pending rows are never touched no matter their age: only the
        flush run may resolve those. One audit row carries the per-table
        counts; the response reports the summed total. Refuses to start
        while another exclusive job runs.
        """
        if maintenance_busy():
            raise MaintenanceBusyException()
        async with _MAINTENANCE_LOCK:
            now = datetime.now(timezone.utc)
            old_otps = list(
                (
                    await self._session.scalars(
                        select(OtpCodes).where(
                            OtpCodes.created_at
                            < now - timedelta(days=OTP_RETENTION_DAYS)
                        )
                    )
                ).all()
            )
            finished_queue = list(
                (
                    await self._session.scalars(
                        select(SyncQueue).where(
                            SyncQueue.status.in_(
                                [
                                    QueueStatus.DONE.value,
                                    QueueStatus.FAILED.value,
                                ]
                            ),
                            SyncQueue.created_at
                            < now
                            - timedelta(days=SYNC_FINISHED_RETENTION_DAYS),
                        )
                    )
                ).all()
            )
            for row in (*old_otps, *finished_queue):
                await self._session.delete(row)
            if old_otps or finished_queue:
                await self._session.flush()
            removed = len(old_otps) + len(finished_queue)
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.DELETE,
                entity_type=AuditEntity.MAINTENANCE,
                entity_id=None,
                new_value={
                    "removed": removed,
                    "otp_codes": len(old_otps),
                    "sync_queue": len(finished_queue),
                },
            )
            return CleanupResponse(removed=removed)

    def _setting_default(self, key: str) -> int:
        """Env default behind one settings key."""
        settings = self._settings
        match key:
            case _ if key == SETTING_GEOFENCE_RADIUS:
                return int(settings.default_geofence_radius_meters)
            case _ if key == SETTING_PRESENT_WINDOW:
                return int(settings.default_present_window_minutes)
            case _ if key == SETTING_LATE_WINDOW:
                return int(settings.default_late_window_minutes)
            case _ if key == SETTING_RETENTION_DAILY:
                return int(settings.backup_retention_daily)
            case _:
                return int(settings.backup_retention_monthly)

    async def _stored_settings(self) -> dict[str, int]:
        """Current settings values, seeding missing rows from env defaults."""
        keys = (
            SETTING_GEOFENCE_RADIUS,
            SETTING_PRESENT_WINDOW,
            SETTING_LATE_WINDOW,
            SETTING_RETENTION_DAILY,
            SETTING_RETENTION_MONTHLY,
        )
        rows = (
            await self._session.scalars(
                select(AppSetting).where(AppSetting.key.in_(keys))
            )
        ).all()
        stored: dict[str, str] = {row.key: row.value for row in rows}
        resolved: dict[str, int] = {}
        for key in keys:
            raw = stored.get(key)
            try:
                resolved[key] = int(raw) if raw is not None else self._setting_default(key)
            except (TypeError, ValueError):
                resolved[key] = self._setting_default(key)
            if key not in stored:
                self._session.add(
                    AppSetting(key=key, value=str(resolved[key]))
                )
        if any(key not in stored for key in keys):
            await self._session.flush()
        return resolved

    async def pending_sync_total(self) -> int:
        """Unprocessed offline-sync rows backing the maintenance line.

        Public because the admin dashboard needs the count on its own. Note that
        `get_system_settings` must NOT be reused for that: it calls
        `_stored_settings`, which INSERTs missing `AppSetting` rows and flushes,
        turning a dashboard GET into a write.
        """
        total = await self._session.scalar(
            select(func.count(SyncQueue.id)).where(
                SyncQueue.status == QueueStatus.PENDING.value
            )
        )
        return int(total or 0)

    async def get_system_settings(self) -> SystemSettingsRead:
        """Persisted tunables plus the live pending-sync count."""
        values = await self._stored_settings()
        return SystemSettingsRead(
            geofence_default_radius=values[SETTING_GEOFENCE_RADIUS],
            present_window_default=values[SETTING_PRESENT_WINDOW],
            late_window_default=values[SETTING_LATE_WINDOW],
            backup_retention_daily=values[SETTING_RETENTION_DAILY],
            backup_retention_monthly=values[SETTING_RETENTION_MONTHLY],
            pending_sync_count=await self.pending_sync_total(),
        )

    async def update_system_settings(
        self, patch: SystemSettingsUpdate, actor_id: int | None = None
    ) -> SystemSettingsRead:
        """Persist the provided fields, then return the full current view.

        Geofence radius and the present/late windows decide who counts as on
        time and who counts as inside the classroom, so every change is
        recorded with its previous value. A key that does not exist yet has no
        previous value: `old_value` is then null on that field.
        """
        updates = patch.model_dump(exclude_none=True)
        changes: dict[str, dict[str, Any]] = {}

        for key, field in (
            (SETTING_GEOFENCE_RADIUS, "geofence_default_radius"),
            (SETTING_PRESENT_WINDOW, "present_window_default"),
            (SETTING_LATE_WINDOW, "late_window_default"),
            (SETTING_RETENTION_DAILY, "backup_retention_daily"),
            (SETTING_RETENTION_MONTHLY, "backup_retention_monthly"),
        ):
            if field not in updates:
                continue
            row = await self._session.scalar(
                select(AppSetting).where(AppSetting.key == key)
            )
            # Read the old value before the write; after it the row no longer
            # distinguishes what was there from what was just put there.
            previous: Any = row.value if row is not None else None

            if row is None:
                self._session.add(AppSetting(key=key, value=str(updates[field])))
            else:
                row.value = str(updates[field])

            changes[field] = {"old": previous, "new": str(updates[field])}

        await self._session.flush()

        if changes:
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.UPDATE,
                entity_type=AuditEntity.APP_SETTING,
                entity_id=None,
                old_value={name: c["old"] for name, c in changes.items()},
                new_value={name: c["new"] for name, c in changes.items()},
            )

        return await self.get_system_settings()

    async def list_backups(self, *, page: int = DEFAULT_PAGE, size: int = DEFAULT_PAGE_SIZE) -> BackupListResponse:
        """Newest-first backup log page."""
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)
        total = await self._session.scalar(select(func.count(BackupLog.id)))
        rows = (
            await self._session.scalars(
                select(BackupLog)
                .order_by(BackupLog.started_at.desc(), BackupLog.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
        return BackupListResponse(
            items=[BackupRead.model_validate(row) for row in rows],
            total=int(total or 0),
            page=page,
            size=size,
        )

    async def list_academic_structure(
        self, *, page: int = DEFAULT_PAGE, size: int = DEFAULT_PAGE_SIZE
    ) -> AcademicStructureListResponse:
        """Newest-first page of structural audit rows."""
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)
        scope = select(AuditLog).where(AuditLog.entity_type.in_(STRUCTURAL_ENTITY_TYPES))
        total = await self._session.scalar(
            select(func.count()).select_from(scope.subquery())
        )
        rows = (
            await self._session.scalars(
                scope.order_by(AuditLog.performed_at.desc(), AuditLog.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
        return AcademicStructureListResponse(
            items=[AcademicStructureRead.model_validate(row) for row in rows],
            total=int(total or 0),
            page=page,
            size=size,
        )

    async def list_audit_logs(
        self,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        performed_by: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> AuditLogListResponse:
        """Newest-first page of the whole audit trail, optionally filtered.

        Unlike `list_academic_structure`, which is pinned to the four
        structural entity types, this endpoint spans every `entity_type` the
        writer records — including the two that carry no single-column id
        (`course_professor` and the batch-level `import` / settings rows).

        `entity_type` and `action` are validated against the recorded
        vocabulary. They are free-form columns, so an unrecognised value would
        otherwise return an empty page that reads as "nothing happened".

        `date_from` is inclusive from 00:00 UTC and `date_to` inclusive to the
        end of that day, so `date_from == date_to` selects exactly one day.
        """
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)

        # A blank query parameter is "no filter", not an unknown value: a client
        # that sends its form fields verbatim sends `?entity_type=` for an unset
        # dropdown, and rejecting that would be a 422 on a request that asked for
        # nothing in particular.
        entity_type = entity_type or None
        action = action or None

        # `in` against the StrEnum compares by value, so a plain query string
        # matches the member without unwrapping it first.
        if entity_type is not None and entity_type not in AuditEntity:
            raise AuditFilterInvalidException("entity_type", entity_type)

        if action is not None and action not in AuditAction:
            raise AuditFilterInvalidException("action", action)

        if date_from is not None and date_to is not None and date_from > date_to:
            raise AuditDateRangeInvalidException()

        scope = select(AuditLog)

        for value, column in (
            (entity_type, AuditLog.entity_type),
            (action, AuditLog.action),
        ):
            scope = apply_if(scope, value, lambda v, c=column: c == v)

        scope = apply_if(
            scope, performed_by, lambda v: AuditLog.performed_by == v
        )

        # Half-open on the upper bound so `date_to` covers the whole day.
        scope = apply_if(
            scope,
            date_from,
            lambda v: AuditLog.performed_at
            >= datetime.combine(v, dt_time.min, tzinfo=timezone.utc),
        )
        scope = apply_if(
            scope,
            date_to,
            lambda v: AuditLog.performed_at
            < datetime.combine(
                v + timedelta(days=1), dt_time.min, tzinfo=timezone.utc
            ),
        )

        total = await self._session.scalar(
            select(func.count()).select_from(scope.subquery())
        )
        rows = (
            await self._session.scalars(
                scope.order_by(AuditLog.performed_at.desc(), AuditLog.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return AuditLogListResponse(
            items=[AuditLogRead.model_validate(row) for row in rows],
            total=int(total or 0),
            page=page,
            size=size,
        )

    async def get_backup(self, backup_id: int) -> BackupLog:
        """One log row or a 404."""
        row = await self._session.get(BackupLog, backup_id)
        if row is None:
            raise BackupNotFoundException(backup_id)
        return row

    async def read_backup_bytes(self, backup_id: int) -> tuple[BackupLog, bytes]:
        """Stored blob for a completed backup."""
        row = await self.get_backup(backup_id)
        if row.storage_backend == BackupStorage.S3.value:
            return row, await self._read_s3_bytes(
                backup_id=backup_id, filename=row.filename
            )
        if row.status != BackupStatus.COMPLETED.value:
            raise BackupNotFoundException(backup_id)
        target = Path(self._settings.backup_local_dir) / row.filename
        try:
            return row, target.read_bytes()
        except OSError:
            raise BackupNotFoundException(backup_id)

    async def _read_s3_bytes(self, *, backup_id: int, filename: str) -> bytes:
        settings = self._settings
        prefix = (settings.backup_s3_prefix or S3_PREFIX_FALLBACK).rstrip("/")
        try:
            response = s3_client(settings).get_object(
                Bucket=settings.backup_s3_bucket, Key=f"{prefix}/{filename}"
            )
        except StorageUnconfiguredException:
            raise
        except Exception as exc:  # noqa: BLE001 - missing object reads as 404
            raise BackupNotFoundException(backup_id) from exc
        body = response.get("Body")
        return body.read() if hasattr(body, "read") else bytes(body)

    def build_export_filename(self, *, now: datetime | None = None) -> str:
        """Timestamped object name for a persisted analytics CSV."""
        stamp = ensure_aware(now) if now is not None else datetime.now(timezone.utc)
        return f"{EXPORT_FILENAME_PREFIX}{stamp:%Y%m%d_%H%M%S}.csv"

    async def export_analytics(
        self,
        *,
        format: str = "csv",
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        course_ids: Sequence[int] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        now: datetime | None = None,
    ) -> tuple[str, BackupLog]:
        """Render the per-course comparison as CSV and persist it.

        Row-shaping stays in the analytics slice; this method stores the
        rendered text through the backup backend and records a
        ``kind="analytics"`` log row so generated files are auditable.
        Only CSV is built: no PDF writer is installed.
        """
        if format != "csv":
            raise DomainException(
                "PDF export is not available yet; request format csv",
                code="validation_error",
                field="format",
            )
        from features.analytics.service import AnalyticsService

        content: str = await AnalyticsService(self._session).export_course_comparison(
            format="csv",
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_ids=course_ids,
            date_from=date_from,
            date_to=date_to,
        )
        payload = content.encode("utf-8")
        if self._settings.backup_storage_type not in (
            BackupStorage.LOCAL.value,
            BackupStorage.S3.value,
        ):
            raise BackupStorageUnconfiguredException(
                f"BACKUP_STORAGE_TYPE={self._settings.backup_storage_type!r} is not "
                "a supported storage backend"
            )
        filename = self.build_export_filename(now=now)
        digest = hashlib.sha256(payload).hexdigest()
        match self._settings.backup_storage_type:
            case BackupStorage.S3.value:
                s3_client(self._settings).put_object(
                    Bucket=self._settings.backup_s3_bucket,
                    Key=f"{(self._settings.backup_s3_prefix or S3_PREFIX_FALLBACK).rstrip('/')}/{filename}",
                    Body=payload,
                    ContentType="text/csv",
                )
            case _:
                target_dir = Path(self._settings.backup_local_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / filename
                target.write_bytes(payload)
                target.chmod(LOCAL_FILE_MODE)
        moment = ensure_aware(now) if now is not None else datetime.now(timezone.utc)
        row = BackupLog(
            filename=filename,
            kind=BackupKind.ANALYTICS.value,
            size_bytes=len(payload),
            sha256=digest,
            storage_backend=self._settings.backup_storage_type,
            encryption_key_version=int(self._settings.backup_encryption_key_version),
            started_at=moment,
            finished_at=moment,
            status=BackupStatus.COMPLETED.value,
            error=None,
        )
        self._session.add(row)
        await self._session.flush()
        return content, row

    async def _run_stage(
        self,
        args: list[str],
        *,
        name: str,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Run one pipeline stage with file-backed stdio and raise on failure."""
        stdin_handle = open(stdin_path, "rb") if stdin_path is not None else None
        stdout_handle = open(stdout_path, "wb") if stdout_path is not None else None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=stdin_handle,
                stdout=stdout_handle,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            _, err = await proc.communicate()
        finally:
            if stdin_handle is not None:
                stdin_handle.close()
            if stdout_handle is not None:
                stdout_handle.close()
        if proc.returncode != 0:
            detail = (err or b"").decode(errors="replace")[-STDERR_TAIL_CHARS:]
            raise BackupFailedException(f"{name} exited {proc.returncode}: {detail}")

    async def _run_pipeline(self, *, tmp_enc: Path) -> None:
        """Stream ``pg_dump | gzip | openssl enc`` into ``tmp_enc`` via work files.

        Stages communicate through files in the same temp directory rather than
        pipes, so a large database is never buffered in memory.
        """
        settings = self._settings
        if not settings.backup_encryption_key:
            raise BackupStorageUnconfiguredException("BACKUP_ENCRYPTION_KEY is not set")
        level = min(
            max(int(settings.backup_compression_level or 6), GZIP_LEVEL_MIN),
            GZIP_LEVEL_MAX,
        )
        workdir = tmp_enc.parent
        dump_path = workdir / WORK_DUMP_NAME
        gz_path = workdir / WORK_GZ_NAME
        enc_env = {
            **os.environ,
            "BACKUP_ENCRYPTION_KEY": settings.backup_encryption_key,
        }
        try:
            await self._run_stage(
                build_pg_dump_args(settings=settings),
                name="pg_dump",
                stdout_path=dump_path,
            )
            await self._run_stage(
                ["gzip", f"-{level}", "-c"],
                name="gzip",
                stdin_path=dump_path,
                stdout_path=gz_path,
            )
            await self._run_stage(
                [
                    "openssl",
                    "enc",
                    "-aes-256-gcm",
                    "-salt",
                    "-pbkdf2",
                    "-in",
                    str(gz_path),
                    "-out",
                    str(tmp_enc),
                    "-pass",
                    "env:BACKUP_ENCRYPTION_KEY",
                ],
                name="openssl",
                env=enc_env,
            )
        except FileNotFoundError as exc:
            raise BackupFailedException(f"Backup tool missing: {exc.filename}") from exc
        finally:
            for path in (dump_path, gz_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove work file %s", path)

    def _store_local(self, *, tmp_enc: Path, digest: str, filename: str) -> None:
        """Copy the blob and its sidecar into the local directory (owner-only)."""
        target_dir = Path(self._settings.backup_local_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        sidecar = target.with_suffix(target.suffix + SIDECAR_SUFFIX)
        target.write_bytes(tmp_enc.read_bytes())
        sidecar.write_text(f"{digest}  {filename}\n")
        target.chmod(LOCAL_FILE_MODE)

    def _store_s3(self, *, tmp_enc: Path, filename: str) -> None:
        """Upload the blob under the timestamped prefix of the shared bucket."""
        settings = self._settings
        prefix = (settings.backup_s3_prefix or S3_PREFIX_FALLBACK).rstrip("/")
        s3_client(settings).put_object(
            Bucket=settings.backup_s3_bucket,
            Key=f"{prefix}/{filename}",
            Body=tmp_enc.read_bytes(),
        )

    async def _delete_stored(self, *, filename: str) -> None:
        """Remove one pruned blob (and its local sidecar). Best-effort: prune
        failures are logged, and the log row is still deleted."""
        settings = self._settings
        match settings.backup_storage_type:
            case BackupStorage.S3.value:
                prefix = (settings.backup_s3_prefix or S3_PREFIX_FALLBACK).rstrip("/")
                try:
                    client = s3_client(settings)
                    client.delete_object(
                        Bucket=settings.backup_s3_bucket, Key=f"{prefix}/{filename}"
                    )
                except StorageUnconfiguredException:
                    logger.warning(
                        "S3 prune skipped for %s: backend unconfigured", filename
                    )
                except Exception:  # noqa: BLE001 - prune must not fail
                    logger.warning("S3 prune delete failed for %s", filename)
                return
            case _:
                target = Path(settings.backup_local_dir) / filename
                sidecar = target.with_suffix(target.suffix + SIDECAR_SUFFIX)
                for path in (target, sidecar):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Local prune delete failed for %s", path)


async def run_scheduled_backup(settings: Settings | None = None) -> int | None:
    """Cron entry point: run one full backup and commit; None when skipped.

    Same reasoning as the risk batch for owning the transaction:
    `SystemService.run_backup` only `flush()`es, relying on the request
    dependency to commit, so a cron run has to commit the `backup_log` row
    itself or lose it.

    The unconfigured-key preflight is the reason this is a wrapper rather than
    a call to `run_backup`. Without an encryption key the pipeline cannot
    succeed, and letting it fail would write a `failed` row every night - the
    admin Backup panel would fill with failures nobody caused and the real ones
    would be lost in the noise. Skipping before touching the database keeps the
    failure visible as one CRITICAL log line instead. `run_backup` itself is
    unchanged, so a manual trigger still fails loudly on the row.

    Returns the new backup id, or None when the run was skipped.
    """
    cfg = settings or get_settings()
    if not cfg.backup_encryption_key:
        logger.critical(
            "Scheduled backup skipped: BACKUP_ENCRYPTION_KEY is not set"
        )
        return None

    started = time.perf_counter()
    logger.info("Scheduled backup started")
    async with track(JOB_BACKUP), database.get_session() as session:
        service = SystemService(session, cfg)
        try:
            # `actor_id` stays None: a cron run has no authenticated actor, and
            # the audit row rides this wrapper's own commit the same way the
            # `backup_log` row does.
            row = await service.run_backup(kind=BackupKind.FULL.value)
            await session.commit()
        except BackupInProgressException:
            await session.rollback()
            logger.warning(
                "Scheduled backup skipped: a backup is already running"
            )
            return None
        except Exception:
            await session.rollback()
            logger.exception("Scheduled backup failed")
            return None

    logger.info(
        "Scheduled backup completed: %s (%d bytes in %.1fs)",
        row.filename,
        row.size_bytes,
        time.perf_counter() - started,
    )
    return row.id
