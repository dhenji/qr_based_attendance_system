from core.exceptions import AppException, DatabaseException, DomainException


class CourseException(AppException):
    """Root umbrella for all course errors."""


class CourseDomainException(CourseException, DomainException):
    pass


class CourseDatabaseException(CourseException, DatabaseException):
    pass


class CourseNotFoundException(CourseDomainException):
    """404 - the target course does not exist."""

    status_code: int = 404
    code: str = "course_not_found"

    def __init__(self, course_id: int) -> None:
        super().__init__(message=f"Course {course_id} not found")


class CourseCodeExistsException(CourseDomainException):
    """409 - another course already uses this code.

    `courses.course_code` is unique, so the duplicate is rejected before the
    INSERT instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "course_code_exists"

    def __init__(self, code: str) -> None:
        super().__init__(message=f"Course code {code} already exists")
