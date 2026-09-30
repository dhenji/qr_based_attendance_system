from __future__ import annotations

from core.exceptions import AppException, DomainException


class FaceEnrollmentException(AppException):
    """Root umbrella for all face-enrollment errors."""


class FaceEnrollmentDomainException(FaceEnrollmentException, DomainException):
    pass


class InvalidImageException(FaceEnrollmentDomainException):
    """400 - an uploaded photo is missing, empty, oversized, or not an image."""

    status_code: int = 400
    code: str = "invalid_image"

    def __init__(self, detail: str) -> None:
        super().__init__(message=f"Invalid image: {detail}")
