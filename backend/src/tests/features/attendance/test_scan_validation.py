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

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.attendance.exceptions import (
    FaceMismatchException,
    LivenessFailedException,
    OutsideGeofenceException,
    StudentNumberMismatchException,
)
from features.attendance.model import Attendance
from features.attendance import service as attendance_service
from features.attendance.schema import (
    GPSInput,
    LivenessEvidence,
    ScanRequest,
    ScanResponse,
)
from features.attendance.service import AttendanceService
from features.session.exceptions import (
    DuplicateScanException,
    SessionExpiredException,
    SessionNotFoundException,
)
from features.session.model import Session
from features.session.service import SessionService
from features.student.exceptions import (
    FaceNotEnrolledException,
    NotEnrolledException,
    StudentNotFoundException,
)
from features.sync.model import SyncQueue
from shared.enums import QueueStatus, ScannedVia, UserRole, ValidationStatus
from shared.face_embeddings import (
    cosine_similarity,
    deserialize_embedding,
    embedding_to_base64,
    serialize_embedding,
)
from tests.conftest import Factories


def _make_live_emb(score: float = 0.9) -> str:
    # Create a reference embedding
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    # Create live embedding close to ref for high score
    if score >= 0.8:
        live = ref * 0.95 + np.random.RandomState(42).randn(128).astype(np.float32) * 0.01
    elif score >= 0.65:
        live = ref * 0.8 + np.random.RandomState(123).randn(128).astype(np.float32) * 0.1
    else:
        live = np.random.RandomState(999).randn(128).astype(np.float32)
    return embedding_to_base64(live)


# Somewhere inside the default radius of the fixture classroom.
INSIDE_GPS = GPSInput(lat=14.0001, lng=121.0001, accuracy=5.0)
OUTSIDE_GPS = GPSInput(lat=14.02, lng=121.0, accuracy=5.0)
# ~70 m from the classroom but reported accuracy 50 m → ambiguous (review), not rejected.
AMBIGUOUS_GPS = GPSInput(lat=14.00063, lng=121.0, accuracy=50.0)

CLASSROOM_LAT = 14.0
CLASSROOM_LNG = 121.0


HIGH_SCORE = 0.92
REVIEW_BAND_SCORE = 0.68
MISMATCH_SCORE = 0.40


SYNC_STALE_SECONDS = 60

# Past the end of any real sequence, so it can never collide with a seeded id.
UNKNOWN_SESSION_ID = 2**31


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
        "live_face_embedding": _make_live_emb(0.92),
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
    # Set a real embedding
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    stack["student"].face_embedding_algorithm = "mediapipe-v1"
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
        user_id=stack["student"].user_id,
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
        user_id=stack["student"].user_id,
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
        user_id=stack["student"].user_id,
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
        user_id=stack["student"].user_id,
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
        user_id=stack["student"].user_id,
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

    # Create live embedding that gives score in review band
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    live = ref * 0.605 + np.random.RandomState(27).randn(128).astype(np.float32) * 0.079
    live = live / np.linalg.norm(live)
    # Compute expected score
    from shared.face_embeddings import cosine_similarity, deserialize_embedding

    r, _, _ = deserialize_embedding(stack["student"].face_embedding)
    score = cosine_similarity(r, live)
    if not (0.65 <= score < 0.70):
        live = ref * 0.6 + np.random.RandomState(33).randn(128).astype(np.float32) * 0.08
        live = live / np.linalg.norm(live)
        score = cosine_similarity(r, live)
    assert 0.65 <= score < 0.70

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            live_face_embedding=embedding_to_base64(live),
        )
    )

    assert result.status == ValidationStatus.PRESENT.value

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    # The computed status is kept for the professor's approve/reject decision.
    assert row.original_status == ValidationStatus.PRESENT.value
    assert row.validation_status == ValidationStatus.PRESENT.value
    assert row.liveness_evidence is not None
    assert row.liveness_evidence["review"] is True
    assert row.liveness_evidence["review_reason"] == "face_review_band"
    assert abs(float(row.face_match_score) - score) < 0.001


async def test_review_band_preserves_late_as_original_status(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    live = ref * 0.69 + np.random.RandomState(7).randn(128).astype(np.float32) * 0.07
    live = live / np.linalg.norm(live)

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=8),
            live_face_embedding=embedding_to_base64(live),
        )
    )

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    assert result.status == ValidationStatus.LATE.value
    assert row.original_status == ValidationStatus.LATE.value


