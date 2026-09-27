from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from features.course.constants import (
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    DURATION_MAX,
    DURATION_MIN,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    UNITS_MAX,
    UNITS_MIN,
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
