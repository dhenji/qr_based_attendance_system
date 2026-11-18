from __future__ import annotations

from core.exceptions import AppException, DomainException


class AttendanceException(AppException):
    """Root umbrella for all attendance errors."""


class AttendanceDomainException(AttendanceException, DomainException):
    pass


class OutsideGeofenceException(AttendanceDomainException):
    """403 - GPS location outside the allowed geofence radius."""

    status_code: int = 403
    code: str = "outside_geofence"

    def __init__(self, distance_m: float, radius_m: int) -> None:
        super().__init__(
            message=f"Location {distance_m:.1f}m from classroom exceeds max {radius_m}m"
        )


class GpsAccuracyTooLowException(AttendanceDomainException):
    """422 - reported GPS accuracy is too coarse to verify attendance."""

    status_code: int = 422
    code: str = "gps_accuracy_too_low"

    def __init__(self, accuracy_m: float, max_m: float) -> None:
        super().__init__(
            message=f"GPS accuracy {accuracy_m:.1f}m exceeds max allowed {max_m:.1f}m"
        )


class LivenessFailedException(AttendanceDomainException):
    """403 = liveness challenge (blink/head-turn) verification failed."""

    status_code: int = 403
    code: str = "liveness_failed"

    def __init__(self) -> None:
        super().__init__(message="Liveness verification failed")


class FaceMismatchException(AttendanceDomainException):
    """403 - scan face does not match the enrolled face."""

    status_code: int = 403
    code: str = "face_mismatch"

    def __init__(self, score: float, threshold: float) -> None:
        super().__init__(
            message=f"Face match score {score:.3f} is below threshold {threshold:.3f}"
        )


class StudentNumberMismatchException(AttendanceDomainException):
    """403 - the body claims a different student than the one authenticated.

    `student_number` stays in the scan/precheck body because the contract
    documents it (api-contracts.md:935/949), but the authenticated user is
    authoritative: a body that names another student is a spoofed request,
    not a typo, so it is rejected rather than silently ignored.
    """

    status_code: int = 403
    code: str = "student_number_mismatch"

    def __init__(self, submitted: str, expected: str | None = None) -> None:
        if expected is None:
            message: str = (
                f"student_number '{submitted}' does not belong to the "
                "authenticated account"
            )
        else:
            message = (
                f"student_number '{submitted}' does not match this account "
                f"('{expected}')"
            )

        super().__init__(message=message)


class ReviewNotFoundException(AttendanceDomainException):
    """404 - the flagged attendance record does not exist."""

    status_code: int = 404
    code: str = "review_not_found"

    def __init__(self, record_id: int) -> None:
        super().__init__(message=f"Review record {record_id} not found")


class ReviewNotPendingException(AttendanceDomainException):
    """409 - the record is not awaiting review (already resolved or never flagged)."""

    status_code: int = 409
    code: str = "review_not_pending"

    def __init__(self, record_id: int) -> None:
        super().__init__(message=f"Review record {record_id} is not pending review")


class AttendanceAttemptLimitReachedException(AttendanceDomainException):
    """409 - the student has exhausted the allowed scan attempts for this session."""

    status_code: int = 409
    code: str = "attendance_attempt_limit_reached"

    def __init__(self, limit: int) -> None:
        super().__init__(
            message=(
                f"Maximum of {limit} attendance attempts reached for this session "
                "(0 attempts remaining)"
            )
        )
