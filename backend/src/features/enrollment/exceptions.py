from core.exceptions import AppException, DomainException


class EnrollmentException(AppException):
    """Root umbrella for all enrollment errors."""


class EnrollmentDomainException(EnrollmentException, DomainException):
    pass


class InvalidSemesterException(EnrollmentDomainException):
    """422 - semester code does not match the year level's term structure."""

    code: str = "invalid_semester"

    def __init__(self, semester: str, year_level_id: int) -> None:
        super().__init__(
            message=f"Semester '{semester}' is not valid for year level {year_level_id}",
            field="semester",
        )
