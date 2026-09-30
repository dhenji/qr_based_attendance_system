from __future__ import annotations

from datetime import datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from features.student.constants import (
    EMAIL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    PASSWORD_MIN_LENGTH,
    SECTION_MAX_LENGTH,
    STUDENT_ID_MAX_LENGTH,
    STUDENT_ID_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)


class StudentCreate(BaseModel):
    """Admin roster create.

    `username` is the claim slot used at self-registration (omitted =
    auto-generated at claim). It is validated here but NOT persisted:
    `students` has no username column, and `users.username` uniqueness is
    enforced at claim time.
    """

    student_id: str = Field(
        min_length=STUDENT_ID_MIN_LENGTH, max_length=STUDENT_ID_MAX_LENGTH
    )
    first_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    middle_name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    last_name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    email: EmailStr = Field(max_length=EMAIL_MAX_LENGTH)
    program_id: int = Field(gt=0)
    year_level_id: int = Field(gt=0)
    section: str | None = Field(default=None, max_length=SECTION_MAX_LENGTH)
    username: str | None = Field(
        default=None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )

    @field_validator("student_id")
    @classmethod
    def _normalize_student_id(cls, value: str) -> str:
        return value.strip().upper()

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


class StudentRead(BaseModel):
    id: int
    student_id: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    email: str
    program_code: str
    year_level_label: str
    section: str | None = None
    is_active: bool
    face_enrolled: bool = False
    created_at: datetime
    scan_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class StudentDetail(StudentRead):
    """Single-student detail, for the profile page and the admin detail route.

    `student_number` is the same value as `student_id`, carried under the name
    the *student-facing* contract uses (api-contracts.md:1035) while the admin
    roster rows keep `student_id` (:615/:634). Both are emitted so either
    client reads the field it expects; the two spellings collapse onto the one
    column `students.student_id` and cannot disagree.
    """

    student_number: str = ""
    face_enrolled_at: datetime | None = None
    face_embedding_version: int = 0


class StudentUpdate(BaseModel):
    first_name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    last_name: str | None = Field(
        default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH
    )
    email: EmailStr | None = Field(default=None, max_length=EMAIL_MAX_LENGTH)
    program_id: int | None = Field(default=None, gt=0)
    year_level_id: int | None = Field(default=None, gt=0)
    section: str | None = Field(default=None, max_length=SECTION_MAX_LENGTH)
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.strip().lower()

    @model_validator(mode="after")
    def _reject_null_on_not_nullable(self) -> "StudentUpdate":
        for field in ("first_name", "last_name", "email", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class StudentImportError(BaseModel):
    line: int
    reason: str


class StudentImportResult(BaseModel):
    imported: int
    duplicates: int
    errors: list[StudentImportError] = Field(default_factory=list)


class FaceEmbeddingResponse(BaseModel):
    """Version-gated face-embedding pull.

    `embedding` is the base64-encoded encrypted blob from `students.face_embedding` - opaque passthrough, decrypted client-side.
    """

    version: int
    embedding: str


class ScheduleItem(BaseModel):
    """One enrolled offering for GET /student/schedule

    Read-only projection over Enrollment -> CourseOffering -> Course / Program / YearLevel, plus the current primary professor name. `classroom_name` is None when the offering has no room set;
    `professor_name` is None when no current assignment exists.
    """

    offering_id: int
    course_id: int
    course_code: str
    course_name: str
    program_code: str
    year_level_label: str
    semester: str
    schedule_days: str
    schedule_start_time: time
    schedule_end_time: time
    classroom_name: str | None = None
    professor_name: str | None = None


class ScheduleResponse(BaseModel):
    """Full schedule envelope (no pagination - one row per enrollment)."""

    offerings: list[ScheduleItem] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    """Student self-service password change."""

    current_password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH)
