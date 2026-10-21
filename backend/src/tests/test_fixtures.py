"""The shared API fixtures, exercised end to end (coding-standards 5.1).

`conftest.py` ships three client fixtures. Until something uses them they can
rot silently, and a broken fixture fails every future test at once rather
than one. This file is that something.

It also pins the auth boundary over the real ASGI stack: a real JWT is
minted by `core.security` and travels as a bearer token through
`require_role`, so these assertions are about the production auth path rather
than a faked dependency.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.attendance.model import Attendance
from features.auth.model import User
from features.program.model import YearLevel
from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

CLASSROOM_LAT = 14.0
CLASSROOM_LNG = 121.0


# --- test_client: no database --------------------------------------------


def test_health_needs_no_database(test_client: Any) -> None:
    response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_route_without_a_token_is_401(test_client: Any) -> None:
    response = test_client.get("/api/admin/programs")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "missing_token"


def test_unmounted_enrollment_router_is_not_reachable(test_client: Any) -> None:
    """`features/enrollment/router.py` is intentionally not mounted."""

    response = test_client.get("/api/admin/enrollments")

    assert response.status_code == 404


# --- api_client + auth_headers: real database ----------------------------


async def test_admin_can_create_and_read_a_program(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await auth_headers(role=UserRole.ADMIN.value)

    created = await api_client.post(
        "/api/admin/programs",
        json={"code": "bscs", "name": "BS Computer Science", "total_years": 4},
        headers=headers,
    )

    assert created.status_code == 201
    body = created.json()
    # The schema normalizes the code, so the stored form is what is asserted.
    assert body["code"] == "BSCS"
    assert body["is_active"] is True

    listed = await api_client.get("/api/admin/programs", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == body["id"]


async def test_created_program_is_visible_to_a_second_request(
    api_client: Any, auth_headers: Any
) -> None:
    """The overridden `_get_db` commits, so a later request sees the row.

    If the override forgot to commit, this is where it would show: the
    service's own `flush` is visible inside the request but not after it.
    """

    headers = await auth_headers(role=UserRole.ADMIN.value)
    created = await api_client.post(
        "/api/admin/programs",
        json={"code": "BSIT", "name": "BS Information Tech", "total_years": 4},
        headers=headers,
    )

    detail = await api_client.get(
        f"/api/admin/programs/{created.json()['id']}", headers=headers
    )

    assert detail.status_code == 200
    assert detail.json()["code"] == "BSIT"


async def test_program_aggregates_count_year_levels_and_terms(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """`terms_count` reads `term_structure["terms"]`, not the dict length.

    A `len(term_structure)` mistake silently reports 1 for every program,
    which is why this asserts a two-term structure counting as 2.
    """

    program = await factories.program()
    await factories.year_level(program)
    headers = await auth_headers(role=UserRole.ADMIN.value)

    listed = await api_client.get("/api/admin/programs", headers=headers)
    aggregate = listed.json()["items"][0]

    assert aggregate["year_level_count"] == 1
    assert aggregate["terms_count"] == 2


async def test_student_token_is_forbidden_from_admin_routes(
    api_client: Any, auth_headers: Any
) -> None:
    headers = await auth_headers(role=UserRole.STUDENT.value)

    response = await api_client.get("/api/admin/programs", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_malformed_token_is_401(api_client: Any) -> None:
    response = await api_client.get(
        "/api/admin/programs", headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_token"


async def test_admin_can_create_a_course(api_client: Any, auth_headers: Any) -> None:
    headers = await auth_headers(role=UserRole.ADMIN.value)

    response = await api_client.post(
        "/api/admin/courses",
        json={
            "course_code": "cs101",
            "course_name": "Intro to Computing",
            "units": 3,
            "session_duration_hours": 1.5,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["course_code"] == "CS101"


async def test_duplicate_course_code_is_rejected(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The unique constraint surfaces as a 409, not a 500."""

    await factories.course(course_code="CS200")
    headers = await auth_headers(role=UserRole.ADMIN.value)

    response = await api_client.post(
        "/api/admin/courses",
        json={
            "course_code": "CS200",
            "course_name": "Another",
            "units": 3,
            "session_duration_hours": 1.0,
        },
        headers=headers,
    )

    assert response.status_code == 409


