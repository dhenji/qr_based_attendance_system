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
