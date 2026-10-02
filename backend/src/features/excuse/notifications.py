"""Copy for the excuse notification emails.

The wording of every message the excuse workflow sends, one function per event
in `docs/architecture/excuse-workflow.md` §8. Pure subject/body builders: no
database, no clock, no I/O, so the copy can be asserted in a unit test without
seeding an excuse. Recipients are resolved in `service.py` and delivery is
fire-and-forget through `shared.email.dispatch_emails`.

Only the email half of §8's "in-app + email" is built here. There is no
notification table or queue, so nothing is recorded in-app and this module owns
no read side - an unreceived notice is recovered by re-opening the request.

A professor who excuses a student directly (`quick_excuse`,
`excuse_with_evidence`) gets no notice, and neither does a student whose excuse
is edited or revoked: §8 lists four events and these are not among them.
"""

from __future__ import annotations

# Event → subject line. Subjects name the course because that is what a
# recipient scanning a busy inbox looks for first.
SUBJECT_REQUEST_SUBMITTED: str = "New excuse request: {course}"
SUBJECT_REQUEST_APPROVED: str = "Excuse approved: {course}"
SUBJECT_REQUEST_REJECTED: str = "Excuse rejected: {course}"
SUBJECT_BULK_EXCUSED: str = "You have been excused: {course}"

# A rejection with no note is still reported as a rejection; an empty sentence
# reads like a truncated mail.
REJECTION_WITHOUT_NOTES: str = "No reason was given."

# The four return `(subject, body)`; the caller supplies the recipient address.
EmailCopy = tuple[str, str]


def request_submitted(
    *,
    student_name: str,
    course: str,
    session_date: str,
    reason: str,
) -> EmailCopy:
    """Sent to the offering's professors when a student files a request."""

    subject: str = SUBJECT_REQUEST_SUBMITTED.format(course=course)
    body: str = (
        f"{student_name} has requested an excuse for {course} on {session_date}.\n\n"
        f"Reason given:\n{reason}\n\n"
        "Review the request and approve or reject it. Any attachments the "
        "student provided are on the request itself."
    )

    return subject, body


def request_approved(
    *,
    course: str,
    session_date: str,
) -> EmailCopy:
    """Sent to the student when a professor approves their request."""

    subject: str = SUBJECT_REQUEST_APPROVED.format(course=course)
    body: str = (
        f"Your excuse for {course} on {session_date} has been approved.\n\n"
        "The attendance record now shows you as excused for that session."
    )

    return subject, body


def request_rejected(
    *,
    course: str,
    session_date: str,
    review_notes: str | None,
) -> EmailCopy:
    """Sent to the student when a professor rejects their request."""

    subject: str = SUBJECT_REQUEST_REJECTED.format(course=course)
    body: str = (
        f"Your excuse for {course} on {session_date} was rejected.\n\n"
        f"Reason: {review_notes or REJECTION_WITHOUT_NOTES}\n\n"
        "The attendance record is unchanged. Speak to your professor if you "
        "think this is a mistake."
    )

    return subject, body


def bulk_excused(
    *,
    course: str,
    session_date: str,
    reason: str,
) -> EmailCopy:
    """Sent to every student a bulk excuse covered."""

    subject: str = SUBJECT_BULK_EXCUSED.format(course=course)
    body: str = (
        f"You have been excused for {course} on {session_date}.\n\n"
        f"Reason: {reason}"
    )

    return subject, body