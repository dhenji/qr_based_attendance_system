from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.constants import (
    LATITUDE_MAX,
    LATITUDE_MIN,
    LONGITUDE_MAX,
    LONGITUDE_MIN,
    RADIUS_METERS_MAX,
    RADIUS_METERS_MIN,
)
from shared.enums import SessionType, ValidationStatus
from shared.pagination import PaginatedResponse

from features.session.constants import (
    CLASSROOM_NAME_MAX_LENGTH,
    DURATION_MINUTES_MAX,
    DURATION_MINUTES_MIN,
    OVERRIDE_REASON_MAX_LENGTH,
    SESSION_CODE_MAX_LENGTH,
    SESSION_CODE_MIN_LENGTH,
    WINDOW_MINUTES_MAX,
    WINDOW_MINUTES_MIN,
)


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
    # Lecture vs laboratory (D77). Defaults to lecture; lab sessions must
    # resolve classroom coordinates or creation fails with
    # `lab_coordinates_required`.
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    # Per-student attempt cap for this session. None inherits the admin
    # default; 0 means unlimited. Bounded 0..10.
    attendance_attempt_limit: int | None = Field(default=None, ge=0, le=10)
    # Whether the professor explicitly overrode the offering's classroom. When
    # True, the payload's classroom fields are used as-is (including None),
    # so an intentionally cleared room is not replaced by the offering's
    # default. When False (the default), omitted fields inherit the plan.
    classroom_override: bool = False
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
    classroom_lat: float | None = Field(default=None, ge=LATITUDE_MIN, le=LATITUDE_MAX)
    classroom_lng: float | None = Field(
        default=None, ge=LONGITUDE_MIN, le=LONGITUDE_MAX
    )
    # Schedule exception (D93). Omitted means "use the offering's plan" —
    # the server resolves the next occurrence of the offering's meeting and
    # stores it as the session's scheduled start/end.
    #
    # These are wall clock values in the institution's timezone, not ISO
    # instants: the offering's own `schedule_start_time` is a naive wall
    # clock too, and the browser cannot convert an IANA zone without a
    # timezone library. Either field alone is an override; together they
    # re-point the session. Either one sets `schedule_overridden`.
    session_date: date | None = None
    start_time: time | None = None
    # D94: why the professor moved the class, in their own words. Optional,
    # and only meaningful with an override.
    override_reason: str | None = Field(
        default=None, max_length=OVERRIDE_REASON_MAX_LENGTH
    )

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
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    # Per-student attempt cap for this session. 0 means unlimited.
    attendance_attempt_limit: int = 0
    qr_payload: QRPayload
    expires_at: datetime | None = None
    # The scheduled window (D93): the offering's plan, or the override the
    # professor asked for. `schedule_overridden` says which.
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    schedule_overridden: bool = False
    plan_source: str = "none"
    # D94: when the session was actually opened, and — for an override — the
    # start it would have carried.
    actual_start_time: datetime | None = None
    original_scheduled_start_time: datetime | None = None
    override_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StartWindowRead(BaseModel):
    """Whether the session may be opened right now, and why not (D94).

    The server's own answer, so the open form renders the window instead of
    re-deriving it. `scheduled_date` / `start_time` / `end_time` are today's
    occurrence of the meeting in the institution's local terms, and are null
    when today is not one of the meeting's days — the plan's *next*
    occurrence is what the session would carry then.
    """

    permitted: bool = True
    reason: str | None = None
    scheduled_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    current_time: datetime
    timezone: str = "UTC"
    early_open_minutes: int = 0
    late_open_minutes: int = 0


class SessionPlanRead(BaseModel):
    """Everything a session for an offering inherits (D93).

    The resolved plan, so the open form renders what the server will store
    rather than re-deriving it. `source` names where the meeting came from:
    `component` (the offering's active meeting for this type), `offering_legacy`
    (the offering's own schedule columns), `course_default` (no meeting
    configured) or `none` (nothing at all).
    """

    offering_id: int
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    source: str = "none"
    # The next occurrence, in the institution's local terms and as UTC.
    session_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    timezone: str = "UTC"
    duration_minutes: int = 0
    present_window_minutes: int = 0
    late_window_minutes: int = 0
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    radius_meters: int = 0
    # Whether a professor may override the time at all — there is nothing to
    # override when no meeting is configured.
    override_capable: bool = False
    # Per-student attempt cap default inherited by new sessions. 0 = unlimited.
    attendance_attempt_limit_default: int = 0
    # Whether the session may be opened right now (D94).
    start_window: StartWindowRead | None = None