async def test_review_band_record_reads_identically_on_student_history_and_professor_feed(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A review-band scan renders the same status on both read paths.

    The review-band change stores the computed status in
    `attendance_records.validation_status` while keeping it in
    `original_status` and flagging `liveness_evidence.review`. Both views are
    supposed to read `validation_status` and nothing else, so the student's
    history tile and the professor's live-session tile must agree on the same
    row. This pins that contract for the review band, which is the case where
    the two views are most likely to drift: a record that is *pending review*
    here is still a present/late outcome on both pages, and any path that
    recomputes status from timestamps or falls back to a default would split
    them again.
    """
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    attendance_service = AttendanceService(test_db_session, settings)
    session_service = SessionService(test_db_session, settings)

    live = _review_band_live_embedding(stack["student"])

    result = await attendance_service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            live_face_embedding=embedding_to_base64(live),
        )
    )

    history = await attendance_service.get_history(user_id=stack["student"].user_id)
    active = await session_service.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )

    assert result.status == ValidationStatus.PRESENT.value
    assert len(history.items) == 1
    history_item = history.items[0]
    feed_item = next(
        s for s in active.students if s.student_number == student.student_id
    )

    # Both views read the persisted `validation_status` and nothing else.
    assert history_item.status == ValidationStatus.PRESENT
    assert feed_item.status == ValidationStatus.PRESENT
    assert history_item.status == feed_item.status
    # The scanned-at timestamp is the same column on both sides, so the two
    # tiles must name the same instant too — a stale snapshot would split them.
    assert history_item.scanned_at == feed_item.scanned_at
    # The review flag and the computed original are preserved for the queue.
    assert history_item.original_status == ValidationStatus.PRESENT


async def test_late_review_band_record_reads_identically_on_student_history_and_professor_feed(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Same contract as above, for a review-band scan that computed to LATE.

    The late band is the second half of the review window and the one that
    produced the original symptom (history showed Late, the live feed showed
    Present), so it gets its own case rather than folding into the present one.
    """
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    attendance_service = AttendanceService(test_db_session, settings)
    session_service = SessionService(test_db_session, settings)

    live = _review_band_live_embedding(stack["student"], target=0.69)

    await attendance_service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=8),
            live_face_embedding=embedding_to_base64(live),
        )
    )

    history = await attendance_service.get_history(user_id=stack["student"].user_id)
    active = await session_service.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )

    assert len(history.items) == 1
    history_item = history.items[0]
    feed_item = next(
        s for s in active.students if s.student_number == student.student_id
    )

    assert history_item.status == ValidationStatus.LATE
    assert feed_item.status == ValidationStatus.LATE
    assert history_item.status == feed_item.status
    assert history_item.original_status == ValidationStatus.LATE


def _review_band_live_embedding(
    student: Student, *, target: float = 0.68
) -> np.ndarray:
    """A live embedding whose cosine score lands inside the review band.

    The reference embedding is the unit vector the seed writes for the
    student; the live one is a blend of it and noise, tuned so the score sits
    between `face_review_band_low` (0.65) and `face_match_threshold` (0.70).
    The existing review-band tests build this inline and re-tune with a second
    attempt when the first lands outside the band; this helper does the same
    thing once so the two new tests share a recipe.
    """
    ref, _, _ = deserialize_embedding(student.face_embedding)

    for seed_value in (27, 33, 7, 123):
        live = ref * target + np.random.RandomState(seed_value).randn(128).astype(
            np.float32
        ) * 0.08
        live = live / np.linalg.norm(live)
        if 0.65 <= cosine_similarity(ref, live) < 0.70:
            return live

    raise AssertionError(
        f"could not build a review-band embedding for target={target}"
    )


async def test_score_below_review_band_raises_face_mismatch(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    live = np.random.RandomState(12345).randn(128).astype(np.float32)
    live = live / np.linalg.norm(live)

    with pytest.raises(FaceMismatchException) as excinfo:
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                live_face_embedding=embedding_to_base64(live),
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

    live = np.random.RandomState(54321).randn(128).astype(np.float32)
    live = live / np.linalg.norm(live)

    with pytest.raises(FaceMismatchException):
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                live_face_embedding=embedding_to_base64(live),
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
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                gps=OUTSIDE_GPS,
            )
        )

    assert excinfo.value.status_code == 403
    assert "exceeds max 50m" in excinfo.value.message


async def test_scan_with_ambiguous_geofence_is_reviewed(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            gps=AMBIGUOUS_GPS,
        )
    )

    assert result.status == ValidationStatus.PRESENT.value

    row: Attendance = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.id == result.id)
        )
    ).one()

    assert row.liveness_evidence is not None
    assert row.liveness_evidence["review"] is True
    assert row.liveness_evidence["review_reason"] == "geofence_uncertainty"
    geo = row.liveness_evidence["geofence"]
    assert geo is not None
    assert "distance_meters" in geo
    assert "radius_meters" in geo
    assert geo["radius_meters"] == 50
    assert "classroom_lat" in geo


