from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import SystemServiceDep, require_role
from features.auth.model import User
from features.system.schema import (
    AcademicStructureListResponse,
    BackupListResponse,
    BackupTriggerResponse,
    SystemSettingsRead,
    SystemSettingsUpdate,
)
from shared.enums import UserRole
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

# This module owns /admin/system/* and /admin/backups/* ONLY. Both paths are
# unique across the mounted admin routers, so one router covers the slice.
router = APIRouter(prefix="/admin")

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


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
    _: AdminUser,
    service: SystemServiceDep,
) -> SystemSettingsRead:
    return await service.update_system_settings(patch)


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
    _: AdminUser,
    service: SystemServiceDep,
) -> BackupTriggerResponse:
    row = await service.run_backup(kind="full")
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
