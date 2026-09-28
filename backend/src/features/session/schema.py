from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from features.session.constants import (
    CLASSROOM_NAME_MAX_LENGTH,
    DURATION_MINUTES_MAX,
    DURATION_MINUTES_MIN,
    RADIUS_METERS_MAX,
    RADIUS_METERS_MIN,
    SESSION_CODE_MAX_LENGTH,
    SESSION_CODE_MIN_LENGTH,
    WINDOW_MINUTES_MAX,
    WINDOW_MINUTES_MIN,
)
from shared.enums import ValidationStatus


class QRPayload(BaseModel):
    """Versioned QR payload; compact keys map to Session columns."""

    v: Literal[1] = 1
    code: str
    offering: int
    radius: int
    pw: int
    lw: int


class SessionCreate(BaseModel):
    offering_id: int = Field(gt=0)
    duration_minutes: int | None = Field(
        default=None, ge=DURATION_MINUTES_MIN, le=DURATION_MINUTES_MAX
    )
    present_window_minutes: int | None = Field(
        default=None, ge=WINDOW_MINUTES_MIN, le=WINDOW_MINUTES_MAX
    )
    late_window_minutes: int | None = Field(
        default=None, ge=WINDOW_MINUTES_MIN, le=WINDOW_MINUTES_MAX
    )
    classroom_radius_meters: int | None = Field(
        default=None, ge=RADIUS_METERS_MIN, le=RADIUS_METERS_MAX
    )
    classroom_name: str | None = Field(
        default=None, max_length=CLASSROOM_NAME_MAX_LENGTH
    )
    classroom_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    classroom_lng: float | None = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _windows_within_duration(self) -> "SessionCreate":
        if (
            self.duration_minutes is not None
            and self.present_window_minutes is not None
            and self.late_window_minutes is not None
            and self.present_window_minutes + self.late_window_minutes
            > self.duration_minutes
        ):
            raise ValueError(
                "present_window_minutes + late_window_minutes must not exceed "
                "duration_minutes"
            )

        return self


class SessionRead(BaseModel):
    id: int
    session_code: str
    offering_id: int
    qr_payload: QRPayload
    expires_at: datetime | None = None
    scheduled_end_time: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionListItem(BaseModel):
    """Row for GET /professor/sessions; counts and status are computed DTOs."""

    id: int
    offering_id: int
    session_code: str
    created_at: datetime
    expires_at: datetime | None = None
    duration_minutes: int
    present_count: int = 0
    late_count: int = 0
    absent_count: int = 0
    status: Literal["active", "closed"]

    model_config = ConfigDict(from_attributes=True)


class SessionHistoryItem(SessionListItem):
    compliance_rate: float = 0.0
    participation_rate: float = 0.0


class ActiveStudentItem(BaseModel):
    student_number: str
    name: str
    section: str | None = None
    status: ValidationStatus
    scanned_at: datetime | None = None
    excuse_reason: str | None = None


class SessionCounts(BaseModel):
    present: int = 0
    late: int = 0
    pending: int = 0
    absent: int = 0
    excused: int = 0


class SessionActiveResponse(BaseModel):
    """Live session detail; status, timers, counts and lists are computed DTOs."""

    id: int
    offering: int
    session_code: str
    scan_window_remaining: int
    scheduled_end_time: datetime
    status: Literal["active", "closed"]
    enrolled_count: int = 0
    remaining: int = 0
    pending_sync_count: int = 0
    students: list[ActiveStudentItem] = Field(default_factory=list)
    counts: SessionCounts = Field(default_factory=SessionCounts)


class SessionCloseResponse(BaseModel):
    id: int
    status: Literal["closed"] = "closed"
    final_counts: SessionCounts = Field(default_factory=SessionCounts)


class ProfessorAttendanceItem(BaseModel):
    """Row for GET /professor/attendance; names map student/attendance columns."""

    id: int
    student_number: str
    student_name: str
    section: str | None = None
    session_id: int
    status: ValidationStatus
    original_status: ValidationStatus | None = None
    scanned_at: datetime
    scanned_via: str | None = None
    face_match_score: float | None = None


class VerifyCodeRequest(BaseModel):
    """Typed session code (verify-code) or code scanned from the session QR."""

    code: str = Field(
        min_length=SESSION_CODE_MIN_LENGTH, max_length=SESSION_CODE_MAX_LENGTH
    )

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("code must not be blank")

        return v


class VerifyGeofence(BaseModel):
    """Geofence config; keys map to Session classroom columns."""

    radius: int
    lat: float | None = None
    lng: float | None = None


class VerifyCodeResponse(BaseModel):
    session_id: int
    offering_id: int
    course_code: str
    course_name: str
    program_code: str
    year_level_label: str
    expires_at: datetime | None = None
    scheduled_end_time: datetime
    geofence: VerifyGeofence
    present_window_minutes: int
    late_window_minutes: int