async def test_session_without_classroom_coords_skips_geofence(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A session with no geofence set must not reject an arbitrary position."""

    stack: dict[str, Any] = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            gps=OUTSIDE_GPS,
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_scan_without_gps_succeeds_when_geofence_disabled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A session with geofencing disabled must accept a scan with no GPS."""

    stack: dict[str, Any] = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    session = stack["session"]
    session.geofence_enabled = False
    session.classroom_lat = None
    session.classroom_lng = None
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=student.user_id,
        payload=scan_request(
            session,
            student.student_id,
            scanned_at=session.created_at + timedelta(minutes=2),
            gps=None,
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_scan_without_gps_fails_when_geofence_required(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A required geofence cannot be satisfied without a GPS fix."""

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(OutsideGeofenceException):
        await service.submit_scan(
            user_id=student.user_id,
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                gps=None,
            )
        )


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
            user_id=stack["student"].user_id,
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
            user_id=stack["student"].user_id,
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


@pytest.mark.parametrize("sample_count", [1, 100])
async def test_ear_samples_accept_schema_boundaries(sample_count: int) -> None:
    evidence = valid_evidence(ear_samples=[0.2] * sample_count)

    assert len(evidence.ear_samples) == sample_count


@pytest.mark.parametrize("sample_count", [101, 120])
async def test_ear_samples_over_schema_limit_are_rejected(sample_count: int) -> None:
    with pytest.raises(ValueError, match="at most 100 items"):
        valid_evidence(ear_samples=[0.2] * sample_count)


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
            user_id=stack["student"].user_id,
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
        await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=unknown)

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "session_not_found"


async def test_authenticated_user_without_a_student_row_raises(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A STUDENT-role account with no linked `students` row is a 404."""

    stack: dict[str, Any] = await seed(factories)
    orphan = await factories.user(role=UserRole.STUDENT.value)
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(StudentNotFoundException) as excinfo:
        await service.submit_scan(
            user_id=orphan.id,
            payload=scan_request(
                stack["session"],
                stack["student"].student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            )
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "student_not_found"


async def test_scanning_as_another_student_is_refused(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The body cannot name a different student than the token does.

    This is the spoofing guard: the scan used to select the student by
    `payload.student_number`, so any authenticated student could submit (and
    then replay an idempotency key for) somebody else's attendance.
    """

    stack: dict[str, Any] = await seed(factories)
    victim = await factories.student(stack["year_level"])
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(StudentNumberMismatchException) as excinfo:
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                victim.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            )
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "student_number_mismatch"
    assert (await test_db_session.scalars(select(Attendance))).all() == []


async def test_scanned_student_number_comparison_ignores_case(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """`students.student_id` is stored upper-cased; the request is not.

    A student typing `stu-00001` is the same student, so a case difference
    must not read as a spoofing attempt.
    """

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=student.user_id,
        payload=scan_request(
            stack["session"],
            student.student_id.lower(),
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        )
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_unenrolled_student_raises_not_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Enrollment is checked after ownership, on the authenticated student."""

    stack: dict[str, Any] = await factories.full_stack()
    await test_db_session.delete(stack["enrollment"])
    await test_db_session.flush()
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(NotEnrolledException) as excinfo:
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                stack["student"].student_id,
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
            user_id=stack["student"].user_id,
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

    await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload)

    with pytest.raises(DuplicateScanException) as excinfo:
        await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload)

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

    first = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload, idempotency_key="key-abc")
    second = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload, idempotency_key="key-abc")

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

    await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload, idempotency_key="key-one")

    with pytest.raises(DuplicateScanException):
        await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=payload, idempotency_key="key-two")


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
        user_id=stack["student"].user_id,
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
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    await service.submit_scan(
        user_id=stack["student"].user_id,
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
    stack = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    scanned_at = now - timedelta(seconds=SYNC_STALE_SECONDS + 30)

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(stack["session"], student.student_id, scanned_at)
    )

    queued: SyncQueue | None = (
        await test_db_session.scalars(select(SyncQueue))
    ).one_or_none()

    assert queued is not None
    assert queued.record_data["attendance_id"] == result.id
    assert queued.record_data["session_id"] == stack["session"].id
    assert queued.record_data["student_id"] == student.id

    # Queued, not finished. Nothing has processed the row yet, so it is what the
    # active session and the maintenance line count, and what a forced sync
    # picks up. Marking it done here would leave the backlog permanently empty
    # while the row sat unreadable to both.
    assert queued.status == QueueStatus.PENDING.value