class SessionOfferingTile(BaseModel):
    """One of today's sessions, reduced to what a dashboard tile shows.

    The contract writes this row as `{ offering, scanned, enrolled }`. The
    offering is split into `session_id` + `offering_id` because both are needed
    to key the tile and no single column identifies the session on its own;
    `scanned` is the attendance-row count, which is not the same as
    present + late (excused and pending rows are scans too).

    `status` rides along so a caller can count closed sessions without a second
    query in a different scope. Sessions carry no status column — this is the
    derived `_session_status` value.
    """

    session_id: int
    offering_id: int
    scanned: int
    enrolled: int
    status: Literal["scheduled", "active", "closed"]


class SessionListItem(BaseModel):
    """Row for GET /professor/sessions; counts and status are computed DTOs."""

    id: int
    offering_id: int
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    # Per-student attempt cap for this session. 0 means unlimited.
    attendance_attempt_limit: int = 0
    session_code: str
    created_at: datetime
    expires_at: datetime | None = None
    scheduled_end_time: datetime
    duration_minutes: int
    present_count: int = 0
    late_count: int = 0
    absent_count: int = 0
    # Unscanned students read as pending while the session is scheduled/active
    # and as absent once it is closed, so the list tile carries both tallies
    # (default 0 keeps older payloads valid).
    pending_count: int = 0
    status: Literal["scheduled", "active", "closed"]

    model_config = ConfigDict(from_attributes=True)


class SessionHistoryItem(SessionListItem):
    compliance_rate: float = 0.0
    participation_rate: float = 0.0


class ActiveStudentItem(BaseModel):
    # The student's database primary key, so per-record actions (such as a
    # professor quick-excuse) can target the row without a second lookup. The
    # printed student number stays in `student_number`.
    student_id: int
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
    rejected: int = 0


class SessionActiveResponse(BaseModel):
    """Live session detail; status, timers, counts and lists are computed DTOs."""

    id: int
    offering: int
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    # Per-student attempt cap for this session. 0 means unlimited.
    attendance_attempt_limit: int = 0
    session_code: str
    scan_window_remaining: int = Field(
        description=(
            "Seconds remaining before the session expires. Note this is "
            "SECONDS, unlike duration_minutes / present_window_minutes / "
            "late_window_minutes, which are minutes."
        )
    )
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    expires_at: datetime | None = None
    # Offering-level academic context (nullable so a broken graph degrades
    # gracefully instead of 500ing on attribute access).
    program_code: str | None = None
    year_level_label: str | None = None
    academic_year: str | None = None
    semester: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    status: Literal["scheduled", "active", "closed"]
    enrolled_count: int = 0
    remaining: int = 0
    pending_sync_count: int = 0
    # Session configuration (minutes).
    duration_minutes: int = 0
    present_window_minutes: int = 0
    late_window_minutes: int = 0
    # Location / geofence details.
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    classroom_radius_meters: int = 0
    # Schedule provenance (D94).
    schedule_overridden: bool = False
    actual_start_time: datetime | None = None
    original_scheduled_start_time: datetime | None = None
    override_reason: str | None = None
    created_at: datetime | None = None
    # Attendance rates (compliance = present/enrolled; participation adds late+excused).
    compliance_rate: float = 0.0
    participation_rate: float = 0.0
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
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    status: ValidationStatus
    original_status: ValidationStatus | None = None
    scanned_at: datetime
    scanned_via: str | None = None
    face_match_score: float | None = None


class ProfessorAttendanceResponse(PaginatedResponse[ProfessorAttendanceItem]):
    """Paginated professor attendance ledger plus global aggregates."""

    counts: dict[str, int] = Field(default_factory=dict)
    total_students: int = 0
    total_sessions: int = 0


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
    uncertainty_cap_meters: float = 50.0
    gps_hard_floor_meters: float = 1000.0
    gps_review_accuracy_threshold: float = 100.0


class VerifyCodeResponse(BaseModel):
    session_id: int
    offering_id: int
    session_type: SessionType = SessionType.LECTURE
    # Remote/online session: skips the geofence (no classroom coordinates
    # required) and is recorded as remote for audit/reporting purposes.
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
    # Per-session attempt cap. 0 means unlimited. The caller's attempt
    # state is populated only when the caller resolves to a student row
    # (student role); other roles read None. The exhaustion case never
    # appears in a 200 — it raises 409 attendance_attempt_limit_reached
    # with attempt metadata (consumed=False) instead.
    attendance_attempt_limit: int = 0
    attempts_used: int | None = None
    attempts_remaining: int | None = None
    course_code: str
    course_name: str
    program_code: str
    year_level_label: str
    expires_at: datetime | None = None
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    geofence: VerifyGeofence
    present_window_minutes: int
    late_window_minutes: int
    classroom_name: str | None = None
    is_remote: bool = False
    # Whether the geofence is enforced for this session. Defaults to True;
    # set False for an in-person session with no known classroom.
    geofence_enabled: bool = True
