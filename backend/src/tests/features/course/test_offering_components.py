"""Lecture/lab session types and offering components (D77).

DB-backed cover for the new contract: offerings carry per-type scheduled
components, sessions persist their type, lab opens require coordinates, and
the professor reads expose + filter by type.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Callable, Coroutine

from sqlalchemy import select

from features.course.model import OfferingComponent
from features.session.model import Session
from shared.enums import UserRole
from tests.conftest import Factories

OFFERINGS = "/api/admin/offerings"
SESSIONS = "/api/professor/sessions"


async def _admin_headers(auth_headers: Any, factories: Factories) -> dict[str, str]:
    return await auth_headers(await factories.user(role=UserRole.ADMIN.value))


async def _seed_offering(factories: Factories, **overrides: Any) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level, **overrides)
    return {
        "program": program,
        "year_level": year_level,
        "course": course,
        "offering": offering,
    }


async def _seed_offering_with_lab(
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> dict[str, Any]:
    """An offering that meets a laboratory as well as a lecture (D95).

    A session of a type the offering does not configure is refused, so a
    laboratory session needs a laboratory meeting. Both meetings cover the
    suite's pinned clock (D94), and their weekly total is the course's
    units (D82): three lecture days plus one laboratory day is four units.
    The laboratory meeting has no coordinates, so the laboratory sessions
    below resolve their room from the payload.
    """
    seed = await _seed_offering(factories)
    seed["course"].units = 4
    await factories.db.flush()

    await db_factory(
        OfferingComponent,
        offering_id=seed["offering"].id,
        session_type="lecture",
        schedule_days="MWF",
        schedule_start_time=time(8, 0),
        schedule_end_time=time(9, 0),
        is_active=True,
    )
    await db_factory(
        OfferingComponent,
        offering_id=seed["offering"].id,
        session_type="lab",
        schedule_days="W",
        schedule_start_time=time(8, 0),
        schedule_end_time=time(9, 0),
        classroom_name="Lab 101",
        is_active=True,
    )

    return seed


async def _assigned_professor_headers(
    factories: Factories, auth_headers: Any, offering: Any
) -> dict[str, str]:
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    assigner = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(offering, professor, assigner)
    return await auth_headers(professor_user)


def _offering_payload(seed: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "course_id": seed["course"].id,
        "program_id": seed["program"].id,
        "year_level_id": seed["year_level"].id,
        "semester": "1st Sem",
        "academic_year": "2026-2027",
        "sessions_per_week": 2,
        "schedule_days": "MWF",
        "schedule_start_time": "08:00:00",
        "schedule_end_time": "09:00:00",
    }
    payload.update(overrides)
    return payload


# --- offering create with components --------------------------------------


async def test_create_offering_with_mixed_components(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    # MWF 08:00-09:00 counts 3h plus lab M 13:00-15:00 counts 2h = 5h total,
    # so the template needs exactly 5 units under the exact-match rule (D79).
    seed["course"].units = 5
    await factories.db.flush()
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(
        OFFERINGS,
        json=_offering_payload(
            seed,
            components=[
                {
                    "session_type": "lecture",
                    "schedule_days": "MWF",
                    "schedule_start_time": "08:00:00",
                    "schedule_end_time": "09:00:00",
                    "classroom_name": "Room 203",
                },
                {
                    "session_type": "lab",
                    "schedule_days": "M",
                    "schedule_start_time": "13:00:00",
                    "schedule_end_time": "15:00:00",
                    "classroom_name": "Lab 101",
                    "classroom_lat": 14.5,
                    "classroom_lng": 121.0,
                },
            ],
        ),
        headers=headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert sorted(body["session_types"]) == ["lab", "lecture"]
    assert len(body["components"]) == 2
    lab = next(c for c in body["components"] if c["session_type"] == "lab")
    assert lab["schedule_days"] == "M"
    assert lab["classroom_name"] == "Lab 101"
    assert lab["classroom_lat"] == 14.5

    fetched = await api_client.get(f"{OFFERINGS}/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert sorted(fetched.json()["session_types"]) == ["lab", "lecture"]
    assert len(fetched.json()["components"]) == 2


async def test_create_offering_without_components_defaults_to_lecture(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(
        OFFERINGS, json=_offering_payload(seed), headers=headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_types"] == ["lecture"]
    (component,) = body["components"]
    assert component["session_type"] == "lecture"
    assert component["schedule_days"] == "MWF"
    assert component["schedule_start_time"].startswith("08:00")


# --- component CRUD --------------------------------------------------------


async def test_component_crud_roundtrip(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    listed = await api_client.get(f"{OFFERINGS}/{offering_id}/components", headers=headers)
    assert listed.status_code == 200
    # Factory-seeded offerings bypass the service, so no default component.
    assert listed.json() == []

    created = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "M",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "15:00:00",
            "classroom_name": "Lab 101",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    component_id = created.json()["id"]
    assert created.json()["session_type"] == "lab"

    duplicate = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "M",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "15:00:00",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "component_exists"

    patched = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{component_id}",
        json={"classroom_name": "Lab 102"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["classroom_name"] == "Lab 102"

    bad_window = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{component_id}",
        json={"schedule_start_time": "16:00:00", "schedule_end_time": "15:00:00"},
        headers=headers,
    )
    assert bad_window.status_code == 422
    assert bad_window.json()["detail"]["code"] == "invalid_schedule_window"

    archived = await api_client.delete(
        f"{OFFERINGS}/{offering_id}/components/{component_id}", headers=headers
    )
    assert archived.status_code == 204

    listed_again = await api_client.get(
        f"{OFFERINGS}/{offering_id}/components", headers=headers
    )
    assert listed_again.status_code == 200
    assert listed_again.json() == []

    missing = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/999999",
        json={"classroom_name": "Nowhere"},
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "component_not_found"

    missing_offering = await api_client.get(
        f"{OFFERINGS}/999999/components", headers=headers
    )
    assert missing_offering.status_code == 404
    assert missing_offering.json()["detail"]["code"] == "offering_not_found"


# --- single-component mirror ------------------------------------------------


async def test_single_component_mirrors_onto_offering(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    created = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "M",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "15:00:00",
            "classroom_name": "Lab 101",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    # One active meeting: the offering columns mirror it, so the legacy
    # schedule display and the session fallback agree with the meeting.
    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["schedule_days"] == "M"
    assert body["schedule_start_time"].startswith("13:00")
    assert body["classroom_name"] == "Lab 101"
    assert body["session_types"] == ["lab"]

    # A second meeting breaks the mirror: the offering keeps its columns.
    second = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lecture",
            "schedule_days": "W",
            "schedule_start_time": "09:00:00",
            "schedule_end_time": "10:00:00",
        },
        headers=headers,
    )
    assert second.status_code == 201, second.text

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.json()["schedule_days"] == "M"
    assert sorted(fetched.json()["session_types"]) == ["lab", "lecture"]

    # Archiving back down to one meeting re-mirrors the survivor.
    archived = await api_client.delete(
        f"{OFFERINGS}/{offering_id}/components/{created.json()['id']}",
        headers=headers,
    )
    assert archived.status_code == 204

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.json()["schedule_days"] == "W"
    assert fetched.json()["session_types"] == ["lecture"]


# --- session open ----------------------------------------------------------


async def test_open_lab_session_without_coordinates_is_422(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    seed = await _seed_offering_with_lab(factories, db_factory)
    headers = await _assigned_professor_headers(
        factories, auth_headers, seed["offering"]
    )
    await test_db_session.commit()

    response = await api_client.post(
        SESSIONS,
        json={"offering_id": seed["offering"].id, "session_type": "lab"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "lab_coordinates_required"


async def test_open_lab_session_with_coordinates_persists_type(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    seed = await _seed_offering_with_lab(factories, db_factory)
    headers = await _assigned_professor_headers(
        factories, auth_headers, seed["offering"]
    )
    await test_db_session.commit()

    opened = await api_client.post(
        SESSIONS,
        json={
            "offering_id": seed["offering"].id,
            "session_type": "lab",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )

    assert opened.status_code == 201, opened.text
    assert opened.json()["session_type"] == "lab"

    session_id = opened.json()["id"]
    active = await api_client.get(
        f"{SESSIONS}/active/{session_id}", headers=headers
    )
    assert active.status_code == 200
    assert active.json()["session_type"] == "lab"


async def test_open_session_defaults_to_lecture(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    headers = await _assigned_professor_headers(
        factories, auth_headers, seed["offering"]
    )

    opened = await api_client.post(
        SESSIONS, json={"offering_id": seed["offering"].id}, headers=headers
    )

    assert opened.status_code == 201, opened.text
    assert opened.json()["session_type"] == "lecture"


async def test_lab_session_prefills_component_classroom(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_offering(factories)
    # The lone lab meeting is 2h, so the template needs exactly 2 units for
    # the session-open requirement gate (D82). It is scheduled on the day the
    # suite's pinned clock falls on, and it covers that hour, so the open is
    # inside its scheduled window (D94).
    seed["course"].units = 2
    await factories.db.flush()
    admin_headers = await _admin_headers(auth_headers, factories)

    created = await api_client.post(
        f"{OFFERINGS}/{seed['offering'].id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "W",
            "schedule_start_time": "08:00:00",
            "schedule_end_time": "10:00:00",
            "classroom_name": "Lab 101",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text

    headers = await _assigned_professor_headers(
        factories, auth_headers, seed["offering"]
    )
    opened = await api_client.post(
        SESSIONS,
        json={"offering_id": seed["offering"].id, "session_type": "lab"},
        headers=headers,
    )

    # No coordinates typed, but the lab component supplies them.
    assert opened.status_code == 201, opened.text
    assert opened.json()["session_type"] == "lab"


# --- reads filter by type --------------------------------------------------


async def test_session_list_history_and_ledger_filter_by_type(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    seed = await _seed_offering_with_lab(factories, db_factory)
    offering_id = seed["offering"].id
    headers = await _assigned_professor_headers(factories, auth_headers, seed["offering"])
    await test_db_session.commit()

    lecture = await api_client.post(
        SESSIONS,
        json={
            "offering_id": offering_id,
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert lecture.status_code == 201, lecture.text
    await api_client.post(f"{SESSIONS}/{lecture.json()['id']}/close", headers=headers)

    lab = await api_client.post(
        SESSIONS,
        json={
            "offering_id": offering_id,
            "session_type": "lab",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert lab.status_code == 201, lab.text

    listed = await api_client.get(SESSIONS, headers=headers)
    assert listed.status_code == 200
    assert {item["session_type"] for item in listed.json()["items"]} == {
        "lecture",
        "lab",
    }

    labs_only = await api_client.get(
        SESSIONS, params={"session_type": "lab"}, headers=headers
    )
    assert labs_only.status_code == 200
    assert [item["session_type"] for item in labs_only.json()["items"]] == ["lab"]

    history = await api_client.get(
        f"{SESSIONS}/history", params={"session_type": "lab"}, headers=headers
    )
    assert history.status_code == 200
    assert [item["session_type"] for item in history.json()["items"]] == ["lab"]


async def test_attendance_ledger_carries_session_type(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    seed = await _seed_offering_with_lab(factories, db_factory)
    offering = seed["offering"]
    headers = await _assigned_professor_headers(factories, auth_headers, offering)
    await test_db_session.commit()

    opened = await api_client.post(
        SESSIONS,
        json={
            "offering_id": offering.id,
            "session_type": "lab",
            "classroom_lat": 14.5,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert opened.status_code == 201, opened.text

    student = await factories.student(seed["year_level"])
    await factories.enrollment(student, offering)
    row = (
        await factories.db.scalars(select(Session).where(Session.id == opened.json()["id"]))
    ).one()
    await factories.attendance(student, row)

    ledger = await api_client.get(
        "/api/professor/attendance", headers=headers
    )
    assert ledger.status_code == 200
    assert [item["session_type"] for item in ledger.json()["items"]] == ["lab"]

    filtered = await api_client.get(
        "/api/professor/attendance",
        params={"session_type": "lecture"},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []
