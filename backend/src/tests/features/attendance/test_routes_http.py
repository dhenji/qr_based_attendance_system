"""HTTP-level cover for the Phase 5 student routes (PROMPT 5.1-5.9).

The scan service has extensive service-level coverage in
`test_scan_validation.py`; this file covers the other eight routes, which
had none. Two things only a real request can show:

- the routing and role gating (`require_role` resolving off a real JWT),
- the response *shape*, which is what the frontend actually reads.

`test_fixtures.py` already covers `POST /student/attendance/scan` and
`POST /student/sessions/verify-code` over HTTP; the ownership regressions
here are the ones that fix added.

Ownership is the reason most tests build the stack by hand rather than
through `full_stack()`: the scan and precheck routes resolve the student from
the authenticated user, so the seeded student has to be linked to the account
whose bearer token the request carries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password
from features.attendance.model import Attendance, AttendanceAttemptCounter
from shared.enums import UserRole, ValidationStatus
from shared.face_embeddings import embedding_to_base64, serialize_embedding
from tests.conftest import Factories
import numpy as np

# One point either side of the classroom coordinates below.
INSIDE_LAT = 14.0001
INSIDE_LNG = 121.0001
CLASSROOM_LAT = 14.0
CLASSROOM_LNG = 121.0
HIGH_SCORE = 0.92
REVIEW_BAND_SCORE = 0.68


def _make_live_emb_http() -> str:
    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    live = ref * 0.95 + np.random.RandomState(42).randn(128).astype(np.float32) * 0.01
    live = live / np.linalg.norm(live)
    return embedding_to_base64(live)


def liveness_evidence_payload() -> dict[str, Any]:
    """A passing blink -> left -> right challenge (D31)."""

    return {
        "blink_detected": True,
        "head_turn_left": True,
        "head_turn_right": True,
        "ear_samples": [0.20, 0.21, 0.19],
        "pnp_evidence": {"depth_mean": 0.4},
    }


def scan_body(
    session_id: int,
    student_number: str,
    scanned_at,
    **overrides,
):
    body = {
        "session_id": session_id,
        "student_number": student_number,
        "gps": {"lat": INSIDE_LAT, "lng": INSIDE_LNG, "accuracy": 5.0},
        "liveness_evidence": liveness_evidence_payload(),
        "live_face_embedding": _make_live_emb_http(),
        "scanned_at": scanned_at.isoformat() if hasattr(scanned_at, 'isoformat') else scanned_at,
        "scanned_via": "qr_camera",
    }
    body.update(overrides)
    return body




async def linked_stack(
    factories: Factories, **session_overrides: Any
) -> dict[str, Any]:
    """`full_stack` plus a geofence the scan body sits inside."""

    stack: dict[str, Any] = await factories.full_stack(**session_overrides)
    stack["session"].classroom_lat = CLASSROOM_LAT
    stack["session"].classroom_lng = CLASSROOM_LNG
    stack["session"].classroom_radius_meters = 50
    return stack


# --- 5.9 precheck --------------------------------------------------------


async def test_precheck_reports_enrolled_and_unscanned(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)

    response = await api_client.post(
        "/api/student/attendance/precheck",
        json={
            "session_id": stack["session"].id,
            "student_number": stack["student"].student_id,
        },
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enrolled"] is True
    assert body["already_scanned"] is False
    assert body["student"]["student_id"] == stack["student"].student_id
    assert body["student"]["section"] == "A1"


async def test_precheck_writes_nothing(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """PROMPT 5.9: a read-only gate, no attendance_records and no sync_queue."""

    stack = await linked_stack(factories)

    response = await api_client.post(
        "/api/student/attendance/precheck",
        json={
            "session_id": stack["session"].id,
            "student_number": stack["student"].student_id,
        },
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    assert (await test_db_session.scalars(select(Attendance))).all() == []


async def test_precheck_flips_already_scanned_after_a_scan(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: AsyncSession
) -> None:
    """The second step of the flow: scan, then precheck reports the duplicate."""

    stack = await linked_stack(factories)
    import numpy as np
    from shared.face_embeddings import serialize_embedding

    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    await test_db_session.commit()
    headers = await auth_headers(stack["user"])
    precheck_body = {
        "session_id": stack["session"].id,
        "student_number": stack["student"].student_id,
    }

    scanned_at = stack["session"].created_at + timedelta(minutes=2)
    scan = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(stack["session"].id, stack["student"].student_id, scanned_at),
        headers=headers,
    )
    assert scan.status_code == 200

    precheck = await api_client.post(
        "/api/student/attendance/precheck", json=precheck_body, headers=headers
    )

    assert precheck.status_code == 200
    assert precheck.json()["already_scanned"] is True


@pytest.mark.parametrize(
    ("sample_count", "expected_status"),
    [(100, 200), (101, 422), (120, 422)],
)
async def test_scan_enforces_ear_sample_limit(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
    sample_count: int,
    expected_status: int,
) -> None:
    stack = await linked_stack(factories)
    import numpy as np
    from shared.face_embeddings import serialize_embedding

    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    await test_db_session.commit()
    body = scan_body(
        stack["session"].id,
        stack["student"].student_id,
        stack["session"].created_at + timedelta(minutes=2),
    )
    body["liveness_evidence"]["ear_samples"] = [0.2] * sample_count

    response = await api_client.post(
        "/api/student/attendance/scan",
        json=body,
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == expected_status
    if expected_status == 422:
        error = response.json()["detail"][0]
        assert error["type"] == "too_long"
        assert error["loc"] == ["body", "liveness_evidence", "ear_samples"]
        assert (await test_db_session.scalars(select(Attendance))).all() == []
    else:
        assert response.json()["status"] == ValidationStatus.PRESENT.value
        assert len((await test_db_session.scalars(select(Attendance))).all()) == 1


async def test_precheck_for_an_expired_session_is_410(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """PROMPT 5.9 error codes: 410 session_expired."""

    past = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    stack = await linked_stack(
        factories,
        scheduled_start_time=past - timedelta(hours=1),
        scheduled_end_time=past,
        expires_at=past,
    )

    response = await api_client.post(
        "/api/student/attendance/precheck",
        json={
            "session_id": stack["session"].id,
            "student_number": stack["student"].student_id,
        },
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "session_expired"


async def test_precheck_for_an_unknown_session_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """PROMPT 5.9 error codes: 404 session_not_found."""

    stack = await linked_stack(factories)

    response = await api_client.post(
        "/api/student/attendance/precheck",
        json={
            "session_id": 2**31,
            "student_number": stack["student"].student_id,
        },
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


# --- ownership (added with the spoofing fix) -----------------------------


async def test_precheck_as_another_student_is_403(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    victim = await factories.student(stack["year_level"])

    response = await api_client.post(
        "/api/student/attendance/precheck",
        json={
            "session_id": stack["session"].id,
            "student_number": victim.student_id,
        },
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "student_number_mismatch"


async def test_scan_as_another_student_is_403(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """A scan for somebody else is refused and writes no attendance row."""

    stack = await linked_stack(factories)
    victim = await factories.student(stack["year_level"])

    response = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(
            stack["session"].id,
            victim.student_id,
            stack["session"].created_at + timedelta(minutes=2),
        ),
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "student_number_mismatch"
    assert (await test_db_session.scalars(select(Attendance))).all() == []


async def test_scan_and_precheck_require_the_student_role(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    stack = await linked_stack(factories)
    headers = await auth_headers(role=UserRole.PROFESSOR.value)
    # Read the values the bodies need before committing: `created_at` is a
    # server_default refreshed on flush, so touching it afterwards would be a
    # lazy load outside the event loop.
    session_id = stack["session"].id
    student_number = stack["student"].student_id
    scanned_at = stack["session"].created_at

    # Two failing requests in one test, so the seed has to outlive the first
    # one's rollback: `api_client` commits on success only, and a rejected
    # request rolls the shared test transaction back - seeded rows included.
    # Without this the second request 401s on `user_not_found` because the
    # professor row the first one discarded is the one it is authenticating.
    await test_db_session.commit()

    scanned = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(session_id, student_number, scanned_at),
        headers=headers,
    )
    prechecked = await api_client.post(
        "/api/student/attendance/precheck",
        json={"session_id": session_id, "student_number": student_number},
        headers=headers,
    )

    assert scanned.status_code == 403
    assert scanned.json()["detail"]["code"] == "insufficient_permissions"
    assert prechecked.status_code == 403
    assert prechecked.json()["detail"]["code"] == "insufficient_permissions"


async def test_idempotency_key_is_scoped_to_the_caller(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Two students replaying one key must not share a cached response.

    The store is keyed by user/session/key; before that it was keyed by the
    caller's key alone, so student B replaying student A's key was served A's
    cached ScanResponse - including A's attendance id.
    """

    stack = await linked_stack(factories)
    import numpy as np
    from shared.face_embeddings import serialize_embedding

    ref = np.ones(128, dtype=np.float32) * 0.1
    ref = ref / np.linalg.norm(ref)
    stack["student"].face_embedding = serialize_embedding(ref)
    # A second student enrolled in the same offering, so both may scan it.
    other_user = await factories.user(role=UserRole.STUDENT.value)
    other = await factories.student(stack["year_level"], user=other_user)
    other.face_embedding = serialize_embedding(ref)
    await factories.enrollment(other, stack["offering"])
    shared_key = "shared-key"

    first = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(
            stack["session"].id,
            stack["student"].student_id,
            stack["session"].created_at + timedelta(minutes=2),
        ),
        headers={**(await auth_headers(stack["user"])), "X-Idempotency-Key": shared_key},
    )
    second = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(
            stack["session"].id,
            other.student_id,
            stack["session"].created_at + timedelta(minutes=3),
        ),
        headers={**(await auth_headers(other_user)), "X-Idempotency-Key": shared_key},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] != first.json()["id"]


