from __future__ import annotations

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


class OfferingNotFoundException(CourseDomainException):
    """404 - the target offering does not exist."""

    status_code: int = 404
    code: str = "offering_not_found"

    def __init__(self, offering_id: int) -> None:
        super().__init__(message=f"Offering {offering_id} not found")


class OfferingExistsException(CourseDomainException):
    """409 - an offering already exists for this course/program/semester/year.

    `course_offerings` carries the `uq_course_offering` unique constraint (course_id, program_id, semester, academic_year), so the duplicate is
    rejected before the INSERT instead of letting the unique violation surface
    as a 500.
    """

    status_code: int = 409
    code: str = "offering_exists"

    def __init__(
        self, course_id: int, program_id: int, semester: str, academic_year: str
    ) -> None:
        super().__init__(
            message=(
                f"Offering for course {course_id}, program {program_id}, "
                f"{semester} {academic_year} already exists"
            )
        )


class WindowsExceedDurationException(CourseDomainException):
    """422 - present + late windows exceed the course session duration."""

    code: str = "windows_exceed_duration"

    def __init__(self, present: int, late: int, duration_minutes: float) -> None:
        super().__init__(
            message=(
                f"Present ({present}m) + late ({late}m) windows exceed "
                f"session duration ({duration_minutes}m)"
            )
        )


class OfferingAssignmentNotFoundException(CourseDomainException):
    """404 - no open professor assignment on this offering."""

    status_code: int = 404
    code: str = "assignment_not_found"

    def __init__(self, offering_id: int, professor_id: int) -> None:
        super().__init__(
            message=f"No assignment found for professor {professor_id} "
            f"on offering {offering_id}"
        )
