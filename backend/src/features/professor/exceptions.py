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