# --- 5.3 history ---------------------------------------------------------


async def test_history_returns_only_the_callers_rows(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    mine = await factories.attendance(stack["student"], stack["session"])
    stranger = await factories.student(stack["year_level"])
    await factories.enrollment(stranger, stack["offering"])
    theirs = await factories.attendance(stranger, stack["session"])

    response = await api_client.get(
        "/api/student/attendance/history",
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [mine.id]
    assert theirs.id not in [item["id"] for item in body["items"]]


async def test_history_summary_reports_rates_and_counts(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    await factories.attendance(
        stack["student"], stack["session"], validation_status="present"
    )
    await factories.attendance(
        stack["student"],
        stack["session"],
        validation_status="late",
        timestamp=stack["session"].created_at + timedelta(minutes=20),
    )

    response = await api_client.get(
        "/api/student/attendance/history",
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["counts"]["present"] == 1
    assert summary["counts"]["late"] == 1
    assert summary["compliance_rate"] > 0.0
    assert summary["participation_rate"] > 0.0


async def test_history_accepts_a_status_filter(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    await factories.attendance(
        stack["student"], stack["session"], validation_status="present"
    )
    await factories.attendance(
        stack["student"],
        stack["session"],
        validation_status="excused",
        timestamp=stack["session"].created_at + timedelta(minutes=30),
    )

    response = await api_client.get(
        "/api/student/attendance/history",
        params={"status": ValidationStatus.EXCUSED.value},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == ValidationStatus.EXCUSED.value


# --- 5.4 face embedding --------------------------------------------------


async def test_face_embedding_is_returned_when_stale(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    stack["student"].face_embedding = b"stored-blob"
    stack["student"].face_enrolled_at = datetime.now(timezone.utc)
    stack["student"].face_embedding_version = 3

    response = await api_client.get(
        "/api/student/me/face-embedding",
        params={"current_version": 1},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 3
    assert body["embedding"]


async def test_face_embedding_is_204_when_current(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """PROMPT 5.4: 204 rather than an empty 200 when the client is up to date."""

    stack = await linked_stack(factories)
    stack["student"].face_embedding = b"stored-blob"
    stack["student"].face_enrolled_at = datetime.now(timezone.utc)
    stack["student"].face_embedding_version = 3

    response = await api_client.get(
        "/api/student/me/face-embedding",
        params={"current_version": 3},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 204


async def test_face_embedding_is_404_when_never_enrolled(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """PROMPT 5.4: 404 when `face_embedding IS NULL`."""

    stack = await linked_stack(factories)

    response = await api_client.get(
        "/api/student/me/face-embedding",
        params={"current_version": 0},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "face_embedding_not_found"


# --- 5.6 schedule --------------------------------------------------------


async def test_schedule_returns_the_enrolled_offering(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)

    response = await api_client.get(
        "/api/student/schedule", headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 200
    offerings = response.json()["offerings"]
    assert len(offerings) == 1
    item = offerings[0]
    assert item["offering_id"] == stack["offering"].id
    assert item["course_code"] == stack["course"].course_code
    assert item["program_code"] == stack["program"].code
    assert item["year_level_label"] == stack["year_level"].label
    assert item["semester"] == stack["offering"].semester
    assert item["schedule_days"] == stack["offering"].schedule_days
    # No assignment exists in full_stack, so the name is legitimately None.
    assert item["professor_name"] is None


async def test_schedule_names_the_assigned_professor(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """PROMPT 5.6 joins course_professors for the professor name."""

    stack = await linked_stack(factories)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(stack["offering"], stack["professor"], assigner)

    response = await api_client.get(
        "/api/student/schedule", headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 200
    item = response.json()["offerings"][0]
    expected = f"{stack['professor'].first_name} {stack['professor'].last_name}"
    assert item["professor_name"] == expected


async def test_schedule_omits_an_archived_offering(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """An enrollment in an archived offering is not shown."""

    stack = await linked_stack(factories)
    stack["offering"].is_active = False

    response = await api_client.get(
        "/api/student/schedule", headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 200
    assert response.json()["offerings"] == []


# --- 5.7 profile ---------------------------------------------------------


async def test_profile_returns_student_number(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The student-facing contract names the field `student_number`.

    The admin roster rows use `student_id` for the same column; both are
    emitted on this response so each client reads the name it expects.
    """

    stack = await linked_stack(factories)

    response = await api_client.get(
        "/api/student/profile", headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student_number"] == stack["student"].student_id
    assert body["student_id"] == stack["student"].student_id
    assert body["program_code"] == stack["program"].code
    assert body["year_level_label"] == stack["year_level"].label
    assert body["face_enrolled"] is False
    assert body["created_at"]
    assert body["scan_count"] == 0


async def test_profile_scan_count_reflects_scans(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    await factories.attendance(stack["student"], stack["session"])

    response = await api_client.get(
        "/api/student/profile", headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 200
    assert response.json()["scan_count"] == 1


async def test_change_password_updates_the_hash(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    stack["user"].password_hash = hash_password("CurrentPass1!")

    response = await api_client.patch(
        "/api/student/profile/password",
        json={"current_password": "CurrentPass1!", "new_password": "BrandNewPass2!"},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated"}


async def test_change_password_rejects_a_wrong_current_password(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    stack["user"].password_hash = hash_password("CurrentPass1!")

    response = await api_client.patch(
        "/api/student/profile/password",
        json={"current_password": "WrongPass1!", "new_password": "BrandNewPass2!"},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "current_password_invalid"


async def test_change_password_rejects_a_weak_new_password(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await linked_stack(factories)
    stack["user"].password_hash = hash_password("CurrentPass1!")

    response = await api_client.patch(
        "/api/student/profile/password",
        json={"current_password": "CurrentPass1!", "new_password": "weakpass1"},
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 422


# --- 5.8 liveness review queue -------------------------------------------


async def seed_pending_review(factories: Factories, **overrides: Any) -> dict[str, Any]:
    """A stack whose student scanned inside the review band, so it is pending."""

    stack: dict[str, Any] = await linked_stack(factories)
    scanned_at = stack["session"].created_at + timedelta(minutes=2)

    await factories.attendance(
        stack["student"],
        stack["session"],
        timestamp=scanned_at,
        validation_status=ValidationStatus.PENDING.value,
        original_status=ValidationStatus.PRESENT.value,
        face_match_score=REVIEW_BAND_SCORE,
        liveness_evidence={
            "blink_detected": True,
            "head_turn_left": True,
            "head_turn_right": True,
            "ear_samples": [0.20, 0.21, 0.19],
            "pnp_evidence": {"depth_mean": 0.4},
            "review": True,
            "accuracy": 5.0,
        },
        **overrides,
    )

    return stack


async def test_review_queue_lists_pending_records(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    await seed_pending_review(factories)

    response = await api_client.get(
        "/api/admin/attendance/liveness-review",
        headers=await auth_headers(role=UserRole.ADMIN.value),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["student_number"]
    assert item["session_code"]
    assert item["face_match_score"] == pytest.approx(REVIEW_BAND_SCORE)
    assert item["evidence"]["review"] is True


async def test_review_queue_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    await seed_pending_review(factories)

    response = await api_client.get(
        "/api/admin/attendance/liveness-review",
        headers=await auth_headers(role=UserRole.PROFESSOR.value),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_approving_a_review_restores_the_computed_status(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await seed_pending_review(factories)
    record = (
        await factories.db.scalars(
            select(Attendance).where(Attendance.student_id == stack["student"].id)
        )
    ).one()

    response = await api_client.patch(
        f"/api/admin/attendance/liveness-review/{record.id}/resolve",
        json={"decision": "approve"},
        headers=await auth_headers(role=UserRole.ADMIN.value),
    )

    assert response.status_code == 200
    assert response.json()["status"] == ValidationStatus.PRESENT.value

    await factories.db.refresh(record)
    assert record.validation_status == ValidationStatus.PRESENT.value
    assert "review" not in (record.liveness_evidence or {})


async def test_rejecting_a_review_sets_rejected(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await seed_pending_review(factories)
    record = (
        await factories.db.scalars(
            select(Attendance).where(Attendance.student_id == stack["student"].id)
        )
    ).one()

    response = await api_client.patch(
        f"/api/admin/attendance/liveness-review/{record.id}/resolve",
        json={"decision": "reject", "note": "photo mismatch"},
        headers=await auth_headers(role=UserRole.ADMIN.value),
    )

    assert response.status_code == 200
    assert response.json()["status"] == ValidationStatus.REJECTED.value

    await factories.db.refresh(record)
    assert record.validation_status == ValidationStatus.REJECTED.value
    # PROMPT 5.8 asked for the note to be kept; it rides in the JSONB evidence.
    assert (record.liveness_evidence or {}).get("review_note") == "photo mismatch"


async def test_resolving_an_already_resolved_record_is_409(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await seed_pending_review(factories)
    record = (
        await factories.db.scalars(
            select(Attendance).where(Attendance.student_id == stack["student"].id)
        )
    ).one()
    headers = await auth_headers(role=UserRole.ADMIN.value)

    first = await api_client.patch(
        f"/api/admin/attendance/liveness-review/{record.id}/resolve",
        json={"decision": "approve"},
        headers=headers,
    )
    second = await api_client.patch(
        f"/api/admin/attendance/liveness-review/{record.id}/resolve",
        json={"decision": "approve"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "review_not_pending"


async def test_review_note_is_dropped_when_absent(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: AsyncSession
) -> None:
    """A resolve without a note must not leave a stale key behind."""

    stack = await seed_pending_review(factories)
    record = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.student_id == stack["student"].id)
        )
    ).one()

    response = await api_client.patch(
        f"/api/admin/attendance/liveness-review/{record.id}/resolve",
        json={"decision": "approve"},
        headers=await auth_headers(role=UserRole.ADMIN.value),
    )

    assert response.status_code == 200
    await test_db_session.refresh(record)
    assert "review_note" not in (record.liveness_evidence or {})

# --- attempt metadata over HTTP (machine-readable contract) ----------------


def _enroll_http_face(student: Any) -> None:
    """Set a real reference embedding on the linked student."""

    ref = np.ones(128, dtype=np.float32) * 0.1
    student.face_embedding = serialize_embedding(ref / np.linalg.norm(ref))


def _mismatch_http_embedding() -> str:
    """An embedding far from any enrolled reference (score well below band)."""

    return embedding_to_base64(np.random.RandomState(999).randn(128).astype(np.float32))


async def test_scan_exhaustion_envelope_carries_attempt_details(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: AsyncSession
) -> None:
    """The 409 body carries `detail.details` with the post-increment state.

    This is the envelope the frontend actually parses; service-level
    assertions on `exc.details` never prove it survives serialization.
    """

    stack = await linked_stack(factories, attendance_attempt_limit=1)
    student = stack["student"]
    _enroll_http_face(student)
    test_db_session.add(
        AttendanceAttemptCounter(
            student_id=student.id, session_id=stack["session"].id, attempts=1
        )
    )
    # `api_client` commits on success only, and this test's first request
    # fails — commit the seed up front or the counter row rolls back.
    await test_db_session.commit()

    response = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(
            stack["session"].id,
            student.student_id,
            stack["session"].created_at + timedelta(minutes=2),
        ),
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "attendance_attempt_limit_reached"
    assert detail["details"] == {
        "attempt_limit": 1,
        "attempts_used": 2,
        "attempts_remaining": 0,
        "attempt_consumed": True,
    }


async def test_scan_success_response_carries_attempt_fields(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: AsyncSession
) -> None:
    """A 200 scan reports limit/used/remaining in the body the client maps."""

    stack = await linked_stack(factories, attendance_attempt_limit=3)
    student = stack["student"]
    _enroll_http_face(student)
    await test_db_session.commit()

    response = await api_client.post(
        "/api/student/attendance/scan",
        json=scan_body(
            stack["session"].id,
            student.student_id,
            stack["session"].created_at + timedelta(minutes=2),
        ),
        headers=await auth_headers(stack["user"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attendance_attempt_limit"] == 3
    assert body["attempts_used"] == 1
    assert body["attempts_remaining"] == 2


async def test_post_increment_mismatch_envelope_carries_attempt_details(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: AsyncSession
) -> None:
    """A consuming failure (face mismatch) reports the updated remaining count."""

    stack = await linked_stack(factories, attendance_attempt_limit=3)
    student = stack["student"]
    _enroll_http_face(student)
    await test_db_session.commit()

    body = scan_body(
        stack["session"].id,
        student.student_id,
        stack["session"].created_at + timedelta(minutes=2),
    )
    body["live_face_embedding"] = _mismatch_http_embedding()

    response = await api_client.post(
        "/api/student/attendance/scan", json=body, headers=await auth_headers(stack["user"])
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "face_mismatch"
    assert detail["details"] == {
        "attempt_limit": 3,
        "attempts_used": 1,
        "attempts_remaining": 2,
        "attempt_consumed": True,
    }
