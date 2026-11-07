"""Pure-copy tests for attendance liveness rejection notifications."""

from features.attendance import notifications


def test_liveness_rejected_subject_and_body() -> None:
    subject, body = notifications.liveness_rejected(
        course="CS101 - Intro",
        session_code="ABC123",
        session_date="2026-03-14",
        reason="unclear evidence",
        retake_available=True,
    )
    assert subject == "Attendance evidence rejected: CS101 - Intro"
    assert "unclear evidence" in body
    assert "ABC123" in body
    assert "retake" in body.lower()


def test_liveness_rejected_without_reason() -> None:
    subject, body = notifications.liveness_rejected(
        course="CS101 - Intro",
        session_code="ABC123",
        session_date="2026-03-14",
        reason=None,
        retake_available=False,
    )
    assert "No reason was given." in body
    assert "no longer open" in body
