from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from features.professor.constants import (
    DEPARTMENT_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)


class AssignedCourse(BaseModel):
    offering_id: int
    course_code: str


class ProfessorCreate(BaseModel):
    """Admin roster create.

    `username` is the claim slot used at self-registration (omitted =
    auto-generated at claim). It is validated here but NOT persisted:
    `professors` has no username column, and `users.username` uniqueness is
    enforced at claim time. `courses` assigns offerings immediately via
    `CourseProfessorService.check_overlap` (course_professors rows); no user
    row is created — the professor stays Unclaimed until self-register.
    """

    first_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    middle_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    last_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    email: EmailStr = Field(max_length=EMAIL_MAX_LENGTH)
    department: str | None = Field(default=None, max_length=DEPARTMENT_MAX_LENGTH)
    username: str | None = Field(
        default=None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    courses: list[int] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip()

    @field_validator("courses")
    @classmethod
    def _validate_courses(cls, value: list[int]) -> list[int]:
        for offering_id in value:
            if offering_id <= 0:
                raise ValueError("courses must contain offering ids > 0")

        return value


class ProfessorRead(BaseModel):
    id: int
    first_name: str
    middle_name: str | None = None
    last_name: str
    email: str
    department: str | None = None
    is_active: bool
    claim_status: Literal["Claimed", "Unclaimed"]
    assigned_courses: list[AssignedCourse] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfessorDetail(ProfessorRead):
    pass


class ProfessorUpdate(BaseModel):
    first_name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    last_name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    email: EmailStr | None = Field(default=None, max_length=EMAIL_MAX_LENGTH)
    department: str | None = Field(default=None, max_length=DEPARTMENT_MAX_LENGTH)
    is_active: bool | None = None
    courses: list[int] | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip().lower()

    @field_validator("courses")
    @classmethod
    def _validate_courses(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None

        for offering_id in value:
            if offering_id <= 0:
                raise ValueError("courses must contain offering ids > 0")

        return value

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "ProfessorUpdate":
        for field in ("first_name", "last_name", "email", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self
