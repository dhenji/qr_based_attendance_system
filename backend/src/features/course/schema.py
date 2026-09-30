from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.constants import (
    DEFAULT_LATE_WINDOW_MINUTES,
    DEFAULT_PRESENT_WINDOW_MINUTES,
    LATITUDE_MAX,
    LATITUDE_MIN,
    LONGITUDE_MAX,
    LONGITUDE_MIN,
    SEMESTER_MAX_LENGTH,
    SEMESTER_MIN_LENGTH,
)
from features.course.constants import (
    ACADEMIC_YEAR_MAX_LENGTH,
    ACADEMIC_YEAR_MIN_LENGTH,
    CLASSROOM_NAME_MAX_LENGTH,
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    DURATION_MAX,
    DURATION_MIN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    SCHEDULE_DAYS_MAX_LENGTH,
    SCHEDULE_DAYS_MIN_LENGTH,
    SEMESTER_WEEKS_MAX,
    SEMESTER_WEEKS_MIN,
    SESSIONS_PER_WEEK_MAX,
    SESSIONS_PER_WEEK_MIN,
    UNITS_MAX,
    UNITS_MIN,
    WINDOW_MINUTES_MAX,
    WINDOW_MINUTES_MIN,
)


class CourseCreate(BaseModel):
    course_code: str = Field(min_length=CODE_MIN_LENGTH, max_length=CODE_MAX_LENGTH)
    course_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    units: int = Field(ge=UNITS_MIN, le=UNITS_MAX)
    session_duration_hours: float = Field(ge=DURATION_MIN, le=DURATION_MAX)

    @field_validator("course_code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class CourseRead(BaseModel):
    id: int
    course_code: str
    course_name: str
    units: int
    session_duration_hours: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseUpdate(BaseModel):
    course_code: str | None = Field(
        default=None, min_length=CODE_MIN_LENGTH, max_length=CODE_MAX_LENGTH
    )
    course_name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    units: int | None = Field(default=None, ge=UNITS_MIN, le=UNITS_MAX)
    session_duration_hours: float | None = Field(
        default=None, ge=DURATION_MIN, le=DURATION_MAX
    )
    is_active: bool | None = None

    @field_validator("course_code")
    @classmethod
    def _normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip().upper()

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "CourseUpdate":
        for field in (
            "course_code",
            "course_name",
            "units",
            "session_duration_hours",
            "is_active",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class OfferingCreate(BaseModel):
    course_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    year_level_id: int = Field(gt=0)
    semester: str = Field(
        min_length=SEMESTER_MIN_LENGTH, max_length=SEMESTER_MAX_LENGTH
    )
    academic_year: str = Field(
        min_length=ACADEMIC_YEAR_MIN_LENGTH, max_length=ACADEMIC_YEAR_MAX_LENGTH
    )
    sessions_per_week: int = Field(ge=SESSIONS_PER_WEEK_MIN, le=SESSIONS_PER_WEEK_MAX)
    semester_weeks: int = Field(ge=SEMESTER_WEEKS_MIN, le=SEMESTER_WEEKS_MAX)
    schedule_days: str = Field(
        min_length=SCHEDULE_DAYS_MIN_LENGTH, max_length=SCHEDULE_DAYS_MAX_LENGTH
    )
    schedule_start_time: time
    schedule_end_time: time
    classroom_name: str | None = Field(
        default=None, max_length=CLASSROOM_NAME_MAX_LENGTH
    )
    classroom_lat: float | None = Field(
        default=None, ge=LATITUDE_MIN, le=LATITUDE_MAX
    )
    classroom_lng: float | None = Field(
        default=None, ge=LONGITUDE_MIN, le=LONGITUDE_MAX
    )
    default_present_window_minutes: int = Field(
        default=DEFAULT_PRESENT_WINDOW_MINUTES,
        ge=WINDOW_MINUTES_MIN,
        le=WINDOW_MINUTES_MAX,
    )
    default_late_window_minutes: int = Field(
        default=DEFAULT_LATE_WINDOW_MINUTES,
        ge=WINDOW_MINUTES_MIN,
        le=WINDOW_MINUTES_MAX,
    )

    @field_validator("semester", "academic_year", "schedule_days")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("schedule_days")
    @classmethod
    def _normalize_days(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _times_order(self) -> "OfferingCreate":
        if self.schedule_end_time <= self.schedule_start_time:
            raise ValueError("schedule_end_time must be after schedule_start_time")

        return self


class OfferingRead(BaseModel):
    id: int
    course_id: int
    program_id: int
    year_level_id: int
    semester: str
    academic_year: str
    sessions_per_week: int
    semester_weeks: int
    schedule_days: str
    schedule_start_time: time
    schedule_end_time: time
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    default_present_window_minutes: int
    default_late_window_minutes: int
    enrolled_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfferingUpdate(BaseModel):
    sessions_per_week: int | None = Field(
        default=None, ge=SESSIONS_PER_WEEK_MIN, le=SESSIONS_PER_WEEK_MAX
    )
    semester_weeks: int | None = Field(
        default=None, ge=SEMESTER_WEEKS_MIN, le=SEMESTER_WEEKS_MAX
    )
    schedule_days: str | None = Field(
        default=None,
        min_length=SCHEDULE_DAYS_MIN_LENGTH,
        max_length=SCHEDULE_DAYS_MAX_LENGTH,
    )
    schedule_start_time: time | None = None
    schedule_end_time: time | None = None
    classroom_name: str | None = None
    classroom_lat: float | None = Field(
        default=None, ge=LATITUDE_MIN, le=LATITUDE_MAX
    )
    classroom_lng: float | None = Field(
        default=None, ge=LONGITUDE_MIN, le=LONGITUDE_MAX
    )
    default_present_window_minutes: int | None = Field(
        default=None, ge=WINDOW_MINUTES_MIN, le=WINDOW_MINUTES_MAX
    )
    default_late_window_minutes: int | None = Field(
        default=None, ge=WINDOW_MINUTES_MIN, le=WINDOW_MINUTES_MAX
    )
    is_active: bool | None = None

    @field_validator("schedule_days")
    @classmethod
    def _normalize_days(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip().upper()

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "OfferingUpdate":
        # classroom_* are nullable columns, so an explicit null clears them;
        # every other mutable field rejects null like CourseUpdate does.
        for field in (
            "sessions_per_week",
            "semester_weeks",
            "schedule_days",
            "schedule_start_time",
            "schedule_end_time",
            "default_present_window_minutes",
            "default_late_window_minutes",
            "is_active",
        ):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        if (
            self.schedule_start_time is not None
            and self.schedule_end_time is not None
            and self.schedule_end_time <= self.schedule_start_time
        ):
            raise ValueError("schedule_end_time must be after schedule_start_time")

        return self


class ProfessorAssignment(BaseModel):
    professor_id: int = Field(gt=0)
    is_primary: bool = False
    effective_from: date
    effective_to: date | None = None
    semester: str = Field(
        min_length=SEMESTER_MIN_LENGTH, max_length=SEMESTER_MAX_LENGTH
    )

    @field_validator("semester")
    @classmethod
    def _strip_semester(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _dates_order(self) -> "ProfessorAssignment":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")

        return self


class AssignmentRead(BaseModel):
    offering_id: int
    professor_id: int
    is_primary: bool
    effective_from: date
    effective_to: date | None = None
    semester: str
    assigned_by: int
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RosterItem(BaseModel):
    student_id: str
    name: str
    section: str | None = None
    enrolled_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BulkEnrollError(BaseModel):
    line: int
    reason: str


class BulkEnrollResult(BaseModel):
    enrolled: int
    skipped: int
    errors: list[BulkEnrollError] = Field(default_factory=list)
