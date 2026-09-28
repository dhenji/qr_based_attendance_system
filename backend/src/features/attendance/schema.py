from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from features.attendance.constants import (
    EAR_SAMPLES_MAX_COUNT,
    EAR_SAMPLES_MIN_COUNT,
    EAR_VALUE_MAX,
    EAR_VALUE_MIN,
    FACE_MATCH_SCORE_MAX,
    FACE_MATCH_SCORE_MIN,
    GPS_ACCURACY_MAX,
    GPS_ACCURACY_MIN,
    GPS_LAT_MAX,
    GPS_LAT_MIN,
    GPS_LNG_MAX,
    GPS_LNG_MIN,
    STUDENT_NUMBER_MAX_LENGTH,
    STUDENT_NUMBER_MIN_LENGTH,
)
from shared.enums import ScannedVia, ValidationStatus


class GPSInput(BaseModel):
    """Nested gps input; stored flat as gps_lat/gps_lng on write."""

    lat: float = Field(ge=GPS_LAT_MIN, le=GPS_LAT_MAX)
    lng: float = Field(ge=GPS_LNG_MIN, le=GPS_LNG_MAX)
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

    @field_validator("ear_samples")
    @classmethod
    def _ear_in_range(cls, v: list[float]) -> list[float]:
        for sample in v:
            if not EAR_VALUE_MIN <= sample <= EAR_VALUE_MAX:
                raise ValueError("ear_samples must all be within 0.0..1.0")

        return v


class ScanRequest(BaseModel):
    """Submit attendance scan (online or offline-sync replay)."""

    session_id: int = Field(gt=0)
    student_number: str = Field(
        min_length=STUDENT_NUMBER_MIN_LENGTH, max_length=STUDENT_NUMBER_MAX_LENGTH
    )
    gps: GPSInput
    liveness_evidence: LivenessEvidence
    face_match_score: float = Field(ge=FACE_MATCH_SCORE_MIN, le=FACE_MATCH_SCORE_MAX)
    scanned_at: datetime
    scanned_via: ScannedVia = ScannedVia.QR_CAMERA

    @field_validator("student_number")
    @classmethod
    def _strip_student_number(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("student_number must not be blank")

        return v


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
    page: int = 1
    size: int = 50
    summary: HistorySummary = Field(default_factory=HistorySummary)
