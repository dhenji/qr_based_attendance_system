from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Response, status

from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

from api.deps import AdminUser, SystemServiceDep
from features.system.constants import (
    ACTION_MAX_LENGTH,
    ACTOR_MAX_LENGTH,
    ENTITY_TYPE_MAX_LENGTH,
)
from features.system.schema import (
    AcademicStructureListResponse,
    AuditLogListResponse,
    BackupListResponse,
    BackupTriggerResponse,
    CleanupResponse,
    SyncFlushResponse,
    SystemSettingsRead,
    SystemSettingsUpdate,
)

# This module owns /admin/system/*, /admin/backups/* and /admin/audit-logs
# ONLY. All three paths are unique across the mounted admin routers, so one
# router covers the slice.
router = APIRouter(prefix="/admin")


@router.get(
    "/system/settings",
    response_model=SystemSettingsRead,
    summary="Read persisted system settings",
)
async def get_system_settings(
    _: AdminUser,
    service: SystemServiceDep,
) -> SystemSettingsRead:
    return await service.get_system_settings()


@router.patch(
    "/system/settings",
    response_model=SystemSettingsRead,
    summary="Update persisted system settings",
)
async def update_system_settings(
    patch: SystemSettingsUpdate,
    user: AdminUser,
    service: SystemServiceDep,
) -> SystemSettingsRead:
    return await service.update_system_settings(patch, actor_id=user.id)


@router.get(
    "/system/academic-structure",
    response_model=AcademicStructureListResponse,
    summary="List structural changes (program/year/course/offering audit)",
)
async def list_academic_structure(
    _: AdminUser,
    service: SystemServiceDep,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> AcademicStructureListResponse:
    return await service.list_academic_structure(page=page, size=size)


@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    summary="List the audit trail (filterable, paginated)",
)
async def list_audit_logs(
    _: AdminUser,
    service: SystemServiceDep,
    entity_type: str | None = Query(default=None, max_length=ENTITY_TYPE_MAX_LENGTH),
    action: str | None = Query(default=None, max_length=ACTION_MAX_LENGTH),
    performed_by: int | None = Query(default=None, ge=1),
    actor: str | None = Query(default=None, max_length=ACTOR_MAX_LENGTH),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: Literal["time", "actor", "action"] = Query(default="time"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> AuditLogListResponse:
    return await service.list_audit_logs(
        entity_type=entity_type,
        action=action,
        performed_by=performed_by,
        actor=actor,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        size=size,
    )


@router.get(
    "/backups",
    response_model=BackupListResponse,
    summary="List backup log entries, newest first",
)
async def list_backups(
    _: AdminUser,
    service: SystemServiceDep,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> BackupListResponse:
    return await service.list_backups(page=page, size=size)


@router.post(
    "/backups",
    response_model=BackupTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full backup",
)
async def trigger_backup(
    user: AdminUser,
    service: SystemServiceDep,
) -> BackupTriggerResponse:
    row = await service.run_backup(kind="full", actor_id=user.id)
    return BackupTriggerResponse(backup_id=row.id)


@router.get(
    "/backups/{backup_id}/download",
    summary="Download a completed backup file",
)
async def download_backup(
    backup_id: int,
    _: AdminUser,
    service: SystemServiceDep,
) -> Response:
    row, data = await service.read_backup_bytes(backup_id)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.post(
    "/system/sync/flush",
    response_model=SyncFlushResponse,
    summary="Reconcile pending offline-sync rows now",
)
async def flush_sync_queue(
    user: AdminUser,
    service: SystemServiceDep,
) -> SyncFlushResponse:
    return await service.flush_sync_queue(actor_id=user.id)


@router.post(
    "/system/cleanup",
    response_model=CleanupResponse,
    summary="Prune expired OTP and finished sync-queue rows",
)
async def cleanup_expired(
    user: AdminUser,
    service: SystemServiceDep,
) -> CleanupResponse:
    return await service.cleanup_expired(actor_id=user.id)
