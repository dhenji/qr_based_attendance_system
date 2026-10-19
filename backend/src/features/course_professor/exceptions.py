from __future__ import annotations

from datetime import date

from core.exceptions import AppException, DomainException


class CourseProfessorException(AppException):
    """Root umbrella for all course-professor errors."""


class CourseProfessorDomainException(CourseProfessorException, DomainException):
    pass


class AssignmentNotEndedException(CourseProfessorDomainException):
    """409 - an operation requiring an ended assignment targeted an open row.

    Raised by reopen (the row is already open-ended) and by permanent removal
    (the admin must End the assignment before erasing it).
    """

    status_code: int = 409
    code: str = "assignment_not_ended"

    def __init__(
        self, offering_id: int, professor_id: int, effective_from: date
    ) -> None:
        super().__init__(
            message=(
                f"The assignment starting {effective_from} for professor "
                f"{professor_id} on offering {offering_id} is still "
                "open-ended. End it first."
            )
        )


class AssignmentReopenConflictException(CourseProfessorDomainException):
    """409 - clearing the end date would overlap a later assignment."""

    status_code: int = 409
    code: str = "assignment_reopen_conflict"

    def __init__(
        self,
        offering_id: int,
        professor_id: int,
        effective_from: date,
        later_effective_from: date,
    ) -> None:
        super().__init__(
            message=(
                f"The assignment starting {effective_from} cannot be reopened "
                f"because professor {professor_id} has a later assignment on "
                f"offering {offering_id} starting {later_effective_from}. "
                "End or change that later assignment first."
            )
        )


class PrimaryAssignmentConflictException(CourseProfessorDomainException):
    """409 - a second primary assignment would overlap the current primary."""

    status_code: int = 409
    code: str = "primary_assignment_conflict"

    def __init__(
        self,
        offering_id: int,
        effective_from: date,
        effective_to: date | None,
        existing_start: date,
        existing_end: date | None,
    ) -> None:
        super().__init__(
            message=(
                f"Offering {offering_id} already has a primary professor "
                f"from {existing_start} to {existing_end or 'ongoing'}. "
                f"The requested primary assignment from {effective_from} to "
                f"{effective_to or 'ongoing'} would overlap it. Assign this "
                "professor as an assistant, or end/change the existing "
                "primary assignment first."
            )
        )


class AssignmentHasSessionsException(CourseProfessorDomainException):
    """409 - permanent removal is blocked because sessions used the assignment."""

    status_code: int = 409
    code: str = "assignment_has_sessions"

    def __init__(
        self, offering_id: int, professor_id: int, effective_from: date
    ) -> None:
        super().__init__(
            message=(
                f"The assignment starting {effective_from} has attendance "
                "sessions and cannot be permanently removed. End the assignment "
                "instead so its session history stays attributed."
            )
        )


class OverlappingAssignmentException(CourseProfessorDomainException):
    """409 - assignment interval overlaps an existing one for the same offering+professor."""

    status_code: int = 409
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
                "This professor already has an assignment for this offering "
                f"from {overlapping_start} to {overlapping_end or 'ongoing'}. "
                "End or change it, or choose dates that do not overlap."
            )
        )