async def test_list_students_returns_seeded_rows(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    year_level = await factories.year_level(await factories.program())
    student = await factories.student(year_level)
    headers = await auth_headers(role=UserRole.ADMIN.value)

    response = await api_client.get("/api/admin/students", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["student_id"] == student.student_id


async def test_validation_error_is_422_with_field_detail(
    api_client: Any, auth_headers: Any
) -> None:
    headers = await auth_headers(role=UserRole.ADMIN.value)

    response = await api_client.post(
        "/api/admin/programs", json={"code": "", "name": "", "total_years": 99},
        headers=headers,
    )

    assert response.status_code == 422


# --- the full student scan journey over HTTP -----------------------------


async def test_student_scans_a_live_session_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The 5-step scan flow (D27) from the student's point of view.

    Composed from the factories rather than `full_stack` because the scan
    route is role-gated on a student token, which needs a user row linked to
    the student.
    """

    program = await factories.program()
    year_level = await factories.year_level(program)
    user = await factories.user(role=UserRole.STUDENT.value)
    student = await factories.student(year_level, user=user)
    professor = await factories.professor()
    admin = await factories.user(role=UserRole.ADMIN.value)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)
    session = await factories.session(
        offering,
        professor,
        classroom_lat=CLASSROOM_LAT,
        classroom_lng=CLASSROOM_LNG,
        classroom_radius_meters=50,
    )
    headers = await auth_headers(user)

    response = await api_client.post(
        "/api/student/attendance/scan",
        json={
            "session_id": session.id,
            "student_number": student.student_id,
            "gps": {"lat": 14.0001, "lng": 121.0001, "accuracy": 5.0},
            "liveness_evidence": {
                "blink_detected": True,
                "head_turn_left": True,
                "head_turn_right": True,
                "ear_samples": [0.2, 0.21],
                "pnp_evidence": {"depth_mean": 0.4},
            },
            "face_match_score": 0.93,
            "scanned_at": session.created_at.isoformat(),
            "scanned_via": "qr_camera",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == ValidationStatus.PRESENT.value

    rows: list[Attendance] = (
        await test_db_session.scalars(select(Attendance))
    ).all()
    assert len(rows) == 1
    assert rows[0].student_id == student.id
    assert rows[0].session_id == session.id


async def test_scan_outside_the_geofence_returns_403(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    program = await factories.program()
    year_level = await factories.year_level(program)
    user = await factories.user(role=UserRole.STUDENT.value)
    student = await factories.student(year_level, user=user)
    professor = await factories.professor()
    admin = await factories.user(role=UserRole.ADMIN.value)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)
    session = await factories.session(
        offering,
        professor,
        classroom_lat=CLASSROOM_LAT,
        classroom_lng=CLASSROOM_LNG,
        classroom_radius_meters=50,
    )

    response = await api_client.post(
        "/api/student/attendance/scan",
        json={
            "session_id": session.id,
            "student_number": student.student_id,
            "gps": {"lat": 14.02, "lng": 121.0, "accuracy": 5.0},
            "liveness_evidence": {
                "blink_detected": True,
                "head_turn_left": True,
                "head_turn_right": True,
                "ear_samples": [0.2],
                "pnp_evidence": {"depth_mean": 0.4},
            },
            "face_match_score": 0.93,
            "scanned_at": session.created_at.isoformat(),
            "scanned_via": "qr_camera",
        },
        headers=await auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "outside_geofence"


async def test_idempotency_header_makes_a_resubmission_a_replay(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    program = await factories.program()
    year_level = await factories.year_level(program)
    user = await factories.user(role=UserRole.STUDENT.value)
    student = await factories.student(year_level, user=user)
    professor = await factories.professor()
    admin = await factories.user(role=UserRole.ADMIN.value)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)
    session = await factories.session(offering, professor)

    payload = {
        "session_id": session.id,
        "student_number": student.student_id,
        "gps": {"lat": CLASSROOM_LAT, "lng": CLASSROOM_LNG, "accuracy": 5.0},
        "liveness_evidence": {
            "blink_detected": True,
            "head_turn_left": True,
            "head_turn_right": True,
            "ear_samples": [0.2],
            "pnp_evidence": {"depth_mean": 0.4},
        },
        "face_match_score": 0.93,
        "scanned_at": session.created_at.isoformat(),
        "scanned_via": "qr_camera",
    }
    headers = {**(await auth_headers(user)), "X-Idempotency-Key": "resubmit-1"}

    first = await api_client.post(
        "/api/student/attendance/scan", json=payload, headers=headers
    )
    second = await api_client.post(
        "/api/student/attendance/scan", json=payload, headers=headers
    )

    assert first.status_code == 200
    # The replay returns the first response rather than a 409 duplicate.
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


async def test_student_can_verify_a_session_code(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    stack = await factories.full_stack()
    headers = await auth_headers(role=UserRole.STUDENT.value)

    response = await api_client.post(
        "/api/student/sessions/verify-code",
        json={"code": stack["session"].session_code},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == stack["session"].id
    assert body["course_code"] == stack["course"].course_code


async def test_verify_code_is_rate_limited(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """T7: the per-IP verify-code limiter throttles probing for a valid code.

    ten attempts fit in the window; the eleventh is a 429 with `rate_limited`.
    """

    stack = await factories.full_stack()
    headers = await auth_headers(role=UserRole.STUDENT.value)

    for _ in range(10):
        ok = await api_client.post(
            "/api/student/sessions/verify-code",
            json={"code": stack["session"].session_code},
            headers=headers,
        )
        assert ok.status_code == 200

    blocked = await api_client.post(
        "/api/student/sessions/verify-code",
        json={"code": stack["session"].session_code},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "rate_limited"


@pytest.mark.slow
async def test_rate_limiter_does_not_bleed_between_tests(
    api_client: Any, auth_headers: Any
) -> None:
    """A placeholder for the limiter budget; see conftest `reset_process_globals`.

    The scan route allows 30 calls per 60s keyed by client IP, and
    `ASGITransport` presents a constant one. If the limiter were not reset
    between tests, the scan tests in this file would eventually start failing
    with 429 for no visible reason.
    """

    for _ in range(3):
        response = await api_client.get(
            "/api/admin/programs", headers=await auth_headers(
                role=UserRole.ADMIN.value
            )
        )
        assert response.status_code == 200


# --- archive guard: RESTRICT FKs are really enforced ---------------------


async def test_hard_delete_is_blocked_while_records_exist(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """`ondelete=RESTRICT` on enrollments must actually block the delete.

    The `test_engine` fixture turns on `PRAGMA foreign_keys=ON` for exactly
    this: SQLite parses but ignores those clauses by default, so without it
    this test would pass against a database enforcing nothing.
    """

    stack = await factories.full_stack()

    with pytest.raises(Exception) as excinfo:
        await test_db_session.delete(stack["student"])
        await test_db_session.flush()

    assert "FOREIGN KEY" in str(excinfo.value).upper()


async def test_offering_with_enrollments_cannot_be_deleted(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    stack = await factories.full_stack()

    with pytest.raises(Exception) as excinfo:
        await test_db_session.delete(stack["offering"])
        await test_db_session.flush()

    assert "FOREIGN KEY" in str(excinfo.value).upper()


async def test_session_window_check_constraint_is_enforced(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """`ck_session_window_sum_lte_duration` must reject an impossible row."""

    stack = await factories.full_stack()

    with pytest.raises(Exception) as excinfo:
        test_db_session.add(
            type(stack["session"])(
                offering_id=stack["offering"].id,
                professor_id=stack["professor"].id,
                session_code="BADWINDOW",
                duration_minutes=10,
                present_window_minutes=5,
                late_window_minutes=30,
                scheduled_start_time=stack["session"].scheduled_start_time,
                scheduled_end_time=stack["session"].scheduled_end_time,
            )
        )
        await test_db_session.flush()

    assert "CHECK" in str(excinfo.value).upper()


# --- fixture sanity ------------------------------------------------------


async def test_each_test_gets_its_own_schema(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A fresh schema per test: seeded rows are the only rows present.

    If the schema were shared or merely truncated, this would see rows from
    whichever test ran before it and the run order would decide the result.
    """

    assert (await test_db_session.scalars(select(User))).all() == []

    await factories.user()

    assert len((await test_db_session.scalars(select(User))).all()) == 1


async def test_full_stack_wires_a_consistent_graph(factories: Factories) -> None:
    """Every foreign key in the scan chain resolves to the row beside it."""

    stack = await factories.full_stack()

    assert stack["year_level"].program_id == stack["program"].id
    assert stack["student"].year_level_id == stack["year_level"].id
    assert stack["session"].offering_id == stack["offering"].id
    assert stack["session"].professor_id == stack["professor"].id
    assert stack["offering"].course_id == stack["course"].id
    assert stack["enrollment"].student_id == stack["student"].id
    assert stack["enrollment"].offering_id == stack["offering"].id


async def test_factories_default_to_the_server_defaults(factories: Factories) -> None:
    """A factory default that quietly diverges from the column default is a trap.

    These are read back from the database rather than the Python side, so
    this also proves the `server_default`s in the models are what the shims
    create.
    """

    stack = await factories.full_stack()

    assert stack["program"].is_active is True
    assert stack["course"].is_active is True
    assert stack["student"].is_active is True
    assert stack["offering"].is_active is True
    # `sessions.classroom_radius_meters` is a server default, not a
    # Python-side one. The offering's window defaults are the opposite since
    # D93: they are NULL, which means "follow the system default" — the
    # effective value is resolved when a session is opened.
    assert stack["session"].classroom_radius_meters == 50
    assert stack["offering"].default_present_window_minutes is None
    assert stack["offering"].default_late_window_minutes is None
    assert stack["student"].face_embedding_version == 0


async def test_factories_leave_the_1_to_1_user_link_unset(
    factories: Factories,
) -> None:
    """`students.user_id` and `professors.user_id` are unique 1:1 FKs.

    A factory that pre-filled them would make the second call in a test
    collide on the unique constraint, so they are opt-in via the `user=`
    argument instead.
    """

    program = await factories.program()
    student = await factories.student(await factories.year_level(program))
    professor = await factories.professor()

    assert student.user_id is None
    assert professor.user_id is None


async def test_factory_user_override_links_the_row(factories: Factories) -> None:
    user = await factories.user()
    program = await factories.program()
    student = await factories.student(await factories.year_level(program), user=user)

    assert student.user_id == user.id


async def test_factory_ids_are_unique_within_a_test(
    factories: Factories,
) -> None:
    """Ids are unique *per table*, and the unique constraints are satisfied.

    A per-test counter rather than a random suffix is what makes a failure
    reproducible. This is the test that would notice if it stopped
    advancing, and if `year_levels.year_number` regressed to a constant.
    """

    program = await factories.program()
    first = await factories.year_level(program)
    second = await factories.year_level(program)
    other = await factories.student(second)

    # Ids restart per table, so uniqueness is only meaningful within one.
    assert first.id != second.id
    assert (first.year_number, second.year_number) == (1, 2)
    assert (first.sort_order, second.sort_order) == (1, 2)
    assert other.year_level_id == second.id
    assert (
        len(
            (
                await factories.db.scalars(
                    select(YearLevel).where(YearLevel.program_id == program.id)
                )
            ).all()
        )
        == 2
    )


async def test_datetimes_come_back_aware(factories: Factories) -> None:
    """The SQLite shim must match Postgres, where `now()` is `timestamptz`.

    Services compare `created_at` against `_utcnow()` values, so a naive
    datetime here would surface as a `TypeError` inside the service rather
    than as a clear failure here.
    """

    session = (await factories.full_stack())["session"]

    assert session.created_at is not None
    assert session.created_at.tzinfo is not None
    assert session.scheduled_start_time.tzinfo is not None


async def test_session_factory_respects_the_window_check_constraint(
    factories: Factories,
) -> None:
    """Defaults must satisfy `ck_session_window_sum_lte_duration`.

    5 + 10 == 15 <= the 60-minute default, so the factory's own defaults
    have to clear the constraint for every test that uses a session.
    """

    session = (await factories.full_stack())["session"]

    assert (
        session.present_window_minutes + session.late_window_minutes
        <= session.duration_minutes
    )
