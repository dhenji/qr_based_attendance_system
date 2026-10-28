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
    """409 - offering already has an active session open.

    The message names the course and the active session's scheduled window
    rather than the offering id, so a professor who opens the same course
    twice sees why instead of decoding a number.
    """

    status_code: int = 409
    code: str = "session_already_active"

    def __init__(
        self,
        *,
        course_code: str,
        scheduled_start: str,
        scheduled_end: str,
    ) -> None:
        super().__init__(
            message=(
                f"An active session is already open for {course_code} "
                f"({scheduled_start}–{scheduled_end}). Close it or wait for it "
                "to expire before opening another."
            )
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


class SessionTypeNotConfiguredException(SessionDomainException):
    """422 - the offering does not meet this kind of session (D95).

    An offering declares what it meets through its active meeting
    components (D77). Opening a session of a type it does not configure
    would inherit the lecture's room and the course template's duration —
    so it is refused, and the message says what the offering does meet.
    """

    status_code: int = 422
    code: str = "session_type_not_configured"

    def __init__(self, session_type: str, configured: list[str]) -> None:
        asked = "laboratory" if session_type == "lab" else "lecture"
        names = [
            "a laboratory" if value == "lab" else "a lecture" for value in configured
        ]
        meets = names[0] if len(names) == 1 else f"{names[0]} and {names[1]}"

        super().__init__(
            message=(
                f"This offering has no {asked} session — it meets {meets}. Ask "
                "an administrator to add the meeting, or open a session of the "
                "type it does meet."
            ),
            field="session_type",
        )


class SessionOutsideScheduledTimeException(SessionDomainException):
    """422 - the session is outside its scheduled time (D94).

    A session may only be opened while its class is running. Outside that
    window the professor has two choices — wait for the scheduled time, or
    open the session at a different date and time — so the message names
    both, and the form renders the same panel the plan endpoint does.
    """

    status_code: int = 422
    code: str = "session_outside_scheduled_time"

    def __init__(
        self, *, reason: str, scheduled: str | None, current: str
    ) -> None:
        if reason == "not_scheduled_today":
            message: str = (
                "This session is outside its scheduled time — this course has "
                f"no class today and it is now {current}. Please wait until "
                "the next class or select a different start time to continue."
            )
        else:
            message = (
                "This session is outside its scheduled time — the class is "
                f"scheduled for {scheduled} and it is now {current}. Please "
                "wait until the scheduled time or select a different start "
                "time to continue."
            )

        super().__init__(message=message)


class SessionNotStartedException(SessionDomainException):
    """422 - the session has not reached its scheduled start time yet."""

    status_code: int = 422
    code: str = "session_not_started"

    def __init__(self, session_id: int | None = None) -> None:
        message: str = "Session has not started yet"

        if session_id is not None:
            message = f"Session {session_id} has not started yet"

        super().__init__(message=message)


class RemoteNotAllowedForLabException(SessionDomainException):
    """422 - remote/online mode is only available for lectures."""

    status_code: int = 422
    code: str = "remote_not_allowed_for_lab"

    def __init__(self) -> None:
        super().__init__(
            message="Remote / online mode is only available for lecture sessions",
            field="is_remote",
        )