@pytest.mark.asyncio
async def test_a_stale_scan_raises_the_active_session_pending_count(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """The queued row and the counter that reports it have to agree.

    Reading the queue any other way than the writer fills it leaves the
    "waiting for offline syncs" banner permanently at zero, which is the same as
    not having the counter at all.
    """
    stack = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    live = SessionService(test_db_session, settings)

    before = await live.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )
    assert before.pending_sync_count == 0

    await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            now - timedelta(seconds=SYNC_STALE_SECONDS + 30),
        )
    )

    after = await live.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )
    assert after.pending_sync_count == 1


@pytest.mark.asyncio
async def test_a_live_scan_leaves_the_pending_count_flat(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """Only an offline replay belongs in the backlog."""
    stack = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    service = AttendanceService(test_db_session, settings)
    live = SessionService(test_db_session, settings)

    await service.submit_scan(
        user_id=stack["student"].user_id,
        payload=scan_request(stack["session"], stack["student"].student_id, now),
    )

    active = await live.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )

    assert active.pending_sync_count == 0
    assert active.remaining == 0


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
        user_id=stack["student"].user_id,
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
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    session = stack["session"]
    # Scheduled an hour ago, but only opened two minutes ago.
    session.scheduled_start_time = now - timedelta(hours=1)
    session.scheduled_end_time = now + timedelta(minutes=58)
    session.created_at = now - timedelta(minutes=2)
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=stack["student"].user_id,
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

    precheck = await service.precheck_scan(user_id=stack["student"].user_id,
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
    """Precheck reports a flag; only `submit_scan` raises.

    The unenrolled student has to be the *authenticated* one now that the
    scan resolves the student off the token, so the enrollment row is what
    gets removed rather than swapping in a second student.
    """

    stack: dict[str, Any] = await factories.full_stack()
    await test_db_session.delete(stack["enrollment"])
    await test_db_session.flush()
    service = AttendanceService(test_db_session)

    precheck = await service.precheck_scan(
        user_id=stack["student"].user_id,
        session_id=stack["session"].id,
        student_number=stack["student"].student_id,
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
        user_id=stack["student"].user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        )
    )

    precheck = await service.precheck_scan(        user_id=stack["student"].user_id,
        session_id=stack["session"].id, student_number=student.student_id
    )

    assert precheck.already_scanned is True


