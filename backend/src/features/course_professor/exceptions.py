from datetime import date

from core.exceptions import AppException, DomainException


class CourseProfessorException(AppException):
    """Root umbrella for all course-professor errors."""


class CourseProfessorDomainException(CourseProfessorException, DomainException):
    pass


class OverlappingAssignmentException(CourseProfessorDomainException):
    """422 - assignment interval overlaps an existing one for the same offering+professor."""

    code: str = "overlapping_assignment"

    def __init__(
        self,
        offering_id: int,
        professor_id: int,
        effective_from: date,
        effective_to: date | None,
        overlapping_start: date,
        overlapping_end: date | None,
    ) -> None:
        super().__init__(
            message=(
                f"Offering {offering_id}, professor {professor_id}: "
                f"range [{effective_from}, {effective_to}) overlaps "
                f"existing [{overlapping_start}, {overlapping_end})"
            )
        )
