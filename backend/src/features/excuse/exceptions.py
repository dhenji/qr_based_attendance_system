from __future__ import annotations

from core.exceptions import AppException, DomainException


class ExcuseException(AppException):
    """Root umbrella for all excuse errors."""


class ExcuseDomainException(ExcuseException, DomainException):
    pass


class ExcuseNotFoundException(ExcuseDomainException):
    """404 - the target excuse request does not exist."""

    status_code: int = 404
    code: str = "excuse_not_found"

    def __init__(
        self,
        request_id: int | None = None,
        *,
        student_id: int | None = None,
        session_id: int | None = None,
    ) -> None:
        """Missing excuse.

        Callers holding a real id pass it positionally. Callers resolving an
        excuse by (student, session) have no id yet, and reporting a placeholder
        such as 0 would send the professor a meaningless "request 0 not found",
        so they name the student and session instead.
        """
        if request_id is not None:
            message = f"Excuse request {request_id} not found"
        else:
            message = (
                f"No professor-issued excuse for student {student_id} "
                f"in session {session_id}"
            )

        super().__init__(message=message)


class SessionNotFoundException(ExcuseDomainException):
    """404 - the target session does not exist."""

    status_code: int = 404
    code: str = "session_not_found"

    def __init__(self, session_id: int) -> None:
        super().__init__(message=f"Session {session_id} not found")


class StudentNotFoundException(ExcuseDomainException):
    """404 - the target student does not exist."""

    status_code: int = 404
    code: str = "student_not_found"

    def __init__(self, student_id: int) -> None:
        super().__init__(message=f"Student {student_id} not found")


class AttendanceNotFoundException(ExcuseDomainException):
    """404 - no attendance record for this student and session."""

    status_code: int = 404
    code: str = "attendance_not_found"

    def __init__(self, student_id: int, session_id: int) -> None:
        super().__init__(
            message=(
                f"No attendance record for student {student_id} "
                f"in session {session_id}"
            )
        )


class ProfessorNotAssignedException(ExcuseDomainException):
    """403 - the professor holds no active assignment for the offering."""

    status_code: int = 403
    code: str = "not_assigned"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Professor is not assigned to offering {offering_id}"
        )


class NotEnrolledException(ExcuseDomainException):
    """403 - the student is not enrolled in the session offering."""

    status_code: int = 403
    code: str = "not_enrolled"

    def __init__(self, student_id: int, offering_id: int) -> None:
        super().__init__(
            message=(
                f"Student {student_id} is not enrolled in offering {offering_id}"
            )
        )


class AlreadyExcusedException(ExcuseDomainException):
    """409 - the attendance record is already excused."""

    status_code: int = 409
    code: str = "already_excused"

    def __init__(self, student_id: int, session_id: int) -> None:
        super().__init__(
            message=(
                f"Student {student_id} is already excused "
                f"for session {session_id}"
            )
        )


class ExcuseNotPendingException(ExcuseDomainException):
    """409 - the excuse request is not awaiting review."""

    status_code: int = 409
    code: str = "excuse_not_pending"

    def __init__(self, request_id: int) -> None:
        super().__init__(
            message=f"Excuse request {request_id} is not pending review"
        )


class DuplicateExcuseException(ExcuseDomainException):
    """409 - an open excuse request already exists for this record."""

    status_code: int = 409
    code: str = "duplicate_excuse"

    def __init__(self, student_id: int, session_id: int) -> None:
        super().__init__(
            message=(
                f"Student {student_id} already has an open excuse request "
                f"for session {session_id}"
            )
        )
