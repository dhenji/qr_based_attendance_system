from __future__ import annotations

from core.exceptions import AppException, DatabaseException, DomainException


class StudentException(AppException):
    """Root umbrella for all student errors."""


class StudentDomainException(StudentException, DomainException):
    pass


class NotEnrolledException(StudentDomainException):
    """403 - student is not enrolled in the course for this session."""

    status_code: int = 403
    code: str = "not_enrolled"

    def __init__(self, student_id: int, course_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} is not enrolled in course {course_id}"
        )


class FaceNotEnrolledException(StudentDomainException):
    """403 - student has no face enrollment on record."""

    status_code: int = 403
    code: str = "face_not_enrolled"

    def __init__(self, student_id: int) -> None:
        super().__init__(message=f"Student {student_id} has no face enrollment")


class StudentNotFoundException(StudentDomainException):
    """404 - the target student does not exist."""

    status_code: int = 404
    code: str = "student_not_found"

    def __init__(self, student_id: int | str) -> None:
        super().__init__(message=f"Student {student_id} not found")


class StudentAccountUnlinkedException(StudentDomainException):
    """409 - the roster row has no `users` account to reset.

    A student is created as a roster record first and only gains a login when
    the account is created or claimed, so `user_id` is legitimately null. There
    is no password to hand out in that state.
    """

    status_code: int = 409
    code: str = "student_account_unlinked"

    def __init__(self, student_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} has no linked account to reset"
        )


class StudentIdExistsException(StudentDomainException):
    """409 - another student already uses this student_id.

    `students.student_id` is unique, so the duplicate is rejected before the
    INSERT instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "student_id_exists"

    def __init__(self, student_id: str) -> None:
        super().__init__(message=f"Student ID {student_id} already exists")


class StudentEmailExistsException(StudentDomainException):
    """409 - another student already uses this email.

    `students.email` is unique, so the duplicate is rejected before the
    INSERT instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "student_email_exists"

    def __init__(self, email: str) -> None:
        super().__init__(message=f"Student email {email} already exists")


class YearLevelMismatchException(StudentDomainException):
    """422 - the year level does not belong to the given program.

    `students` has no `program_id` column; the program is resolved through
    `year_levels.program_id`. Both fields are required and must agree.
    """

    code: str = "year_level_program_mismatch"

    def __init__(self, year_level_id: int, program_id: int) -> None:
        super().__init__(
            message=(
                f"Year level {year_level_id} "
                f"does not belong to program {program_id}"
            )
        )


class StudentNotArchivedException(StudentDomainException):
    """409 - permanent delete attempted on a record that is still active.

    Only archived (`is_active=false`) students may be hard-deleted.
    """

    status_code: int = 409
    code: str = "not_archived"

    def __init__(self, student_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} is still active and cannot be permanently deleted"
        )


class StudentHasRecordsException(StudentDomainException):
    """409 - the archived student still has referencing rows.

    `enrollments`, `attendance_records`, `excuse_requests` and
    `student_risk_scores` reference `students.id` with `ondelete="RESTRICT"`,
    so the delete is rejected before the FK violation surfaces as a 500.
    The FKs stay `RESTRICT` on purpose: cascading them would silently
    destroy attendance history.
    """

    status_code: int = 409
    code: str = "student_has_records"

    def __init__(self, student_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} has records and cannot be permanently deleted"
        )


class FaceEmbeddingNotFoundException(StudentDomainException):
    """404 - the student has no face embedding stored.

    Distinct from `StudentNotFoundException`: the identity exists but `student.face_embedding is NULL` (never enrolled, revoked, or cleared on archive).
    """

    status_code: int = 404
    code: str = "face_embedding_not_found"

    def __init__(self, user_id: int) -> None:
        super().__init__(message=f"No face embedding stored for user {user_id}")


class CurrentPasswordInvalidException(StudentDomainException):
    """400 - the provided current password is incorrect."""

    status_code: int = 400
    code: str = "current_password_invalid"

    def __init__(self) -> None:
        super().__init__(message="Current password is incorrect")


class PasswordReusedException(StudentDomainException):
    """400 - the new password matches the current one."""

    status_code: int = 400
    code: str = "password_reused"

    def __init__(self) -> None:
        super().__init__(
            message="New password must be different from the current password"
        )