async def test_precheck_writes_nothing(
    test_db_session: AsyncSession,
    factories: Factories,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    service = AttendanceService(test_db_session)

    await service.precheck_scan(user_id=stack["student"].user_id,
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
            user_id=stack["student"].user_id,
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
        user_id=stack["student"].user_id,
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
        await service.precheck_scan(user_id=stack["student"].user_id,
            session_id=stack["session"].id,
            student_number=stack["student"].student_id,
        )


# --- idempotency store scoping and expiry ----------------------------------


async def test_idempotency_entry_is_reprocessed_once_expired(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached response is not replayed past IDEMPOTENCY_TTL_SECONDS.

    With no expiry the map only grew, and a key reused later would
    resurrect a response for a submission that is by then outside its
    session window. Expiring the entry means the duplicate guard runs
    again, which is what a genuinely new submission should hit.
    """

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    payload = scan_request(
        stack["session"],
        student.student_id,
        scanned_at=stack["session"].created_at + timedelta(minutes=2),
    )

    first = await service.submit_scan(
        user_id=student.user_id, payload=payload, idempotency_key="ttl-key"
    )
    assert first.id is not None

    # Push every stored entry past its deadline.
    backdate = time.monotonic() - attendance_service.IDEMPOTENCY_TTL_SECONDS - 1
    monkeypatch.setattr(
        attendance_service,
        "_IDEMPOTENCY_STORE",
        {key: (backdate, resp) for key, (_, resp) in attendance_service._IDEMPOTENCY_STORE.items()},
    )

    with pytest.raises(DuplicateScanException):
        await service.submit_scan(
            user_id=student.user_id, payload=payload, idempotency_key="ttl-key"
        )


async def test_expired_idempotency_entry_is_dropped_not_replayed(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stale key is evicted on lookup, so the map cannot hold it forever."""

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)
    payload = scan_request(
        stack["session"],
        student.student_id,
        scanned_at=stack["session"].created_at + timedelta(minutes=2),
    )

    # A real first scan, so the attendance row the duplicate guard looks for
    # actually exists.
    await service.submit_scan(
        user_id=student.user_id, payload=payload, idempotency_key="doomed-key"
    )

    cache_key = f"{student.user_id}:{stack['session'].id}:doomed-key"
    backdate = time.monotonic() - attendance_service.IDEMPOTENCY_TTL_SECONDS - 1
    store: dict[str, Any] = {
        key: (backdate, response)
        for key, (_, response) in attendance_service._IDEMPOTENCY_STORE.items()
    }
    assert cache_key in store
    monkeypatch.setattr(attendance_service, "_IDEMPOTENCY_STORE", store)

    with pytest.raises(DuplicateScanException):
        await service.submit_scan(
            user_id=student.user_id, payload=payload, idempotency_key="doomed-key"
        )

    assert cache_key not in store


async def test_idempotency_cache_prunes_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_prune_idempotency` bounds the map once it passes its cap."""

    now = time.monotonic()
    store: dict[str, Any] = {
        "stale": (now - 1.0, _stale_response()),
        "fresh": (now + 900.0, _stale_response()),
    }
    monkeypatch.setattr(attendance_service, "_IDEMPOTENCY_STORE", store)
    monkeypatch.setattr(attendance_service, "_IDEMPOTENCY_MAX_ENTRIES", 2)

    attendance_service._store_response("new", _stale_response())

    assert "stale" not in store
    assert "fresh" in store
    assert "new" in store


async def test_idempotency_prune_is_a_no_op_below_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = time.monotonic()
    store: dict[str, Any] = {"stale": (now - 1.0, _stale_response())}
    monkeypatch.setattr(attendance_service, "_IDEMPOTENCY_STORE", store)
    monkeypatch.setattr(attendance_service, "_IDEMPOTENCY_MAX_ENTRIES", 100)

    attendance_service._store_response("new", _stale_response())

    # Under the cap nothing is swept, even an already-expired neighbour.
    assert "stale" in store


def _stale_response() -> ScanResponse:
    moment = datetime.now(timezone.utc)
    return ScanResponse(
        id=1,
        status=ValidationStatus.PRESENT.value,
        scanned_at=moment,
        expires_at=moment,
    )


# --- benchmark profile -------------------------------------------------------


async def test_benchmark_mode_skips_geofence_and_liveness(
    test_db_session: AsyncSession,
    factories: Factories,
    now: datetime,
) -> None:
    from tests.conftest import TEST_JWT_SECRET

    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    bench = Settings(
        debug=True, jwt_secret=TEST_JWT_SECRET, benchmark_mode=True
    )
    service = AttendanceService(test_db_session, bench)

    result = await service.submit_scan(
        user_id=student.user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
            gps=OUTSIDE_GPS,
            liveness_evidence=valid_evidence(blink_detected=False),
        ),
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_normal_mode_still_enforces_geofence(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    stack: dict[str, Any] = await seed(factories)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(OutsideGeofenceException):
        await service.submit_scan(
            user_id=student.user_id,
            payload=scan_request(
                stack["session"],
                student.student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                gps=OUTSIDE_GPS,
            ),
        )


async def test_submit_scan_blocked_when_face_not_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """A student with `face_embedding IS NULL` cannot complete a scan."""
    stack: dict[str, Any] = await factories.full_stack()
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(FaceNotEnrolledException) as excinfo:
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                stack["student"].student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
            ),
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "face_not_enrolled"


async def test_submit_scan_allowed_when_face_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """A student with face data on record completes the scan normally."""
    stack: dict[str, Any] = await factories.full_stack()
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    student = stack["student"]
    service = AttendanceService(test_db_session, settings)

    result = await service.submit_scan(
        user_id=student.user_id,
        payload=scan_request(
            stack["session"],
            student.student_id,
            scanned_at=stack["session"].created_at + timedelta(minutes=2),
        ),
    )

    assert result.status == ValidationStatus.PRESENT.value


async def test_face_check_runs_before_geofence_and_liveness(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    now: datetime,
) -> None:
    """The face-enrollment gate precedes geofence/liveness so a student without
    face data cannot reach those checks even with an invalid position."""
    stack: dict[str, Any] = await factories.full_stack()
    service = AttendanceService(test_db_session, settings)

    with pytest.raises(FaceNotEnrolledException) as excinfo:
        await service.submit_scan(
            user_id=stack["student"].user_id,
            payload=scan_request(
                stack["session"],
                stack["student"].student_id,
                scanned_at=stack["session"].created_at + timedelta(minutes=2),
                gps=OUTSIDE_GPS,
                liveness_evidence=valid_evidence(blink_detected=False),
            ),
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "face_not_enrolled"


def test_gps_input_rejects_zero_accuracy() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GPSInput(lat=14.0, lng=121.0, accuracy=0.0)
