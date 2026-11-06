from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from shared.constants import (
    LATITUDE_MAX,
    LATITUDE_MIN,
    LONGITUDE_MAX,
    LONGITUDE_MIN,
)
from shared.enums import ScannedVia, ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE
from features.attendance.constants import (
    EAR_SAMPLES_MAX_COUNT,
    EAR_SAMPLES_MIN_COUNT,
    EAR_VALUE_MAX,
    EAR_VALUE_MIN,
    FACE_MATCH_SCORE_MAX,
    FACE_MATCH_SCORE_MIN,
    GPS_ACCURACY_MAX,
    GPS_ACCURACY_MIN,
    REVIEW_NOTE_MAX_LENGTH,
    STUDENT_NUMBER_MAX_LENGTH,
    STUDENT_NUMBER_MIN_LENGTH,
)


class GPSInput(BaseModel):
    """Nested gps input; stored flat as gps_lat/gps_lng on write."""

    lat: float = Field(ge=LATITUDE_MIN, le=LATITUDE_MAX)
    lng: float = Field(ge=LONGITUDE_MIN, le=LONGITUDE_MAX)
    accuracy: float = Field(ge=GPS_ACCURACY_MIN, le=GPS_ACCURACY_MAX)


class LivenessEvidence(BaseModel):
    """Fixex blink -> left -> right challenge graded server-side (D31)."""

    blink_detected: bool
    head_turn_left: bool
    head_turn_right: bool
    ear_samples: list[float] = Field(
        min_length=EAR_SAMPLES_MIN_COUNT, max_length=EAR_SAMPLES_MAX_COUNT
    )
    pnp_evidence: dict[str, Any] = Field(default_factory=dict)
    face_count: int = Field(default=1, ge=1, le=10)

    @field_validator("ear_samples")
    @classmethod
    def _ear_in_range(cls, v: list[float]) -> list[float]:
        for sample in v:
            if not EAR_VALUE_MIN <= sample <= EAR_VALUE_MAX:
                raise ValueError(
                    "Eye measurements were out of range. Please retry the liveness check."
                )

        return v


class ScanRequest(BaseModel):
    """Submit attendance scan (online or offline-sync replay)."""

    session_id: int = Field(gt=0)
    student_number: str = Field(
        min_length=STUDENT_NUMBER_MIN_LENGTH, max_length=STUDENT_NUMBER_MAX_LENGTH
    )
    # Location is optional: scans against sessions with no geofence (remote,
    # disabled, or no classroom coordinates) must not be forced to supply GPS.
    gps: GPSInput | None = None
    liveness_evidence: LivenessEvidence
    # Either a client-computed embedding (legacy) or a captured scan frame
    # (preferred; the server computes the embedding so enrollment and scan
    # use the same model). At least one must be supplied.
    live_face_embedding: str | None = None
    live_face_image: str | None = None
    scanned_at: datetime
    scanned_via: ScannedVia = ScannedVia.QR_CAMERA

    @field_validator("student_number")
    @classmethod
    def _strip_student_number(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("student_number must not be blank")

        return v

    @model_validator(mode="after")
    def _require_live_face(self) -> "ScanRequest":
        if not self.live_face_embedding and not self.live_face_image:
            raise ValueError("live_face_embedding or live_face_image is required")
        return self


class ScanResponse(BaseModel):
    """Scan result; status maps attendance_records.validation_status."""

    id: int
    status: Literal["present", "late", "pending", "rejected"]
    scanned_at: datetime
    expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class HistoryItem(BaseModel):
    """Row for GET /student/attendance/history; names map attendance/course columns."""

    id: int
    session_id: int
    course_code: str
    course_name: str
    status: ValidationStatus
    original_status: ValidationStatus | None = None
    excuse_reason: str | None = None
    scanned_at: datetime
    scanned_via: str | None = None


class HistoryCounts(BaseModel):
    present: int = 0
    late: int = 0
    absent: int = 0
    excused: int = 0
    rejected: int = 0


class HistorySummary(BaseModel):
    compliance_rate: float = 0.0
    participation_rate: float = 0.0
    counts: HistoryCounts = Field(default_factory=HistoryCounts)


class HistoryResponse(BaseModel):
    """Paginated history plus summary over the FULL filter set (not just the page)."""

    items: list[HistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = DEFAULT_PAGE
    size: int = DEFAULT_PAGE_SIZE
    summary: HistorySummary = Field(default_factory=HistorySummary)


class LivenessReviewItem(BaseModel):
    """One flagged row for GET /admin/attendance/liveness-review."""

    id: int
    student_number: str
    student_name: str
    session_code: str
    course_code: str
    face_match_score: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    scanned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResolveReviewRequest(BaseModel):
    """Body for PATCH /admin/attendance/liveness-review/{id}/resolve."""

    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=REVIEW_NOTE_MAX_LENGTH)

    @field_validator("note")
    @classmethod
    def _strip_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ResolveReviewResponse(BaseModel):
    """Result of a review decision."""

    id: int
    status: ValidationStatus
    reviewed_by: int
    reviewed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrecheckRequest(BaseModel):
    """Pre-check request for scan step 2: validates enrollment and duplicate scan."""

    session_id: int = Field(gt=0)
    student_number: str = Field(
        min_length=STUDENT_NUMBER_MIN_LENGTH, max_length=STUDENT_NUMBER_MAX_LENGTH
    )

    @field_validator("student_number")
    @classmethod
    def _strip_student_number(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("student_number must not be blank")

        return v


class PrecheckResponse(BaseModel):
    """Pre-check response: enrollment status and duplicate scan flag."""

    enrolled: bool
    already_scanned: bool
    student: dict[str, Any] = Field(default_factory=dict)


class OverviewItem(BaseModel):
    """One per-course row for the admin attendance overview."""

    course_id: int
    course_code: str
    course_name: str
    sessions_count: int
    avg_rate: float
    trend: Literal["up", "down", "flat"]


class OverviewResponse(BaseModel):
    """Per-course attendance overview over the requested filter set."""

    items: list[OverviewItem] = Field(default_factory=list)


class RecentScanItem(BaseModel):
    """One row of the latest-scans feed for the admin dashboard."""

    id: int
    scanned_at: datetime
    student_name: str
    course_code: str
    status: str


class RecentScansResponse(BaseModel):
    """Latest scans, newest first, capped by the requested limit."""

    items: list[RecentScanItem] = Field(default_factory=list)
