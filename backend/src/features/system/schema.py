from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from features.system.constants import (
    ATTENDANCE_ATTEMPT_LIMIT_MAX,
    ATTENDANCE_ATTEMPT_LIMIT_MIN,
    GEOFENCE_RADIUS_MAX,
    GEOFENCE_RADIUS_MIN,
    OPEN_GRACE_MAX_MINUTES,
    OPEN_GRACE_MIN_MINUTES,
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
    # The open-window grace (D94): how early and how late a session may be
    # opened around its scheduled class.
    session_early_open_minutes: int
    session_late_open_minutes: int
    backup_retention_daily: int
    backup_retention_monthly: int
    # Per-student attempt cap for a single attendance session. 0 = unlimited.
    attendance_attempt_limit_default: int
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
    session_early_open_minutes: int | None = Field(
        default=None, ge=OPEN_GRACE_MIN_MINUTES, le=OPEN_GRACE_MAX_MINUTES
    )
    session_late_open_minutes: int | None = Field(
        default=None, ge=OPEN_GRACE_MIN_MINUTES, le=OPEN_GRACE_MAX_MINUTES
    )
    backup_retention_daily: int | None = Field(
        default=None, ge=RETENTION_DAILY_MIN, le=RETENTION_DAILY_MAX
    )
    backup_retention_monthly: int | None = Field(
        default=None, ge=RETENTION_MONTHLY_MIN, le=RETENTION_MONTHLY_MAX
    )
    attendance_attempt_limit_default: int | None = Field(
        default=None,
        ge=ATTENDANCE_ATTEMPT_LIMIT_MIN,
        le=ATTENDANCE_ATTEMPT_LIMIT_MAX,
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


class AuditActorRead(BaseModel):
    """Who performed the action.

    `kind` is `anonymous` when nobody was authenticated — a lockout from an
    anonymous attempt, or an unattended run. Otherwise it is `user`, and
    `id`/`name`/`email`/`role` name the account.
    """

    kind: Literal["user", "anonymous"]
    id: int | None = None
    name: str
    email: str | None = None
    role: str | None = None


class AuditSubjectRead(BaseModel):
    """What the action was about.

    `label` is the record's name — "BSCS · Bachelor of Science in Computer
    Science" — read out of the audit snapshot first and only then from a
    join, so it survives the record's deletion. `id` remains the raw
    reference, in the id space of `type`.
    """

    type: str
    id: int | None = None
    label: str
    sublabel: str | None = None


class AuditChangeRead(BaseModel):
    """One field that changed."""

    field: str
    label: str
    before: str
    after: str


class AuditLogRead(BaseModel):
    """One audit trail row.

    The stored shape, unaltered: `entity_type` + `entity_id` identify the
    subject and `old_value`/`new_value` are the JSON snapshots the writer took.
    That is the evidence, and it is exactly what was recorded.

    Alongside it, the derived read model (ADR-086): who acted, what the
    subject is called, a one-line summary, and the field-level change. The
    derived fields are additive — the stored ones are still there, so nothing
    that read the raw row stops working.
    """

    id: int
    action: str
    entity_type: str
    entity_id: int | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    performed_by: int | None = None
    performed_at: datetime

    actor: AuditActorRead
    subject: AuditSubjectRead
    summary: str
    action_label: str
    changes: list[AuditChangeRead] = Field(default_factory=list)

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
