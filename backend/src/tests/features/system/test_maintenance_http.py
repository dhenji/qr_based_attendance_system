"""Force-sync and cleanup maintenance endpoints.

The flush run reconciles pending queue rows against the attendance rows
they mirror; the cleanup run prunes expired OTP codes and finished queue
rows. Both refuse to start while another exclusive job runs, and both
write one aggregate audit row per run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.scheduler import JOB_BACKUP, track

from shared.enums import AuditAction, AuditEntity, QueueStatus, UserRole

from features.auth.model import OtpCodes
from features.sync.model import SyncQueue
from features.system import service as system_service
from features.system.exceptions import MaintenanceBusyException
from features.system.model import AuditLog
from features.system.service import SystemService
from tests.conftest import Factories

FLUSH_ENDPOINT = "/api/admin/system/sync/flush"
CLEANUP_ENDPOINT = "/api/admin/system/cleanup"


async def _admin_headers(auth_headers: Any, factories: Factories) -> dict[str, str]:
    admin = await factories.user(role=UserRole.ADMIN.value)
    return await auth_headers(admin)


def _queue_payload(
    *, attendance_id: int, session_id: int, student_id: int
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "student_id": student_id,
        "attendance_id": attendance_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": None,
    }


async def _maintenance_rows(test_db_session: AsyncSession) -> list[AuditLog]:
    return list(
        (
            await test_db_session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == AuditEntity.MAINTENANCE)
                .order_by(AuditLog.id)
            )
        ).all()
    )


# --- flush ---------------------------------------------------------------


async def test_flush_empty_returns_zeros_and_audits(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(FLUSH_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "succeeded": 0, "failed": 0}

    (row,) = await _maintenance_rows(test_db_session)
    assert row.action == AuditAction.UPDATE
    assert row.entity_id is None
    assert row.new_value == {"processed": 0, "succeeded": 0, "failed": 0}
    assert row.performed_by is not None


async def test_flush_marks_landed_rows_done(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    stack = await factories.full_stack()
    record = await factories.attendance(stack["student"], stack["session"])
    queued = SyncQueue(
        record_data=_queue_payload(
            attendance_id=record.id,
            session_id=stack["session"].id,
            student_id=stack["student"].id,
        ),
        status=QueueStatus.PENDING.value,
    )
    test_db_session.add(queued)
    await test_db_session.flush()
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(FLUSH_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "succeeded": 1, "failed": 0}

    await test_db_session.refresh(queued)
    assert queued.status == QueueStatus.DONE.value

    settings = await api_client.get("/api/admin/system/settings", headers=headers)
    assert settings.json()["pending_sync_count"] == 0


async def test_flush_marks_orphan_rows_failed(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    queued = SyncQueue(
        record_data=_queue_payload(attendance_id=999999, session_id=1, student_id=1),
        status=QueueStatus.PENDING.value,
    )
    test_db_session.add(queued)
    await test_db_session.flush()
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(FLUSH_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "succeeded": 0, "failed": 1}

    await test_db_session.refresh(queued)
    assert queued.status == QueueStatus.FAILED.value
    assert queued.retry_count == 1


async def test_flush_marks_mismatched_rows_failed(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    stack = await factories.full_stack()
    record = await factories.attendance(stack["student"], stack["session"])
    queued = SyncQueue(
        record_data=_queue_payload(
            attendance_id=record.id,
            session_id=stack["session"].id,
            student_id=stack["student"].id + 99999,
        ),
        status=QueueStatus.PENDING.value,
    )
    test_db_session.add(queued)
    await test_db_session.flush()
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(FLUSH_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "succeeded": 0, "failed": 1}

    await test_db_session.refresh(queued)
    assert queued.status == QueueStatus.FAILED.value


async def test_flush_refuses_while_scheduled_job_tracked(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await test_db_session.commit()

    async with track(JOB_BACKUP):
        response = await api_client.post(FLUSH_ENDPOINT, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "maintenance_in_progress"


async def test_cleanup_refuses_while_backup_running(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    await test_db_session.commit()

    async with system_service._BACKUP_LOCK:
        response = await api_client.post(CLEANUP_ENDPOINT, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "maintenance_in_progress"


async def test_maintenance_refuses_concurrent_run(
    test_db_session: AsyncSession, settings: Settings
) -> None:
    assert system_service.is_maintenance_running() is False
    async with system_service._MAINTENANCE_LOCK:
        assert system_service.is_maintenance_running() is True
        with pytest.raises(MaintenanceBusyException):
            await SystemService(test_db_session, settings).flush_sync_queue()
        with pytest.raises(MaintenanceBusyException):
            await SystemService(test_db_session, settings).cleanup_expired()


# --- cleanup -------------------------------------------------------------


async def test_cleanup_prunes_expired_rows(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
    now: datetime,
) -> None:
    test_db_session.add_all(
        [
            OtpCodes(
                email="old@test.local",
                otp_hash="hash",
                expires_at=now + timedelta(minutes=5),
                created_at=now - timedelta(days=8),
            ),
            OtpCodes(
                email="recent@test.local",
                otp_hash="hash",
                expires_at=now + timedelta(minutes=5),
                created_at=now - timedelta(days=6),
            ),
            OtpCodes(
                email="fresh@test.local",
                otp_hash="hash",
                expires_at=now + timedelta(minutes=5),
                created_at=now,
            ),
            SyncQueue(
                record_data={},
                status=QueueStatus.DONE.value,
                created_at=now - timedelta(days=31),
            ),
            SyncQueue(
                record_data={},
                status=QueueStatus.FAILED.value,
                created_at=now - timedelta(days=31),
            ),
            SyncQueue(
                record_data={},
                status=QueueStatus.PENDING.value,
                created_at=now - timedelta(days=31),
            ),
            SyncQueue(
                record_data={},
                status=QueueStatus.DONE.value,
                created_at=now,
            ),
        ]
    )
    await test_db_session.flush()
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(CLEANUP_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"removed": 3}

    remaining_otps = sorted(
        row.email for row in (await test_db_session.scalars(select(OtpCodes))).all()
    )
    assert remaining_otps == ["fresh@test.local", "recent@test.local"]

    remaining_queue = sorted(
        row.status for row in (await test_db_session.scalars(select(SyncQueue))).all()
    )
    assert remaining_queue == [QueueStatus.DONE.value, QueueStatus.PENDING.value]

    (row,) = await _maintenance_rows(test_db_session)
    assert row.action == AuditAction.DELETE
    assert row.entity_id is None
    assert row.new_value == {"removed": 3, "otp_codes": 1, "sync_queue": 2}
    assert row.performed_by is not None


async def test_cleanup_empty_returns_zero_and_audits(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(CLEANUP_ENDPOINT, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"removed": 0}

    (row,) = await _maintenance_rows(test_db_session)
    assert row.action == AuditAction.DELETE
    assert row.new_value == {"removed": 0, "otp_codes": 0, "sync_queue": 0}


# --- authorization -------------------------------------------------------


async def test_maintenance_requires_admin(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    student_user = await factories.user()
    # Each rejected request rolls the seed back, so commit before the
    # first one or the second endpoint would see no user at all.
    await test_db_session.commit()
    headers = await auth_headers(student_user)

    for endpoint in (FLUSH_ENDPOINT, CLEANUP_ENDPOINT):
        response = await api_client.post(endpoint, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_maintenance_requires_auth(api_client: Any) -> None:
    assert (await api_client.post(FLUSH_ENDPOINT)).status_code == 401
    assert (await api_client.post(CLEANUP_ENDPOINT)).status_code == 401
