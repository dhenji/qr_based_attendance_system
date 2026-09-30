"""Attendance scan validation against a real database (coding-standards 5.1).

This is the first suite to drive `AttendanceService` through a real SQL
engine rather than a hand-rolled fake session. The existing tests fake
`scalars`/`scalar`/`execute` and therefore only prove the service calls what
the test told it to call; these prove the generated SQL, the column
mappings, the CHECK/FK constraints and the `Numeric` round-trip all agree.

Every case runs against a schema-per-test database from `conftest.py`, so a
test that writes an `attendance_records` row cannot leak into the next one.

The liveness, geofence, enrollment, duplicate and review-band branches are
each a rejection-or-status decision a student is affected by, so they are
covered on both sides of every boundary.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.attendance.exceptions import (
    FaceMismatchException,
    LivenessFailedException,
    OutsideGeofenceException,
)
from features.attendance.model import Attendance
from features.attendance.schema import (
    GPSInput,
    LivenessEvidence,
    ScanRequest,
)
from features.attendance.service import AttendanceService
from features.session.exceptions import (
    DuplicateScanException,
    SessionExpiredException,
    SessionNotFoundException,
)
from features.session.model import Session
from features.student.exceptions import (
    NotEnrolledException,
    StudentNotFoundException,
)
from features.sync.model import SyncQueue
from shared.enums import ScannedVia, ValidationStatus
from tests.conftest import Factories

# Somewhere inside the default radius of the fixture classroom.
INSIDE_GPS = GPSInput(lat=14.0001, lng=121.0001, accuracy=5.0)
OUTSIDE_GPS = GPSInput(lat=14.02, lng=121.0, accuracy=5.0)

CLASSROOM_LAT = 14.0
CLASSROOM_LNG = 121.0

# Comfortably above `face_match_threshold` (0.70) so a score is unambiguous.
HIGH_SCORE = 0.92
# Inside the review band: `face_review_band_low` <= score < `face_match_threshold`.
REVIEW_BAND_SCORE = 0.68
# Below `face_review_band_low` (0.65).
MISMATCH_SCORE = 0.40

SYNC_STALE_SECONDS = 60

# Past the end of any real sequence, so it can never collide with a seeded id.
UNKNOWN_SESSION_ID = 2**31
UNKNOWN_STUDENT_NUMBER = "STU-99999"


def valid_evidence(**overrides: Any) -> LivenessEvidence:
    """A passing blink -> left -> right challenge (D31)."""

    fields: dict[str, Any] = {
        "blink_detected": True,
        "head_turn_left": True,
        "head_turn_right": True,
        # Mean must land in 0.05..0.5 for the grade to pass.
        "ear_samples": [0.20, 0.22, 0.18],
        "pnp_evidence": {"depth_mean": 0.4},
    }
    fields.update(overrides)
    return LivenessEvidence(**fields)


def scan_request(
    session: Session, student_number: str, scanned_at: datetime, **overrides: Any
) -> ScanRequest:
    fields: dict[str, Any] = {
        "session_id": session.id,
        "student_number": student_number,
        "gps": INSIDE_GPS,
        "liveness_evidence": valid_evidence(),
        "face_match_score": HIGH_SCORE,
        "scanned_at": scanned_at,
        "scanned_via": ScannedVia.QR_CAMERA,
    }
    fields.update(overrides)
    return ScanRequest(**fields)


async def seed(
    factories: Factories, **session_overrides: Any
) -> dict[str, Any]:
    """Full stack with geofence coordinates wired to a live session."""

    stack: dict[str, Any] = await factories.full_stack(**session_overrides)
    stack["session"].classroom_lat = CLASSROOM_LAT
    stack["session"].classroom_lng = CLASSROOM_LNG
    stack["session"].classroom_radius_meters = 50
    stack["offering"].classroom_lat = CLASSROOM_LAT
    stack["offering"].classroom_lng = CLASSROOM_LNG
    return stack


# --- status windows -------------------------------------------------------


async def test_scan_inside_present_window_is_present(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    # created_at anchors the window; 2 minutes in is inside the 5-minute window.
    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_scan_after_present_window_is_late(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    # 8 minutes: past the 5-minute present window, inside present+late (15).
    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=8),
        )
    )

    assert result.status == ValidationStatus.LATE.value


async def test_scan_after_late_window_is_rejected(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    # 20 minutes: past present (5) + late (10).
    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=20),
        )
    )

    assert result.status == ValidationStatus.REJECTED.value


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, ValidationStatus.PRESENT.value), (5, ValidationStatus.PRESENT.value)],
)
async def test_present_window_boundary_is_inclusive(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    minutes: int,
    expected: str,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=minutes),
        )
    )

    assert result.status == expected


async def test_late_window_boundary_is_inclusive(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    # Exactly present (5) + late (10) = 15 minutes, still late not rejected.
    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=15),
        )
    )

    assert result.status == ValidationStatus.LATE.value


# --- review band ----------------------------------------------------------


async def test_score_in_review_band_is_pending_with_original_status(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            face_match_score=REVIEW_BAND_SCORE,
        )
    )

    assert result.status == ValidationStatus.PENDING.value

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    # The computed status is kept for the professor's approve/reject decision.
    assert row.original_status == ValidationStatus.PRESENT.value
    assert row.validation_status == ValidationStatus.PENDING.value
    assert row.liveness_evidence is not None
    assert row.liveness_evidence["review"] is True
    assert Decimal(str(REVIEW_BAND_SCORE)) == row.face_match_score


async def test_review_band_preserves_late_as_original_status(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=8),
            face_match_score=REVIEW_BAND_SCORE,
        )
    )

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    assert result.status == ValidationStatus.PENDING.value
    assert row.original_status == ValidationStatus.LATE.value


async def test_score_below_review_band_raises_face_mismatch(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(FaceMismatchException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                face_match_score=MISMATCH_SCORE,
            )
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "face_mismatch"


async def test_rejected_score_writes_no_attendance_row(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(FaceMismatchException):
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                face_match_score=MISMATCH_SCORE,
            )
        )

    count: int = await test_db_session.scalar(
        select(Attendance.id).where(Attendance.session_id == stack["session"].id)
    )
    assert count is None


# --- geofence -------------------------------------------------------------


async def test_scan_outside_geofence_raises(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(OutsideGeofenceException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                gps=OUTSIDE_GPS,
            )
        )

    assert excinfo.value.status_code == 403
    assert "exceeds max 50m" in excinfo.value.message


async def test_session_without_classroom_coords_skips_geofence(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A session with no geofence set must not reject an arbitrary position."""

    stack: dict[str, Any] = await factories.full_stack()
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            gps=OUTSIDE_GPS,
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


