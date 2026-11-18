"""HTTP cover for professor assignment pages after handovers.

A reassignment keeps the ended row and adds a new one. The professor pages
key course cards by offering id, so the read models must collapse repeated
offerings instead of returning one row per historical assignment.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import AuditAction, AuditEntity, UserRole

from features.system.model import AuditLog
from tests.conftest import Factories


async def _seed(factories: Factories) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    admin = await factories.user(role=UserRole.ADMIN.value)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    return {
        "offering": offering,
        "admin": admin,
        "professor": professor,
        "professor_user": professor_user,
    }


async def test_professor_pages_dedupe_repeated_offering_assignments(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()

    # Two active rows for the same offering: one ending today, one starting
    # today. This is the state that used to crash the keyed course lists.
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today - timedelta(days=30),
        effective_to=today,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today,
        effective_to=None,
    )
    await test_db_session.commit()

    professor_headers = await auth_headers(seed["professor_user"])
    profile = await api_client.get("/api/professor/profile", headers=professor_headers)
    assert profile.status_code == 200
    assert [row["offering_id"] for row in profile.json()["assigned_courses"]] == [
        seed["offering"].id
    ]

    courses = await api_client.get("/api/professor/courses", headers=professor_headers)
    assert courses.status_code == 200
    assert [row["offering_id"] for row in courses.json()["items"]] == [
        seed["offering"].id
    ]

    admin_headers = await auth_headers(seed["admin"])
    detail = await api_client.get(
        f"/api/admin/professors/{seed['professor'].id}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert [row["offering_id"] for row in detail.json()["assigned_courses"]] == [
        seed["offering"].id
    ]


async def test_reassign_professor_returns_201_and_keeps_history(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    replacement = await factories.professor()
    today = date.today()
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today - timedelta(days=30),
        effective_to=None,
    )
    await test_db_session.commit()

    admin_headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reassign",
        json={
            "new_professor_id": replacement.id,
            "effective_from": today.isoformat(),
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["professor_id"] == replacement.id
    assert body["semester"] == seed["offering"].semester

    rows = await api_client.get(
        f"/api/admin/offerings/{seed['offering'].id}/professors",
        headers=admin_headers,
    )
    assert rows.status_code == 200
    by_professor = {row["professor_id"]: row for row in rows.json()}
    assert (
        by_professor[seed["professor"].id]["effective_to"]
        == (today - timedelta(days=1)).isoformat()
    )
    assert by_professor[replacement.id]["effective_to"] is None


async def _assignment_rows(
    api_client: Any, headers: dict[str, str], offering_id: int
) -> list[dict[str, Any]]:
    response = await api_client.get(
        f"/api/admin/offerings/{offering_id}/professors", headers=headers
    )
    assert response.status_code == 200
    return response.json()


async def test_end_future_assignment_cancels_without_500(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The exact production state: ended-today row + future open-ended row."""
    seed = await _seed(factories)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today,
        effective_to=today,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=tomorrow,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{seed['offering'].id}/professors/{seed['professor'].id}",
        params={"effective_from": tomorrow.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    assert [(row["effective_from"], row["effective_to"]) for row in rows] == [
        (today.isoformat(), today.isoformat())
    ]
    assert all(
        row["effective_to"] is None or row["effective_to"] >= row["effective_from"]
        for row in rows
    )


async def test_end_assignment_without_effective_from_uses_open_ended_row(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """Older clients do not send the date; the fallback must not 500."""
    seed = await _seed(factories)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today,
        effective_to=today,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=tomorrow,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{seed['offering'].id}/professors/{seed['professor'].id}",
        headers=headers,
    )

    assert response.status_code == 200
    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    assert len(rows) == 1
    assert rows[0]["effective_from"] == today.isoformat()


async def test_end_current_assignment_sets_today(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()
    start = today - timedelta(days=30)
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{seed['offering'].id}/professors/{seed['professor'].id}",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    assert rows[0]["effective_to"] == today.isoformat()


async def test_reassign_future_assignment_same_day_replaces_it(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    replacement = await factories.professor()
    today = date.today()
    tomorrow = today + timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=today,
        effective_to=today,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=tomorrow,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reassign",
        json={
            "new_professor_id": replacement.id,
            "old_effective_from": tomorrow.isoformat(),
            "effective_from": tomorrow.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["professor_id"] == replacement.id

    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    assert len(rows) == 2
    old_rows = [row for row in rows if row["professor_id"] == seed["professor"].id]
    new_rows = [row for row in rows if row["professor_id"] == replacement.id]
    assert [(row["effective_from"], row["effective_to"]) for row in old_rows] == [
        (today.isoformat(), today.isoformat())
    ]
    assert [(row["effective_from"], row["effective_to"]) for row in new_rows] == [
        (tomorrow.isoformat(), None)
    ]


async def test_reassign_future_assignment_later_closes_day_before(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    replacement = await factories.professor()
    today = date.today()
    start = today + timedelta(days=2)
    later = start + timedelta(days=2)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reassign",
        json={
            "new_professor_id": replacement.id,
            "old_effective_from": start.isoformat(),
            "effective_from": later.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    old_row = next(row for row in rows if row["professor_id"] == seed["professor"].id)
    assert old_row["effective_to"] == (later - timedelta(days=1)).isoformat()
    assert old_row["effective_to"] >= old_row["effective_from"]


async def test_reassign_ended_assignment_returns_409(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    replacement = await factories.professor()
    today = date.today()
    start = today - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=today - timedelta(days=1),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reassign",
        json={
            "new_professor_id": replacement.id,
            "old_effective_from": start.isoformat(),
            "effective_from": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_already_ended"


async def test_reopen_ended_assignment_clears_effective_to_and_audits(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()
    start = today - timedelta(days=10)
    ended = today - timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=ended,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reopen",
        json={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["effective_to"] is None
    assert response.json()["is_primary"] is True

    rows = await _assignment_rows(api_client, headers, seed["offering"].id)
    assert [(row["effective_from"], row["effective_to"]) for row in rows] == [
        (start.isoformat(), None)
    ]

    audit = (
        await test_db_session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.REOPEN.value,
                AuditLog.entity_type == AuditEntity.COURSE_PROFESSOR.value,
            )
        )
    ).one()
    assert audit.old_value["effective_to"] == ended.isoformat()
    assert audit.new_value["effective_to"] is None


async def test_reopen_open_assignment_returns_409(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()
    start = today - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reopen",
        json={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_not_ended"


async def test_reopen_rejects_when_a_later_assignment_exists(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()
    first_start = today - timedelta(days=20)
    first_end = today - timedelta(days=10)
    second_start = today - timedelta(days=9)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=first_start,
        effective_to=first_end,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=second_start,
        effective_to=None,
    )
    await test_db_session.commit()
    offering_id = seed["offering"].id

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors/{seed['professor'].id}/reopen",
        json={"effective_from": first_start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_reopen_conflict"

    rows = await _assignment_rows(api_client, headers, offering_id)
    first = next(
        row for row in rows if row["effective_from"] == first_start.isoformat()
    )
    assert first["effective_to"] == first_end.isoformat()


async def test_reopen_requires_the_exact_assignment_start(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    today = date.today()
    start = today - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=today - timedelta(days=1),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{seed['offering'].id}/professors/"
        f"{seed['professor'].id}/reopen",
        json={"effective_from": (today - timedelta(days=5)).isoformat()},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "assignment_not_found"


# -- primary uniqueness -------------------------------------------------------


async def _seed_primary(
    factories: Factories,
    seed: dict[str, Any],
    *,
    start: date,
    end: date | None,
) -> Any:
    other = await factories.professor()
    await factories.assignment(
        seed["offering"],
        other,
        seed["admin"],
        effective_from=start,
        effective_to=end,
    )
    return other


async def test_assign_primary_rejected_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    await _seed_primary(factories, seed, start=today - timedelta(days=10), end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors",
        json={
            "professor_id": professor_id,
            "is_primary": True,
            "effective_from": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "primary_assignment_conflict"
    rows = await _assignment_rows(api_client, headers, offering_id)
    assert all(row["professor_id"] != professor_id for row in rows)


async def test_assign_assistant_allowed_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    await _seed_primary(factories, seed, start=today - timedelta(days=10), end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors",
        json={
            "professor_id": professor_id,
            "is_primary": False,
            "effective_from": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["is_primary"] is False


async def test_assign_primary_allowed_after_existing_primary_ends(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    await _seed_primary(
        factories,
        seed,
        start=today - timedelta(days=10),
        end=today,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors",
        json={
            "professor_id": professor_id,
            "is_primary": True,
            "effective_from": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["is_primary"] is True


async def test_assign_primary_rejected_on_existing_primary_end_date(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    await _seed_primary(
        factories,
        seed,
        start=today - timedelta(days=10),
        end=today,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors",
        json={
            "professor_id": professor_id,
            "is_primary": True,
            "effective_from": today.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "primary_assignment_conflict"


async def test_reassign_to_primary_rejected_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    replacement = await factories.professor()
    replacement_id = replacement.id
    today = date.today()
    start = today - timedelta(days=10)
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
        is_primary=True,
    )
    await _seed_primary(factories, seed, start=start, end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/reassign",
        json={
            "new_professor_id": replacement_id,
            "is_primary": True,
            "old_effective_from": start.isoformat(),
            "effective_from": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "primary_assignment_conflict"
    rows = await _assignment_rows(api_client, headers, offering_id)
    source = next(row for row in rows if row["professor_id"] == professor_id)
    assert source["effective_to"] is None
    assert all(row["professor_id"] != replacement_id for row in rows)


async def test_reassign_to_assistant_allowed_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    replacement = await factories.professor()
    replacement_id = replacement.id
    today = date.today()
    start = today - timedelta(days=10)
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
        is_primary=True,
    )
    await _seed_primary(factories, seed, start=start, end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/reassign",
        json={
            "new_professor_id": replacement_id,
            "is_primary": False,
            "old_effective_from": start.isoformat(),
            "effective_from": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["is_primary"] is False


async def test_reopen_primary_rejected_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    start = today - timedelta(days=10)
    ended = today - timedelta(days=1)
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=ended,
        is_primary=True,
    )
    await _seed_primary(factories, seed, start=start, end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/reopen",
        json={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "primary_assignment_conflict"
    rows = await _assignment_rows(api_client, headers, offering_id)
    source = next(row for row in rows if row["professor_id"] == professor_id)
    assert source["effective_to"] == ended.isoformat()


async def test_reopen_as_assistant_allowed_when_another_primary_overlaps(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    start = today - timedelta(days=10)
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=today - timedelta(days=1),
        is_primary=True,
    )
    await _seed_primary(factories, seed, start=start, end=None)
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/reopen",
        json={"effective_from": start.isoformat(), "is_primary": False},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_primary"] is False
    assert response.json()["effective_to"] is None


async def test_permanently_remove_unused_assignment_deletes_and_audits(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    start = date.today() - timedelta(days=10)
    ended = date.today() - timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=ended,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 204
    assert await _assignment_rows(api_client, headers, offering_id) == []

    audit = (
        await test_db_session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.DELETE.value,
                AuditLog.entity_type == AuditEntity.COURSE_PROFESSOR.value,
            )
        )
    ).one()
    assert audit.old_value["professor_id"] == professor_id
    assert audit.old_value["effective_from"] == start.isoformat()


async def test_permanently_remove_assignment_with_sessions_returns_409(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    start = date.today() - timedelta(days=10)
    ended = date.today() - timedelta(days=1)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=ended,
    )
    await factories.session(
        seed["offering"],
        seed["professor"],
        created_at=datetime.combine(
            start + timedelta(days=1), time(10), tzinfo=timezone.utc
        ),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_has_sessions"

    rows = await _assignment_rows(api_client, headers, offering_id)
    assert len(rows) == 1
    assert rows[0]["has_sessions"] is True


async def test_permanently_remove_active_assignment_returns_409(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    start = date.today() - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_not_ended"

    rows = await _assignment_rows(api_client, headers, offering_id)
    assert len(rows) == 1
    assert rows[0]["effective_to"] is None


async def test_permanently_remove_live_assignment_with_future_end_returns_409(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    start = today - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=today + timedelta(days=5),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assignment_not_ended"
    assert len(await _assignment_rows(api_client, headers, offering_id)) == 1


async def test_permanently_remove_requires_the_exact_assignment_start(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    start = date.today() - timedelta(days=10)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=None,
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": (start + timedelta(days=1)).isoformat()},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "assignment_not_found"
    assert len(await _assignment_rows(api_client, headers, offering_id)) == 1


async def test_assignment_list_flags_sessions_only_inside_the_row_window(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    today = date.today()
    first_start = today - timedelta(days=30)
    first_end = today - timedelta(days=20)
    second_start = today - timedelta(days=19)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=first_start,
        effective_to=first_end,
        is_primary=False,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=second_start,
        effective_to=None,
        is_primary=False,
    )
    await factories.session(
        seed["offering"],
        seed["professor"],
        created_at=datetime.combine(
            today - timedelta(days=15), time(10), tzinfo=timezone.utc
        ),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    rows = await _assignment_rows(api_client, headers, offering_id)
    by_start = {row["effective_from"]: row for row in rows}

    assert by_start[first_start.isoformat()]["has_sessions"] is False
    assert by_start[second_start.isoformat()]["has_sessions"] is True


async def test_permanently_remove_ignores_sessions_outside_the_row_window(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    professor_id = seed["professor"].id
    today = date.today()
    first_start = today - timedelta(days=30)
    first_end = today - timedelta(days=20)
    second_start = today - timedelta(days=19)

    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=first_start,
        effective_to=first_end,
        is_primary=False,
    )
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=second_start,
        effective_to=None,
        is_primary=False,
    )
    await factories.session(
        seed["offering"],
        seed["professor"],
        created_at=datetime.combine(
            today - timedelta(days=15), time(10), tzinfo=timezone.utc
        ),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    response = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/{professor_id}/permanent",
        params={"effective_from": first_start.isoformat()},
        headers=headers,
    )

    assert response.status_code == 204
    rows = await _assignment_rows(api_client, headers, offering_id)
    assert [row["effective_from"] for row in rows] == [second_start.isoformat()]
    assert rows[0]["has_sessions"] is True


async def test_permanently_remove_primary_frees_the_slot(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    start = date.today() - timedelta(days=10)
    replacement = await factories.professor()

    # End today: the primary slot is still occupied today, so the new primary
    # assignment below would conflict until this row is purged.
    await factories.assignment(
        seed["offering"],
        seed["professor"],
        seed["admin"],
        effective_from=start,
        effective_to=date.today(),
    )
    await test_db_session.commit()

    headers = await auth_headers(seed["admin"])
    removed = await api_client.delete(
        f"/api/admin/offerings/{offering_id}/professors/"
        f"{seed['professor'].id}/permanent",
        params={"effective_from": start.isoformat()},
        headers=headers,
    )
    assert removed.status_code == 204

    assigned = await api_client.post(
        f"/api/admin/offerings/{offering_id}/professors",
        json={
            "professor_id": replacement.id,
            "is_primary": True,
            "effective_from": date.today().isoformat(),
        },
        headers=headers,
    )

    assert assigned.status_code == 201
    rows = await _assignment_rows(api_client, headers, offering_id)
    assert [(row["professor_id"], row["is_primary"]) for row in rows] == [
        (replacement.id, True)
    ]
