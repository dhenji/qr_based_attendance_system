from core.exceptions import AppException, DatabaseException, DomainException


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