# --- liveness -------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"blink_detected": False},
        {"head_turn_left": False},
        {"head_turn_right": False},
        # Mean EAR below 0.05: a face-down or synthetic capture.
        {"ear_samples": [0.01, 0.02]},
        # Mean EAR above 0.5.
        {"ear_samples": [0.8, 0.9]},
    ],
    ids=["no_blink", "no_left_turn", "no_right_turn", "ear_too_low", "ear_too_high"],
)
async def test_failing_liveness_evidence_raises(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    overrides: dict[str, Any],
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(LivenessFailedException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                liveness_evidence=valid_evidence(**overrides),
            )
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "liveness_failed"


async def test_empty_pnp_evidence_fails_liveness(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(LivenessFailedException):
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                liveness_evidence=valid_evidence(pnp_evidence={}),
            )
        )


async def test_ear_samples_must_stay_in_schema_range() -> None:
    """The schema rejects an out-of-range sample before the service runs."""

    with pytest.raises(ValueError):
        valid_evidence(ear_samples=[1.5])


async def test_empty_ear_samples_fail_the_grade(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A passing blink with no EAR readings is not a passing challenge.

    The schema requires at least one sample, so this bypasses it to reach the
    service's own `if not evidence.ear_samples` guard. Without that guard a
    mean of an empty list would raise `ZeroDivisionError` instead of the
    intended 403.
    """

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    evidence = valid_evidence().model_copy(update={"ear_samples": []})

    with pytest.raises(LivenessFailedException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                liveness_evidence=evidence,
            )
        )

    assert excinfo.value.code == "liveness_failed"


# --- session / student guards --------------------------------------------


async def test_unknown_session_raises_not_found(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    service = AttendanceService(test_db_session, settings)
    # A well-formed id that matches no session. The session lookup runs
    # first, so this must report the session rather than the student.
    unknown = scan_request(stack["session"], stack["student"].student_id, now)
    unknown = unknown.model_copy(update={"session_id": UNKNOWN_SESSION_ID})

    with pytest.raises(SessionNotFoundException) as excinfo:
        await service.submit_scan(payload=unknown)

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "session_not_found"


async def test_unknown_student_number_raises(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(StudentNotFoundException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                UNKNOWN_STUDENT_NUMBER,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            )
        )

    assert excinfo.value.status_code == 404


async def test_unenrolled_student_raises_not_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await factories.full_stack()
    outsider = await factories.student(stack["year_level"])
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(NotEnrolledException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                outsider.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            )
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "not_enrolled"


async def test_inactive_student_raises_not_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    stack["student"].is_active = False
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(NotEnrolledException):
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                stack["student"].student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            )
        )


async def test_second_scan_raises_duplicate(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    payload = scan_request(
        stack["session"],
        student.student_id,
        scanned_at=stack["session"].created_at + timedelta(minutes=2),
    )

    await service.submit_scan(payload=payload)

    with pytest.raises(DuplicateScanException) as excinfo:
        await service.submit_scan(payload=payload)

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "duplicate_scan"


# --- idempotency ----------------------------------------------------------


async def test_idempotency_key_replays_cached_response(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    payload = scan_request(
        stack["session"],
        student.student_id,
        scanned_at=stack["session"].created_at + timedelta(minutes=2),
    )

    first = await service.submit_scan(payload=payload, idempotency_key="key-abc")
    second = await service.submit_scan(payload=payload, idempotency_key="key-abc")

    assert second.id == first.id

    count: int = await test_db_session.scalar(
        select(Attendance.id).where(Attendance.session_id == stack["session"].id)
    )
    assert count is not None


async def test_distinct_idempotency_keys_write_distinct_rows(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A different key is a different submission, so the duplicate guard fires."""

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    payload = scan_request(
        stack["session"],
        student.student_id,
        scanned_at=stack["session"].created_at + timedelta(minutes=2),
    )

    await service.submit_scan(payload=payload, idempotency_key="key-one")

    with pytest.raises(DuplicateScanException):
        await service.submit_scan(payload=payload, idempotency_key="key-two")


# --- persisted shape ------------------------------------------------------


async def test_persisted_scan_records_gps_status_and_evidence(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        )
    )

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    assert row.student_id == student.id
    assert row.session_id == stack["session"].id
    assert row.gps_lat == pytest.approx(INSIDE_GPS.lat)
    assert row.gps_lng == pytest.approx(INSIDE_GPS.lng)
    assert row.validation_status == ValidationStatus.PRESENT.value
    assert row.original_status is None
    assert row.scanned_via == ScannedVia.QR_CAMERA.value
    # The stored JSON is the evidence plus GPS accuracy, per `_build_evidence`.
    assert row.liveness_evidence is not None
    assert row.liveness_evidence["accuracy"] == INSIDE_GPS.accuracy
    assert "review" not in row.liveness_evidence


