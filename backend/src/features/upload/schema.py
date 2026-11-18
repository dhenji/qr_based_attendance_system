from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from features.upload.constants import (
    CONTENT_TYPE_MAX_LENGTH,
    FILENAME_MAX_LENGTH,
    FILENAME_MIN_LENGTH,
)


def _clean_filename(value: str) -> str:
    return value.strip()


class PresignedUrlRequest(BaseModel):
    filename: Annotated[
        str, Field(min_length=FILENAME_MIN_LENGTH, max_length=FILENAME_MAX_LENGTH)
    ]
    size_bytes: int = Field(gt=0)
    content_type: Annotated[str | None, Field(max_length=CONTENT_TYPE_MAX_LENGTH)] = (
        None
    )

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        return _clean_filename(value)

    # No content_type normalizer here on purpose: stripping the charset
    # parameter and matching it against the extension belongs to
    # `shared.storage.resolve_content_type`, which owns the
    # extension -> content type mapping. Normalizing twice would give the two
    # layers different inputs to reason about.


class PresignedUrlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    upload_url: str
    object_url: str
    object_key: str
    expires_in: int
