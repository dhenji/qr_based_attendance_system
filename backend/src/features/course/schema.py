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
    RADIUS_METERS_MAX,
    RADIUS_METERS_MIN,
    SEMESTER_MAX_LENGTH,
    SEMESTER_MIN_LENGTH,
)
from shared.enums import SessionType
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


class ComponentCreate(BaseModel):
    """One scheduled component of an offering (D77).

    A laboratory component should carry classroom coordinates: lab sessions
    always enforce the geofence, and creation rejects a lab session whose
    resolved location has none (`lab_coordinates_required`).
    """

    session_type: SessionType = SessionType.LECTURE
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

    @field_validator("schedule_days")
    @classmethod
    def _normalize_days(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def _times_order(self) -> "ComponentCreate":
        if self.schedule_end_time <= self.schedule_start_time:
            raise ValueError("schedule_end_time must be after schedule_start_time")

        return self


class ComponentRead(BaseModel):
    id: int
    offering_id: int
    session_type: SessionType
    schedule_days: str
    schedule_start_time: time
    schedule_end_time: time
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComponentUpdate(BaseModel):
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
    is_active: bool | None = None

    @field_validator("schedule_days")
    @classmethod
    def _normalize_days(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip().upper()

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "ComponentUpdate":
        # classroom_* are nullable columns, so an explicit null clears them;
        # every other mutable field rejects null like OfferingUpdate does.
        for field in (
            "schedule_days",
            "schedule_start_time",
            "schedule_end_time",
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
    default_present_window_minutes: int | None = Field(
        default=None,
        ge=WINDOW_MINUTES_MIN,
        le=WINDOW_MINUTES_MAX,
    )
    default_late_window_minutes: int | None = Field(
        default=None,
        ge=WINDOW_MINUTES_MIN,
        le=WINDOW_MINUTES_MAX,
    )
    # The geofence radius the offering's sessions default to (D93). NULL
    # means "inherit" — the app setting an administrator edits in Admin ->
    # System Settings wins, and only an explicit value overrides it.
    default_classroom_radius_meters: int | None = Field(
        default=None, ge=RADIUS_METERS_MIN, le=RADIUS_METERS_MAX
    )
    # Optional per-type schedules (D77). Omitted means a single lecture
    # component mirroring the offering schedule/classroom above, so
    # pre-existing callers keep working unchanged.
    components: list[ComponentCreate] | None = None

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
    # Derived (D86): resolved from the offering's year level + term code via
    # `shared.schedule.term_weeks`, never stored on the offering.
    semester_weeks: int
    schedule_days: str
    schedule_start_time: time
    schedule_end_time: time
    classroom_name: str | None = None
    classroom_lat: float | None = None
    classroom_lng: float | None = None
    # NULL means "follow the system default" (D93) for both windows and the
    # radius.
    default_present_window_minutes: int | None = None
    default_late_window_minutes: int | None = None
    # The geofence radius override. NULL clears it back to the app setting.
    default_classroom_radius_meters: int | None = Field(
        default=None, ge=RADIUS_METERS_MIN, le=RADIUS_METERS_MAX
    )
    enrolled_count: int = 0
    # Distinct session types across the active components (D77) — feeds the
    # Lecture / Lab / Mixed badges. Empty only when an offering has no
    # active component left.
    session_types: list[SessionType] = Field(default_factory=list)
    components: list[ComponentRead] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfferingUpdate(BaseModel):
    sessions_per_week: int | None = Field(
        default=None, ge=SESSIONS_PER_WEEK_MIN, le=SESSIONS_PER_WEEK_MAX
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
    # An explicit null clears the override and puts the offering back on the
    # app setting (D93).
    default_classroom_radius_meters: int | None = Field(
        default=None, ge=RADIUS_METERS_MIN, le=RADIUS_METERS_MAX
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
        # classroom_*, the window defaults and the radius are nullable
        # columns, so an explicit null clears them (D93: NULL means "follow
        # the system default"); every other mutable field rejects null like
        # CourseUpdate does.
        for field in (
            "sessions_per_week",
            "schedule_days",
            "schedule_start_time",
            "schedule_end_time",
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
    semester: str | None = None

    @field_validator("semester")
    @classmethod
    def _strip_semester(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def _dates_order(self) -> "ProfessorAssignment":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")

        return self


class ProfessorReassignment(BaseModel):
    new_professor_id: int = Field(gt=0)
    is_primary: bool | None = None
    # Composite-PK discriminator: the exact old row to replace. Optional for
    # older clients; the service falls back to the newest open-ended row.
    old_effective_from: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def _dates_order(self) -> "ProfessorReassignment":
        if self.effective_to is not None and self.effective_from is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")

        return self


class ProfessorReopen(BaseModel):
    """Undo an accidental End by clearing the exact row's end date.

    `is_primary` is an optional role override: omit it to restore the role the
    row had before it was ended, or pass `false` to reopen as an assistant when
    another primary professor already covers the dates.
    """

    effective_from: date
    is_primary: bool | None = None


class AssignmentRead(BaseModel):
    offering_id: int
    professor_id: int
    is_primary: bool
    effective_from: date
    effective_to: date | None = None
    semester: str = ""
    # True when a session was opened under this exact effective window. The
    # admin UI hides the permanent-remove action for those rows; the service
    # enforces the same rule independently.
    has_sessions: bool = False
    assigned_by: int
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RosterItem(BaseModel):
    # The student's database primary key. The roster's `student_id` is the
    # printed student number (a string); this is the integer id that the
    # per-record excuse routes (and other id-keyed endpoints) need. Carrying
    # both keeps the display value untouched while letting callers act on the
    # row without a second lookup.
    id: int
    student_id: str
    name: str
    email: str | None = None
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


class CourseImportError(BaseModel):
    line: int
    reason: str


class CourseImportResult(BaseModel):
    imported: int
    duplicates: int
    errors: list[CourseImportError] = Field(default_factory=list)