async def test_fresh_scan_writes_no_sync_queue_row(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """A scan within `SYNC_STALE_SECONDS` of now is live, not an offline replay."""

    stack: dict[str, Any] = await factories.full_stack()
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=now,
        )
    )

    queued: int = await test_db_session.scalar(select(SyncQueue.id))
    assert queued is None


async def test_stale_offline_scan_queues_a_sync_record(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    stack: dict[str, Any] = await factories.full_stack()
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    scanned_at = now - timedelta(seconds=SYNC_STALE_SECONDS + 30)

    result = await service.submit_scan(
        payload=scan_request(stack["session"], student.student_id, scanned_at)
    )

    queued: SyncQueue | None = (
        await test_db_session.scalars(select(SyncQueue))
    ).one_or_none()

    assert queued is not None
    assert queued.record_data["attendance_id"] == result.id
    assert queued.record_data["session_id"] == stack["session"].id
    assert queued.record_data["student_id"] == student.id


async def test_naive_scanned_at_is_treated_as_utc(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """An offline client may send a naive timestamp; it means UTC, not local.

    Without `_ensure_aware` the service would subtract a naive value from an
    aware `created_at` and raise, so the whole offline path would break.
    """

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    created_at = stack["session"].created_at.replace(tzinfo=None)

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=created_at + timedelta(minutes=2),
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_session_created_at_anchors_the_window_not_the_schedule(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """`_compute_status` measures from `created_at`, not `scheduled_start_time`.

    A professor who opens a session late must not immediately mark every
    scan as late, so the anchor is when the session actually started.
    """

    stack: dict[str, Any] = await factories.full_stack()
    student = stack["student"]
    session = stack["session"]
    # Scheduled an hour ago, but only opened two minutes ago.
    session.scheduled_start_time = now - timedelta(hours=1)
    session.scheduled_end_time = now + timedelta(minutes=58)
    session.created_at = now - timedelta(minutes=2)
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        payload=scan_request(
            session,
            student.student_id,
            scanned_at=session.created_at + timedelta(minutes=1),
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


# --- precheck -------------------------------------------------------------


async def test_precheck_reports_enrolled_and_unscanned(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    service = AttendanceService(test_db_session)

    precheck = await service.precheck_scan(
        session_id=stack["session"].id,
        student_number=stack["student"].student_id,
    )

    assert precheck.enrolled is True
    assert precheck.already_scanned is False
    assert precheck.student["student_id"] == stack["student"].student_id
    assert precheck.student["section"] == "A1"


async def test_precheck_reports_unenrolled_without_raising(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    """Precheck reports a flag; only `submit_scan` raises."""

    stack: dict[str, Any] = await factories.full_stack()
    outsider = await factories.student(stack["year_level"])
    service = AttendanceService(test_db_session)

    precheck = await service.precheck_scan(
        session_id=stack["session"].id, student_number=outsider.student_id
    )

    assert precheck.enrolled is False
    assert precheck.already_scanned is False


async def test_precheck_reports_already_scanned(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        )
    )

    precheck = await service.precheck_scan(
        session_id=stack["session"].id, student_number=student.student_id
    )

    assert precheck.already_scanned is True


async def test_precheck_writes_nothing(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    service = AttendanceService(test_db_session)

    await service.precheck_scan(
        session_id=stack["session"].id,
        student_number=stack["student"].student_id,
    )

    row: Attendance | None = (
        await test_db_session.scalars(select(Attendance))
    ).one_or_none()
    assert row is None


async def test_scanned_at_after_expiry_is_refused_while_the_session_is_live(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The offline-replay case: the session is open but the scan is not.

    A student's phone was offline for the whole session. By the time the
    queue syncs, `expires_at` may still be in the future, so the expiry
    check on the session alone would accept a scan that happened after the
    window closed. `_get_active_session` compares `scanned_at` against
    `expires_at` for exactly this.
    """

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    expires_at: datetime = stack["session"].expires_at

    # One minute after the window shut, but still before it has shut *now*.
    assert expires_at is not None
    assert expires_at > datetime.now(timezone.utc)
    assert expires_at + timedelta(minutes=1) > datetime.now(timezone.utc)

    with pytest.raises(SessionExpiredException) as excinfo:
        await service.submit_scan(
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=expires_at + timedelta(minutes=1),
            )
        )

    assert excinfo.value.status_code == 410


async def test_scanned_at_exactly_at_expiry_is_accepted(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The second guard is `>`, so the exact boundary is still in-window."""

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    expires_at: datetime = stack["session"].expires_at

    assert expires_at is not None

    result = await service.submit_scan(
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=expires_at,
        )
    )

    assert result.status == ValidationStatus.REJECTED.value


async def test_precheck_raises_on_expired_session(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    stack: dict[str, Any] = await factories.full_stack(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    service = AttendanceService(test_db_session)

    with pytest.raises(SessionExpiredException):
        await service.precheck_scan(
            session_id=stack["session"].id,
            student_number=stack["student"].student_id,
        )
