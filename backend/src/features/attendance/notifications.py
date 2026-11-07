"""Copy for attendance liveness-review rejection notifications."""

from __future__ import annotations

SUBJECT_LIVENESS_REJECTED: str = "Attendance evidence rejected: {course}"

REJECTION_WITHOUT_NOTES: str = "No reason was given."

EmailCopy = tuple[str, str]


def liveness_rejected(
    *,
    course: str,
    session_code: str,
    session_date: str,
    reason: str | None,
    retake_available: bool,
) -> EmailCopy:
    subject: str = SUBJECT_LIVENESS_REJECTED.format(course=course)
    retake_line: str = (
        "You may retake attendance for this session while it is still open."
        if retake_available
        else "The session is no longer open for attendance submission."
    )
    body: str = (
        f"Your attendance liveness evidence for {course} has been rejected.\n\n"
        f"Session: {session_code} ({session_date})\n"
        f"Reason: {reason or REJECTION_WITHOUT_NOTES}\n\n"
        f"{retake_line}\n\n"
        "Review the rejection reason and submit your attendance again if a "
        "retake is available. Your previous submission and its evidence are "
        "kept for audit purposes."
    )
    return subject, body
