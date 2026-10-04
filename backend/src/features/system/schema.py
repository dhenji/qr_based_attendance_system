from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from features.system.constants import (
    GEOFENCE_RADIUS_MAX,
    GEOFENCE_RADIUS_MIN,
    RETENTION_DAILY_MAX,
    RETENTION_DAILY_MIN,
    RETENTION_MONTHLY_MAX,
    RETENTION_MONTHLY_MIN,
    WINDOW_MAX_MINUTES,
    WINDOW_MIN_MINUTES,
)
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE


class SystemSettingsRead(BaseModel):
    geofence_default_radius: int
    present_window_default: int
    late_window_default: int
    backup_retention_daily: int
    backup_retention_monthly: int
    pending_sync_count: int


class SystemSettingsUpdate(BaseModel):
    geofence_default_radius: int | None = Field(
        default=None, ge=GEOFENCE_RADIUS_MIN, le=GEOFENCE_RADIUS_MAX
    )
    present_window_default: int | None = Field(
        default=None, ge=WINDOW_MIN_MINUTES, le=WINDOW_MAX_MINUTES
    )
    late_window_default: int | None = Field(
        default=None, ge=WINDOW_MIN_MINUTES, le=WINDOW_MAX_MINUTES
    )
    backup_retention_daily: int | None = Field(
        default=None, ge=RETENTION_DAILY_MIN, le=RETENTION_DAILY_MAX
    )
    backup_retention_monthly: int | None = Field(
        default=None, ge=RETENTION_MONTHLY_MIN, le=RETENTION_MONTHLY_MAX
    )


class BackupRead(BaseModel):
    id: int
    filename: str
    kind: str
    size_bytes: int
    storage_backend: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class BackupListResponse(BaseModel):
    items: list[BackupRead] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class BackupTriggerResponse(BaseModel):
    backup_id: int
    status: Literal["started"] = "started"


class SyncFlushResponse(BaseModel):
    processed: int = 0
    succeeded: int = 0
    failed: int = 0


class CleanupResponse(BaseModel):
    removed: int = 0


class AuditLogRead(BaseModel):
    """One audit trail row.

    The stored shape, unaltered: `entity_type` + `entity_id` identify the
    subject and `old_value`/`new_value` are the JSON snapshots the writer took.
    Nothing is derived here, so an administrator reading this endpoint sees what
    was actually recorded.
    """

    id: int
    action: str
    entity_type: str
    entity_id: int | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    performed_by: int | None = None
    performed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AcademicStructureRead(AuditLogRead):
    """The `audit_logs` row, scoped to the four structural entity types.

    A subclass rather than a copy so the two endpoints cannot drift apart; the
    name is kept because it is already in the published OpenAPI schema.
    """


class AcademicStructureListResponse(BaseModel):
    items: list[AcademicStructureRead] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE
