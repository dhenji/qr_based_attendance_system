from __future__ import annotations

from core.exceptions import AppException, DatabaseException, DomainException


class ProfessorException(AppException):
    """Root umbrella for all professor errors."""


class ProfessorDomainException(ProfessorException, DomainException):
    pass


class ProfessorDatabaseException(ProfessorException, DatabaseException):
    pass


class AssignmentNotFoundException(ProfessorDomainException):
    """404 - course assignment not found."""

    status_code: int = 404
    code: str = "assignment_not_found"

    def __init__(self, professor_id: int, course_id: int) -> None:
        super().__init__(
            message=f"No assignment found for professor {professor_id} on course {course_id}"
        )


class ProfessorNotFoundException(ProfessorDomainException):
    """404 - the target professor does not exist."""

    status_code: int = 404
    code: str = "professor_not_found"

    def __init__(self, professor_id: int) -> None:
        super().__init__(message=f"Professor {professor_id} not found")


class ProfessorAccountUnlinkedException(ProfessorDomainException):
    """409 - the roster row has no `users` account to reset.

    A professor is created as a roster record first and only gains a login when
    the account is created or claimed, so `user_id` is legitimately null.
    """

    status_code: int = 409
    code: str = "professor_account_unlinked"

    def __init__(self, professor_id: int) -> None:
        super().__init__(
            message=f"Professor {professor_id} has no linked account to reset"
        )


class ProfessorEmailExistsException(ProfessorDomainException):
    """409 - another professor already uses this email.

    `professors.email` is unique, so the duplicate is rejected before the
    INSERT instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "professor_email_exists"

    def __init__(self, email: str) -> None:
        super().__init__(message=f"Professor email {email} already exists")


class ProfessorNotArchivedException(ProfessorDomainException):
    """409 - permanent delete attempted on a record that is still active.

    Only archived (`is_active=false`) professors may be hard-deleted.
    """

    status_code: int = 409
    code: str = "not_archived"

    def __init__(self, professor_id: int) -> None:
        super().__init__(
            message=f"Professor {professor_id} is still active and cannot be permanently deleted"
        )


class ProfessorHasRecordsException(ProfessorDomainException):
    """409 - the archived professor still has sessions or assignments.

    `sessions.professor_id` and `course_professors.professor_id` are both
    `ondelete="RESTRICT"`, so the delete is rejected before the FK
    violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "professor_has_records"

    def __init__(self, professor_id: int) -> None:
        super().__init__(
            message=f"Professor {professor_id} has sessions and cannot be permanently deleted"
        )


class CurrentPasswordInvalidException(ProfessorDomainException):
    """400 - the provided current password is incorrect."""

    status_code: int = 400
    code: str = "current_password_invalid"

    def __init__(self) -> None:
        super().__init__(message="Current password is incorrect")


class PasswordReusedException(ProfessorDomainException):
    """400 - the new password matches the current one."""

    status_code: int = 400
    code: str = "password_reused"

    def __init__(self) -> None:
        super().__init__(
            message="New password must be different from the current password"
        )
