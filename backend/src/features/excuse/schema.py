from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from features.excuse.constants import (
    ATTACHMENT_MAX_COUNT,
    REASON_MAX_LENGTH,
    REASON_MIN_LENGTH_QUICK,
    REASON_MIN_LENGTH_STUDENT,
)


def _clean_reason(value: str) -> str:
    return " ".join(value.split())


def _clean_urls(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned: list[str] = [url.strip() for url in values if url.strip()]
    return cleaned or None


class QuickExcuseRequest(BaseModel):
    reason: Annotated[
        str, Field(min_length=REASON_MIN_LENGTH_QUICK, max_length=REASON_MAX_LENGTH)
    ]

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _clean_reason(value)


class ProfWithEvidenceRequest(BaseModel):
    reason: Annotated[
        str, Field(min_length=REASON_MIN_LENGTH_QUICK, max_length=REASON_MAX_LENGTH)
    ]
    attachment_urls: Annotated[
        list[str], Field(min_length=1, max_length=ATTACHMENT_MAX_COUNT)
    ]

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _clean_reason(value)

    @field_validator("attachment_urls")
    @classmethod
    def normalize_urls(cls, values: list[str]) -> list[str]:
        cleaned: list[str] | None = _clean_urls(values)
        if not cleaned:
            raise ValueError("At least one attachment URL is required")
        return cleaned


class StudentExcuseRequest(BaseModel):
    session_id: Annotated[int, Field(gt=0)]
    reason: Annotated[
        str, Field(min_length=REASON_MIN_LENGTH_STUDENT, max_length=REASON_MAX_LENGTH)
    ]
    attachment_urls: Annotated[
        list[str], Field(min_length=1, max_length=ATTACHMENT_MAX_COUNT)
    ]

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _clean_reason(value)

    @field_validator("attachment_urls")
    @classmethod
    def normalize_urls(cls, values: list[str]) -> list[str]:
        cleaned: list[str] | None = _clean_urls(values)
        if not cleaned:
            raise ValueError("At least one attachment URL is required")
        return cleaned


class ExcuseReviewRequest(BaseModel):
    status: Annotated[str, Field(pattern="^(approved|rejected)$")]
    review_notes: Annotated[str | None, Field(max_length=REASON_MAX_LENGTH)] = None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("review_notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned: str = _clean_reason(value)
        return cleaned or None


class BulkExcuseRequest(BaseModel):
    reason: Annotated[
        str, Field(min_length=REASON_MIN_LENGTH_QUICK, max_length=REASON_MAX_LENGTH)
    ]

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _clean_reason(value)


class ExcuseRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    session_id: int
    initiated_by: str
    initiated_via: str
    reason: str
    attachment_urls: list[str] | None = None
    status: str
    requested_at: datetime
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None


class ExcuseActionResponse(BaseModel):
    excuse_request_id: int
    status: str
    original_status: str | None = None
    new_status: str


class StudentSubmitResponse(BaseModel):
    id: int
    status: str
    requested_at: datetime


class RevokeExcuseResponse(BaseModel):
    reverted_to: str | None = None


class BulkExcuseResponse(BaseModel):
    excused_count: int
    reason: str
