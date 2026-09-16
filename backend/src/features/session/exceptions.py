from core.exceptions import AppException, DatabaseException, DomainException


class SessionException(AppException):
    """Root umbrella for all session errors - domain or database."""


class SessionDomainException(SessionException, DomainException):
    pass


class SessionDatabaseException(SessionException, DatabaseException):
    pass


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
