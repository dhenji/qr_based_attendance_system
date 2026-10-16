from __future__ import annotations

from core.exceptions import AppException, DatabaseException, DomainException


class SessionException(AppException):
    """Root umbrella for all session errors - domain or database."""


class SessionDomainException(SessionException, DomainException):
    pass


class SessionDatabaseException(SessionException, DatabaseException):
    pass


class SessionNotFoundException(SessionDomainException):
    """404 - the target session does not exist."""

    status_code: int = 404
    code: str = "session_not_found"

    def __init__(self, session_id: int | str) -> None:
        super().__init__(message=f"Session {session_id} not found")


class SessionExpiredException(SessionDomainException):
    """410 - session past its expiration time."""

    status_code: int = 410
    code: str = "session_expired"

    def __init__(self, session_id: int | None = None) -> None:
        message: str = "Session has expired"

        if session_id is not None:
            message = f"Session {session_id} has expired"
            super().__init__(message=message)


class SessionAlreadyActiveException(SessionDomainException):
    """409 - offering already has an active session open."""

    status_code: int = 409
    code: str = "session_already_active"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} already has an active session"
        )


class DuplicateScanException(SessionDatabaseException):
    """409 - student already scanned for this session."""

    code: str = "duplicate_scan"

    def __init__(self, student_id: int, session_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} already scanned for session {session_id}"
        )


class LabCoordinatesRequiredException(SessionDomainException):
    """422 - a laboratory session needs classroom coordinates.

    Laboratory sessions always enforce the geofence (D77), so the resolved
    location — payload override, matching lab component, or offering default —
    must carry both coordinates. Lecture sessions keep the previous behavior
    (coordinates optional).
    """

    status_code: int = 422
    code: str = "lab_coordinates_required"

    def __init__(self) -> None:
        super().__init__(
            message="Laboratory sessions require classroom coordinates",
            field="classroom_lat",
        )
