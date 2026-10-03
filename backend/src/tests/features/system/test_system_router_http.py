from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import DomainException
from features.sync.model import SyncQueue
from features.system.model import AppSetting, BackupLog
from features.system.service import SystemService
from shared.enums import BackupKind, BackupStatus, QueueStatus, UserRole
from tests.conftest import Factories


async def _admin_headers(auth_headers: Any, factories: Factories) -> dict[str, str]:
    admin = await factories.user(role=UserRole.ADMIN.value)
    return await auth_headers(admin)


async def test_settings_get_seeds_defaults(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get("/api/admin/system/settings", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["geofence_default_radius"] == 50
    assert body["present_window_default"] == 5
    assert body["late_window_default"] == 10
    assert body["backup_retention_daily"] == 30
    assert body["backup_retention_monthly"] == 12
    assert body["pending_sync_count"] == 0


async def test_settings_patch_persists(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.patch(
        "/api/admin/system/settings",
        json={"geofence_default_radius": 75, "backup_retention_daily": 45},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["geofence_default_radius"] == 75
    assert body["backup_retention_daily"] == 45
    assert body["present_window_default"] == 5

    stored = {
        row.key: row.value
        for row in (await test_db_session.scalars(select(AppSetting))).all()
    }
    assert stored["geofence_default_radius"] == "75"
    assert stored["backup_retention_daily"] == "45"


async def test_settings_patch_rejects_out_of_range(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.patch(
        "/api/admin/system/settings",
        json={"geofence_default_radius": 5000},
        headers=headers,
    )

    assert response.status_code == 422


async def test_settings_counts_pending_sync(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    test_db_session.add_all(
        [
            SyncQueue(record_data={}, status=QueueStatus.PENDING.value),
            SyncQueue(record_data={}, status=QueueStatus.PENDING.value),
            SyncQueue(record_data={}, status=QueueStatus.DONE.value),
        ]
    )
    await test_db_session.flush()

    response = await api_client.get("/api/admin/system/settings", headers=headers)

    assert response.status_code == 200
    assert response.json()["pending_sync_count"] == 2


async def test_settings_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    student_user = await factories.user()

    response = await api_client.get(
        "/api/admin/system/settings", headers=await auth_headers(student_user)
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_settings_requires_auth(api_client: Any) -> None:
    assert (await api_client.get("/api/admin/system/settings")).status_code == 401
    assert (
        await api_client.patch("/api/admin/system/settings", json={})
    ).status_code == 401


async def test_backups_list_starts_empty(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get("/api/admin/backups", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_trigger_lists_and_downloads_backup(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    settings: Settings,
    test_db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from main import app

    from api.deps import _get_system_service

    cfg = settings.model_copy(
        update={
            "backup_storage_type": "local",
            "backup_local_dir": str(tmp_path),
            "backup_encryption_key": "test-key-0123456789abcdef",
        }
    )

    async def _override_service() -> SystemService:
        return SystemService(test_db_session, cfg)

    app.dependency_overrides[_get_system_service] = _override_service
    try:
        headers = await _admin_headers(auth_headers, factories)

        async def _fake_pipeline(self: SystemService, *, tmp_enc: Path) -> None:
            tmp_enc.write_bytes(b"encrypted-backup-bytes")

        monkeypatch.setattr(SystemService, "_run_pipeline", _fake_pipeline)

        triggered = await api_client.post("/api/admin/backups", headers=headers)

        assert triggered.status_code == 202
        assert triggered.json()["status"] == "started"
        backup_id = triggered.json()["backup_id"]

        listed = await api_client.get("/api/admin/backups", headers=headers)

        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        (item,) = listed.json()["items"]
        assert item["id"] == backup_id
        assert item["status"] == BackupStatus.COMPLETED.value

        downloaded = await api_client.get(
            f"/api/admin/backups/{backup_id}/download", headers=headers
        )

        assert downloaded.status_code == 200
        assert downloaded.content == b"encrypted-backup-bytes"
        assert "attachment" in downloaded.headers["content-disposition"]
    finally:
        app.dependency_overrides.pop(_get_system_service, None)


async def test_download_unknown_backup_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.get(
        "/api/admin/backups/999999/download", headers=headers
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "backup_not_found"


async def test_backups_require_admin(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    student_user = await factories.user()
    await test_db_session.commit()
    headers = await auth_headers(student_user)

    assert (await api_client.get("/api/admin/backups", headers=headers)).status_code == 403
    assert (await api_client.post("/api/admin/backups", headers=headers)).status_code == 403


async def test_export_analytics_persists_csv_and_log(
    test_db_session: AsyncSession, settings: Settings, tmp_path: Path
) -> None:
    cfg = settings.model_copy(
        update={
            "backup_storage_type": "local",
            "backup_local_dir": str(tmp_path),
            "backup_encryption_key": "test-key-0123456789abcdef",
        }
    )

    content, row = await SystemService(test_db_session, cfg).export_analytics()

    assert content.splitlines()[0].startswith("course_id,")
    assert row.kind == BackupKind.ANALYTICS.value
    assert row.status == BackupStatus.COMPLETED.value
    assert (tmp_path / row.filename).read_bytes() == content.encode("utf-8")

    stored = (await test_db_session.scalars(select(BackupLog))).all()
    assert len(stored) == 1


async def test_export_analytics_rejects_pdf(
    test_db_session: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(DomainException) as exc_info:
        await SystemService(test_db_session, settings).export_analytics(format="pdf")

    assert exc_info.value.code == "validation_error"
