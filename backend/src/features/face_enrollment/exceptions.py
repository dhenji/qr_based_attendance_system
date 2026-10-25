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


class NoFaceDetectedException(FaceEnrollmentDomainException):
    """400 - no face detected in uploaded photo."""

    status_code: int = 400
    code: str = "no_face_detected"

    def __init__(self, detail: str = "No face detected") -> None:
        super().__init__(message=f"No face detected: {detail}")


class MultipleFacesException(FaceEnrollmentDomainException):
    """400 - more than one face detected in uploaded photo."""

    status_code: int = 400
    code: str = "multiple_faces"

    def __init__(self, detail: str = "Multiple faces detected") -> None:
        super().__init__(message=f"Multiple faces detected: {detail}")


# Compatibility aliases for alternative naming used by callers/tests.
MultipleFacesDetectedException = MultipleFacesException


class QualityTooLowException(FaceEnrollmentDomainException):
    """422 - a photo failed one of the biometric quality gates."""

    status_code: int = 422
    code: str = "quality_too_low"

    def __init__(self, detail: str = "Image quality too low") -> None:
        super().__init__(message=f"Image quality too low: {detail}")


# Compatibility aliases for alternative naming used by callers/tests.
ImageQualityException = QualityTooLowException
LowQualityImageException = QualityTooLowException
FaceQualityException = QualityTooLowException


class StubEmbeddingException(FaceEnrollmentDomainException):
    """400/403 - stub embedding detected, re-enrollment required."""

    status_code: int = 400
    code: str = "stub_embedding"

    def __init__(self, detail: str = "Re-enrollment required") -> None:
        super().__init__(message=detail)
