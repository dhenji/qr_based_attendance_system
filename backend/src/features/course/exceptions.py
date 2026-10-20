from __future__ import annotations

from datetime import date

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


class CourseNotArchivedException(CourseDomainException):
    """409 - only archived (`is_active=false`) courses may be hard-deleted."""

    status_code: int = 409
    code: str = "not_archived"

    def __init__(self, course_id: int) -> None:
        super().__init__(
            message=f"Course {course_id} is still active and cannot be deleted"
        )


class CourseHasOfferingsException(CourseDomainException):
    """409 - course offerings still reference this course.

    `course_offerings.course_id` is `ondelete="RESTRICT"`, so the delete is
    rejected before the FK violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "course_has_offerings"

    def __init__(self, course_id: int) -> None:
        super().__init__(
            message=f"Course {course_id} has offerings and cannot be deleted"
        )


class OfferingNotArchivedException(CourseDomainException):
    """409 - only archived (`is_active=false`) offerings may be hard-deleted."""

    status_code: int = 409
    code: str = "not_archived"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} is still active and cannot be deleted"
        )


class OfferingHasEnrollmentsException(CourseDomainException):
    """409 - students are still enrolled in this offering.

    `enrollments.offering_id` is `ondelete="RESTRICT"`, so the delete is
    rejected before the FK violation surfaces as a 500.
    """

    status_code: int = 409
    code: str = "offering_has_enrollments"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} has enrolled students and cannot be deleted"
        )


class OfferingHasSessionsException(CourseDomainException):
    """409 - class sessions were already opened for this offering.

    `sessions.offering_id` is `ondelete="RESTRICT"`, and sessions own
    attendance/excuse history, so an offering with sessions is never
    physically deleted.
    """

    status_code: int = 409
    code: str = "offering_has_sessions"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} has sessions and cannot be deleted"
        )


class OfferingHasAssignmentsException(CourseDomainException):
    """409 - professor assignments still reference this offering.

    `course_professors.offering_id` is `ondelete="RESTRICT"` (composite PK),
    so even ended assignments block the delete — history is never rewritten.
    """

    status_code: int = 409
    code: str = "offering_has_assignments"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} has professor assignments and cannot be deleted"
        )


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


class OfferingScheduleWindowException(CourseDomainException):
    """422 - the requested schedule would end at or before it starts.

    Raised for a PATCH that supplies only one of the two times as well as one
    that supplies both, because the stored value of the omitted half still
    has to satisfy the comparison. `OfferingUpdate`'s own validator only sees
    the fields present in the request body, so it cannot catch the
    single-field case.
    """

    status_code: int = 422
    code: str = "invalid_schedule_window"

    def __init__(self) -> None:
        super().__init__(
            message="schedule_end_time must be after schedule_start_time",
            field="schedule_end_time",
        )


class WeeklyHoursExceedUnitsException(CourseDomainException):
    """422 - weekly scheduled meeting hours exceed the course units total.

    `courses.units` is the required total of scheduled meeting hours per week
    across all active components of the offering (D79). The check runs against
    the merged active set, so API requests cannot bypass the frontend totals.
    """

    code: str = "weekly_hours_exceed_units"

    def __init__(
        self,
        scheduled_hours: float,
        limit_hours: float,
        course_code: str | None = None,
        units: int | None = None,
    ) -> None:
        over_hours = round(scheduled_hours - limit_hours, 2)
        if course_code is not None and units is not None:
            message = (
                f"Weekly scheduled hours ({scheduled_hours}h) exceed the "
                f"{units}-unit requirement ({limit_hours}h) for course {course_code}; "
                f"{over_hours}h over"
            )
        else:
            message = (
                f"Weekly scheduled hours ({scheduled_hours}h) exceed the "
                f"weekly requirement ({limit_hours}h); {over_hours}h over"
            )
        super().__init__(message=message, field="components")


class WeeklyHoursBelowUnitsException(CourseDomainException):
    """422 - weekly scheduled meeting hours fall short of the course units total."""

    code: str = "weekly_hours_below_units"

    def __init__(
        self,
        scheduled_hours: float,
        limit_hours: float,
        course_code: str | None = None,
        units: int | None = None,
    ) -> None:
        short_hours = round(limit_hours - scheduled_hours, 2)
        if course_code is not None and units is not None:
            message = (
                f"Weekly scheduled hours ({scheduled_hours}h) fall short of the "
                f"{units}-unit requirement ({limit_hours}h) for course {course_code}; "
                f"{short_hours}h short"
            )
        else:
            message = (
                f"Weekly scheduled hours ({scheduled_hours}h) fall short of the "
                f"weekly requirement ({limit_hours}h); {short_hours}h short"
            )
        super().__init__(message=message, field="components")


class ScheduleMismatchException(CourseDomainException):
    """422 - an offering whose meetings mismatch the requirement cannot go live.

    Activation (is_active False -> True) requires the merged active-component
    total to equal `courses.units * 60` exactly (D82), including the
    zero-meeting case. The message names the course code and both hours and
    carries no row ids: the list/detail toggles render it verbatim.
    """

    code: str = "schedule_mismatch"

    def __init__(
        self,
        scheduled_hours: float,
        limit_hours: float,
        course_code: str | None = None,
        units: int | None = None,
    ) -> None:
        if course_code is not None and units is not None:
            message = (
                f"Cannot activate: weekly scheduled hours ({scheduled_hours}h) "
                f"do not match the {units}-unit requirement ({limit_hours}h) "
                f"for course {course_code}. Fix the meetings first."
            )
        else:
            message = (
                f"Cannot activate: weekly scheduled hours ({scheduled_hours}h) "
                f"do not match the weekly requirement ({limit_hours}h). "
                "Fix the meetings first."
            )
        super().__init__(message=message, field="is_active")


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


class EnrollmentNotFoundException(CourseDomainException):
    """404 - the student has no enrollment row on this offering.

    An unknown roster id raises `StudentNotFoundException` instead, so the
    unenroll path distinguishes "no such student" from "not enrolled here".
    """

    status_code: int = 404
    code: str = "enrollment_not_found"

    def __init__(self, offering_id: int, student_number: str) -> None:
        super().__init__(
            message=f"Student {student_number} is not enrolled "
            f"in offering {offering_id}"
        )


class ComponentNotFoundException(CourseDomainException):
    """404 - the target offering component does not exist."""

    status_code: int = 404
    code: str = "component_not_found"

    def __init__(self, component_id: int) -> None:
        super().__init__(message=f"Offering component {component_id} not found")


class ComponentExistsException(CourseDomainException):
    """409 - the offering already has this scheduled component.

    `offering_components` carries the `uq_offering_component` unique
    constraint (offering_id, session_type, schedule_days,
    schedule_start_time), so the duplicate is rejected before the INSERT
    instead of letting the unique violation surface as a 500.
    """

    status_code: int = 409
    code: str = "component_exists"

    def __init__(self, offering_id: int, session_type: str) -> None:
        super().__init__(
            message=(
                f"Offering {offering_id} already has a {session_type} "
                "component on that schedule"
            )
        )


class ProfessorNotEligibleException(CourseDomainException):
    """422 - the selected professor is not eligible for assignment."""

    status_code: int = 422
    code: str = "professor_not_eligible"

    def __init__(self, professor_id: int) -> None:
        super().__init__(
            message=f"Professor {professor_id} is not eligible for assignment"
        )


class InvalidEffectiveFromException(CourseDomainException):
    """422 - reassignment effective date must be after the current assignment's start date."""

    status_code: int = 422
    code: str = "invalid_effective_from"

    def __init__(self, offering_id: int, professor_id: int) -> None:
        super().__init__(
            message="Choose an effective date after the current assignment's start date."
        )


class AssignmentAlreadyEndedException(CourseDomainException):
    """409 - the targeted assignment row ended before today."""

    status_code: int = 409
    code: str = "assignment_already_ended"

    def __init__(
        self, offering_id: int, professor_id: int, effective_from: date
    ) -> None:
        super().__init__(
            message=(
                f"The assignment starting {effective_from} for professor "
                f"{professor_id} on offering {offering_id} has already ended."
            )
        )
