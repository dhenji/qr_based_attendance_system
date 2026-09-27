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

    def __init__(self, student_id: int) -> None:
        super().__init__(message=f"Student {student_id} not found")


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
