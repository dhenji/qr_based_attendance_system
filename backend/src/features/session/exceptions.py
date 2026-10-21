from __future__ import annotations

from core.exceptions import AppException, DatabaseException, DomainException


class SessionException(AppException):
    """Root umbrella for all session errors - domain or database."""


class SessionDomainException(SessionException, DomainException):
    pass


class SessionDatabaseException(SessionException, DatabaseException):
    pass


class SessionNotFoundException(SessionDomainException):
    """404 - the target session does not exist."""

    status_code: int = 404
    code: str = "session_not_found"

    def __init__(self, session_id: int | str) -> None:
        super().__init__(message=f"Session {session_id} not found")


class SessionExpiredException(SessionDomainException):
    """410 - session past its expiration time."""

    status_code: int = 410
    code: str = "session_expired"

    def __init__(self, session_id: int | None = None) -> None:
        message: str = "Session has expired"

        if session_id is not None:
            message = f"Session {session_id} has expired"
            super().__init__(message=message)


class SessionAlreadyActiveException(SessionDomainException):
    """409 - offering already has an active session open."""

    status_code: int = 409
    code: str = "session_already_active"

    def __init__(self, offering_id: int) -> None:
        super().__init__(
            message=f"Offering {offering_id} already has an active session"
        )


class DuplicateScanException(SessionDatabaseException):
    """409 - student already scanned for this session."""

    code: str = "duplicate_scan"

    def __init__(self, student_id: int, session_id: int) -> None:
        super().__init__(
            message=f"Student {student_id} already scanned for session {session_id}"
        )


class LabCoordinatesRequiredException(SessionDomainException):
    """422 - a laboratory session needs classroom coordinates.

    Laboratory sessions always enforce the geofence (D77), so the resolved
    location — payload override, matching lab component, or offering default —
    must carry both coordinates. Lecture sessions keep the previous behavior
    (coordinates optional).
    """

    status_code: int = 422
    code: str = "lab_coordinates_required"

    def __init__(self) -> None:
        super().__init__(
            message="Laboratory sessions require classroom coordinates",
            field="classroom_lat",
        )


class OfferingScheduleMismatchException(SessionDomainException):
    """422 - sessions cannot open on a mis-scheduled offering (D82).

    The merged active-component total must equal the course units requirement
    exactly; rows with no configured meetings are exempt (nothing to judge).
    The message is professor-facing and renders verbatim on the session-open
    form: course code plus both hours, no row ids.
    """

    status_code: int = 422
    code: str = "offering_schedule_mismatch"

    def __init__(
        self,
        scheduled_hours: float,
        limit_hours: float,
        course_code: str,
        units: int,
    ) -> None:
        super().__init__(
            message=(
                f"Sessions can't be opened for {course_code} yet — its weekly "
                f"schedule ({scheduled_hours}h) doesn't match the {units}-unit "
                f"requirement ({limit_hours}h). Contact your administrator."
            )
        )


class SessionDateInPastException(SessionDomainException):
    """422 - an overridden session date is in the past (D93).

    A class can move earlier or later than planned, but it cannot be opened
    for a day that has already gone by.
    """

    status_code: int = 422
    code: str = "session_date_in_past"
    field: str = "session_date"

    def __init__(self, session_date: str) -> None:
        super().__init__(
            message=(
                f"A session date of {session_date} is in the past — pick today "
                "or a later day."
            )
        )


class ScheduledStartInPastException(SessionDomainException):
    """422 - an overridden start time has already gone by (D93).

    The default (unoverridden) start may legitimately be in the past — a
    class that began an hour ago and is being opened now. Only an explicit
    override is checked, and only against a short grace.
    """

    status_code: int = 422
    code: str = "scheduled_start_in_past"
    field: str = "start_time"

    def __init__(self, start_time: str) -> None:
        super().__init__(
            message=(
                f"A start time of {start_time} is already in the past — pick a "
                "later time or today's date."
            )
        )


class InvalidSessionTimeException(SessionDomainException):
    """422 - the resolved session window is not a valid interval (D93)."""

    status_code: int = 422
    code: str = "invalid_session_time"
    field: str = "start_time"

    def __init__(self) -> None:
        super().__init__(
            message=(
                "The session must end after it starts — check the scheduled "
                "time."
            )
        )
