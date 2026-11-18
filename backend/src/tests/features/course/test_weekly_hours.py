"""Weekly meeting-hours requirement: `units` as the exact scheduled total (D79).

DB-backed cover: offering creation must land exactly on `courses.units * 60`;
component add/edit must land exactly or converge strictly closer without
crossing to the other side, so legacy and mid-build rows can always be fixed
incrementally but can never overshoot or drift. Reads, archives,
deactivations, and schedule-untouched edits skip the check.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Callable, Coroutine

from shared.enums import UserRole

from features.course.model import OfferingComponent
from tests.conftest import Factories

OFFERINGS = "/api/admin/offerings"


async def _admin_headers(auth_headers: Any, factories: Factories) -> dict[str, str]:
    return await auth_headers(await factories.user(role=UserRole.ADMIN.value))


async def _seed(factories: Factories, **course_overrides: Any) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(units=3, **course_overrides)
    offering = await factories.offering(course, program, year_level)
    return {
        "program": program,
        "year_level": year_level,
        "course": course,
        "offering": offering,
    }


def _offering_payload(
    seed: dict[str, Any], components: list[dict[str, Any]]
) -> dict[str, Any]:
    first = components[0]
    return {
        "course_id": seed["course"].id,
        "program_id": seed["program"].id,
        "year_level_id": seed["year_level"].id,
        "semester": "1st Sem",
        "academic_year": "2026-2027",
        "sessions_per_week": len(components),
        "schedule_days": first["schedule_days"],
        "schedule_start_time": first["schedule_start_time"],
        "schedule_end_time": first["schedule_end_time"],
        "components": components,
    }


def _mon_tue_valid() -> list[dict[str, Any]]:
    # Mon 07:00-08:30 (1.5h) + Tue 13:00-14:30 (1.5h) = 3.0h on a 3u course.
    return [
        {
            "session_type": "lecture",
            "schedule_days": "M",
            "schedule_start_time": "07:00:00",
            "schedule_end_time": "08:30:00",
        },
        {
            "session_type": "lecture",
            "schedule_days": "T",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "14:30:00",
        },
    ]


def _mon_tue_over() -> list[dict[str, Any]]:
    # Mon 07:00-08:30 (1.5h) + Tue 13:00-15:00 (2h) = 3.5h > 3u.
    rows = _mon_tue_valid()
    rows[1] = {**rows[1], "schedule_end_time": "15:00:00"}
    return rows


async def test_create_offering_at_cap_is_201(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(
        OFFERINGS, json=_offering_payload(seed, _mon_tue_valid()), headers=headers
    )

    assert response.status_code == 201, response.text
    assert len(response.json()["components"]) == 2


async def test_create_offering_over_cap_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(
        OFFERINGS, json=_offering_payload(seed, _mon_tue_over()), headers=headers
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "weekly_hours_exceed_units"
    assert detail["field"] == "components"


async def test_create_offering_under_requirement_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    # A single Mon 07:00-08:30 meeting is 1.5h on a 3u course: short, not exact.
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    response = await api_client.post(
        OFFERINGS,
        json=_offering_payload(seed, _mon_tue_valid()[:1]),
        headers=headers,
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "weekly_hours_below_units"
    assert detail["field"] == "components"


async def test_multi_day_row_counts_each_day(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """One MWF 08:00-09:00 row is 3h, not 1h; adding a 4th hour is 422."""
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    at_cap = await api_client.post(
        OFFERINGS,
        json=_offering_payload(
            seed,
            [
                {
                    "session_type": "lecture",
                    "schedule_days": "MWF",
                    "schedule_start_time": "08:00:00",
                    "schedule_end_time": "09:00:00",
                }
            ],
        ),
        headers=headers,
    )
    assert at_cap.status_code == 201, at_cap.text

    seed2 = await _seed(factories)
    over = await api_client.post(
        OFFERINGS,
        json=_offering_payload(
            seed2,
            [
                {
                    "session_type": "lecture",
                    "schedule_days": "MWF",
                    "schedule_start_time": "08:00:00",
                    "schedule_end_time": "09:00:00",
                },
                {
                    "session_type": "lab",
                    "schedule_days": "M",
                    "schedule_start_time": "10:00:00",
                    "schedule_end_time": "11:00:00",
                },
            ],
        ),
        headers=headers,
    )
    assert over.status_code == 422
    assert over.json()["detail"]["code"] == "weekly_hours_exceed_units"


async def test_component_add_converges_or_blocks(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Incremental builds converge; overshoot crossings are rejected.

    The factory-seeded offering carries no components (total 0, under side).
    Adding Mon 1.5h moves closer without crossing, so it passes; adding Tue
    2h next would cross into over (3.5h), so it 422s; adding Tue 1.5h lands
    exactly on the 3u requirement, so it passes.
    """
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    first = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lecture",
            "schedule_days": "M",
            "schedule_start_time": "07:00:00",
            "schedule_end_time": "08:30:00",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text

    overshoot = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lecture",
            "schedule_days": "T",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "15:00:00",
        },
        headers=headers,
    )
    assert overshoot.status_code == 422
    assert overshoot.json()["detail"]["code"] == "weekly_hours_exceed_units"

    within = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lecture",
            "schedule_days": "T",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "14:30:00",
        },
        headers=headers,
    )
    assert within.status_code == 201, within.text


async def test_component_edit_reshapes_freely(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Reshape edits are unconstrained (D81): a multi-step schedule change
    passes through mismatched totals no single write could land exactly on.
    Only adds (and creation/reactivation) must converge."""
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    mon = await db_factory(
        OfferingComponent,
        offering_id=offering_id,
        session_type="lecture",
        schedule_days="M",
        schedule_start_time=time(7, 0),
        schedule_end_time=time(8, 30),
        is_active=True,
    )
    headers = await _admin_headers(auth_headers, factories)

    # Lengthen past the requirement, then back through it: both save, because
    # plain edits never face the weekly check.
    longer = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{mon.id}",
        json={"schedule_end_time": "09:30:00"},
        headers=headers,
    )
    assert longer.status_code == 200, longer.text

    crossing = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{mon.id}",
        json={"schedule_end_time": "10:30:00"},
        headers=headers,
    )
    assert crossing.status_code == 200, crossing.text

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.status_code == 200


async def test_reshape_through_mismatch_back_to_exact(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The user's reshape: exact 3.0h (Mon + Tue 1.5h), lengthen Tue into
    over, shorten Mon back — every step saves, the last lands exact."""
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    created = await api_client.post(
        OFFERINGS, json=_offering_payload(seed, _mon_tue_valid()), headers=headers
    )
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]
    by_days = {c["schedule_days"]: c["id"] for c in created.json()["components"]}

    stretch = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{by_days['T']}",
        json={"schedule_end_time": "15:00:00"},
        headers=headers,
    )
    assert stretch.status_code == 200, stretch.text

    shrink = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{by_days['M']}",
        json={"schedule_end_time": "08:00:00"},
        headers=headers,
    )
    assert shrink.status_code == 200, shrink.text

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["components"]) == 2


async def _seed_over_limit(
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    tue_end: time = time(15, 30),
) -> dict[str, Any]:
    """Insert components directly (bypassing the service) to simulate a
    legacy over-limit row: Mon 07:00-08:30 (1.5h) + Tue 13:00-tue_end."""
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    mon = await db_factory(
        OfferingComponent,
        offering_id=offering_id,
        session_type="lecture",
        schedule_days="M",
        schedule_start_time=time(7, 0),
        schedule_end_time=time(8, 30),
        is_active=True,
    )
    tue = await db_factory(
        OfferingComponent,
        offering_id=offering_id,
        session_type="lecture",
        schedule_days="T",
        schedule_start_time=time(13, 0),
        schedule_end_time=tue_end,
        is_active=True,
    )
    seed["mon"] = mon
    seed["tue"] = tue
    return seed


async def test_over_limit_offering_stays_readable_and_edits_down(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    seed = await _seed_over_limit(factories, db_factory, tue_end=time(15, 0))
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    # Reads are free for grandfathered rows.
    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["components"]) == 2

    # Decreasing the overage back to the cap is allowed.
    reduced = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{seed['tue'].id}",
        json={"schedule_end_time": "14:30:00"},
        headers=headers,
    )
    assert reduced.status_code == 200, reduced.text


async def test_over_limit_decrease_while_still_over_is_allowed(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    # 1.5h + 2.5h = 4.0h on 3u; shrinking Tue to 2.0h (3.5h total) moves
    # downward while staying over, so it must pass.
    seed = await _seed_over_limit(factories, db_factory, tue_end=time(15, 30))
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    reduced = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{seed['tue'].id}",
        json={"schedule_end_time": "15:00:00"},
        headers=headers,
    )
    assert reduced.status_code == 200, reduced.text


async def test_over_limit_edit_free_but_add_blocked(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    # Plain edits never face the weekly check (D81), so growing an
    # over-limit row further still saves; growing it via *add* must converge
    # and is rejected, while room-only edits and archives always pass.
    seed = await _seed_over_limit(factories, db_factory, tue_end=time(15, 0))
    offering_id = seed["offering"].id
    tue_id = seed["tue"].id
    headers = await _admin_headers(auth_headers, factories)
    # The first write below fails, and a failing request rolls back the
    # uncommitted seed — commit first so the admin user and rows survive it.
    await test_db_session.commit()

    grown = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{tue_id}",
        json={"schedule_end_time": "16:00:00"},
        headers=headers,
    )
    assert grown.status_code == 200, grown.text

    # A room-only edit leaves the total untouched and must stay possible.
    room = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{tue_id}",
        json={"classroom_name": "Room 101"},
        headers=headers,
    )
    assert room.status_code == 200, room.text

    added = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "W",
            "schedule_start_time": "09:00:00",
            "schedule_end_time": "10:00:00",
        },
        headers=headers,
    )
    assert added.status_code == 422
    assert added.json()["detail"]["code"] == "weekly_hours_exceed_units"

    archived = await api_client.delete(
        f"{OFFERINGS}/{offering_id}/components/{tue_id}", headers=headers
    )
    assert archived.status_code == 204


async def test_reactivating_a_component_revalidates_the_total(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Build an exact 3.0h schedule, swap a meeting, then prove reactivating
    the archived row back on top is rejected while reactivating into an
    exact total passes."""
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    created = await api_client.post(
        OFFERINGS, json=_offering_payload(seed, _mon_tue_valid()), headers=headers
    )
    assert created.status_code == 201, created.text
    exact_id = created.json()["id"]
    tue_id = next(
        c["id"] for c in created.json()["components"] if c["schedule_days"] == "T"
    )

    archived = await api_client.delete(
        f"{OFFERINGS}/{exact_id}/components/{tue_id}", headers=headers
    )
    assert archived.status_code == 204

    replacement = await api_client.post(
        f"{OFFERINGS}/{exact_id}/components",
        json={
            "session_type": "lab",
            "schedule_days": "W",
            "schedule_start_time": "13:00:00",
            "schedule_end_time": "14:30:00",
            "classroom_lat": 14.0,
            "classroom_lng": 121.0,
        },
        headers=headers,
    )
    assert replacement.status_code == 201, replacement.text
    wed_id = replacement.json()["id"]

    # Reactivating Tue on top of the exact schedule would reach 4.5h.
    revived_over = await api_client.patch(
        f"{OFFERINGS}/{exact_id}/components/{tue_id}",
        json={"is_active": True},
        headers=headers,
    )
    assert revived_over.status_code == 422
    assert revived_over.json()["detail"]["code"] == "weekly_hours_exceed_units"

    # Archive the replacement first, then reactivating lands exactly on 3.0h.
    await api_client.delete(
        f"{OFFERINGS}/{exact_id}/components/{wed_id}", headers=headers
    )
    revived_exact = await api_client.patch(
        f"{OFFERINGS}/{exact_id}/components/{tue_id}",
        json={"is_active": True},
        headers=headers,
    )
    assert revived_exact.status_code == 200, revived_exact.text


# --- sessions_per_week auto-count (D80) --------------------------------------
#
# One session per meeting day: a multi-day row counts each of its days. The
# stored column is re-synced on every component write, so the value the risk
# batch reads never drifts from the meetings.


async def test_create_counts_days_not_rows(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)

    # One MWF 08:00-09:00 row is 3h on a 3u course and 3 sessions — even
    # though the payload still carries sessions_per_week=1, the service
    # recomputes it from the components.
    multi = await api_client.post(
        OFFERINGS,
        json=_offering_payload(
            seed,
            [
                {
                    "session_type": "lecture",
                    "schedule_days": "MWF",
                    "schedule_start_time": "08:00:00",
                    "schedule_end_time": "09:00:00",
                }
            ],
        ),
        headers=headers,
    )
    assert multi.status_code == 201, multi.text
    assert multi.json()["sessions_per_week"] == 3

    seed2 = await _seed(factories)
    two_rows = await api_client.post(
        OFFERINGS, json=_offering_payload(seed2, _mon_tue_valid()), headers=headers
    )
    assert two_rows.status_code == 201, two_rows.text
    assert two_rows.json()["sessions_per_week"] == 2


async def test_component_mutations_resync_the_count(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    offering_id = seed["offering"].id
    headers = await _admin_headers(auth_headers, factories)

    added = await api_client.post(
        f"{OFFERINGS}/{offering_id}/components",
        json={
            "session_type": "lecture",
            "schedule_days": "M",
            "schedule_start_time": "07:00:00",
            "schedule_end_time": "08:30:00",
        },
        headers=headers,
    )
    assert added.status_code == 201, added.text
    component_id = added.json()["id"]

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.json()["sessions_per_week"] == 1

    # Lengthen Mon onto Wed too: 1.5h x 2 days lands exactly on the 3u total.
    widened = await api_client.patch(
        f"{OFFERINGS}/{offering_id}/components/{component_id}",
        json={"schedule_days": "MW"},
        headers=headers,
    )
    assert widened.status_code == 200, widened.text

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.json()["sessions_per_week"] == 2

    archived = await api_client.delete(
        f"{OFFERINGS}/{offering_id}/components/{component_id}", headers=headers
    )
    assert archived.status_code == 204

    fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
    assert fetched.json()["sessions_per_week"] == 0


# --- activation gate (D82) ---------------------------------------------------
#
# Only the inactive -> active transition is checked. Deactivation, unrelated
# PATCHes, and already-active rows are unaffected, including the zero-meeting
# case (which mismatches every positive units value).


async def _seed_inactive(
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    meetings: list[tuple[str, time, time]],
) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(units=3)
    offering = await factories.offering(course, program, year_level, is_active=False)
    for days, start, end in meetings:
        await db_factory(
            OfferingComponent,
            offering_id=offering.id,
            session_type="lecture",
            schedule_days=days,
            schedule_start_time=start,
            schedule_end_time=end,
            is_active=True,
        )
    return {"offering": offering}


async def test_activate_exact_offering_is_200(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, factories)
    created = await api_client.post(
        OFFERINGS, json=_offering_payload(seed, _mon_tue_valid()), headers=headers
    )
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]

    down = await api_client.patch(
        f"{OFFERINGS}/{offering_id}", json={"is_active": False}, headers=headers
    )
    assert down.status_code == 200

    up = await api_client.patch(
        f"{OFFERINGS}/{offering_id}", json={"is_active": True}, headers=headers
    )
    assert up.status_code == 200, up.text
    assert up.json()["is_active"] is True


async def test_activate_mismatched_offering_is_422(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    # A failing request rolls back the uncommitted seed — commit first.
    over = await _seed_inactive(
        factories,
        db_factory,
        [("M", time(7, 0), time(8, 30)), ("T", time(13, 0), time(15, 0))],
    )
    under = await _seed_inactive(
        factories, db_factory, [("M", time(7, 0), time(8, 30))]
    )
    empty = await _seed_inactive(factories, db_factory, [])
    await test_db_session.commit()
    # Copy ids now: each failing request rolls back, which expires every ORM
    # instance in the session (same hazard as the component tests).
    offering_ids = [seed_case["offering"].id for seed_case in (over, under, empty)]

    for offering_id in offering_ids:
        response = await api_client.patch(
            f"{OFFERINGS}/{offering_id}",
            json={"is_active": True},
            headers=headers,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "schedule_mismatch"
        assert detail["field"] == "is_active"

    # The rows stay inactive after the rejected transitions.
    for offering_id in offering_ids:
        fetched = await api_client.get(f"{OFFERINGS}/{offering_id}", headers=headers)
        assert fetched.json()["is_active"] is False


async def test_deactivate_and_unrelated_patch_ignore_the_gate(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    db_factory: Callable[..., Coroutine[Any, Any, Any]],
    test_db_session: Any,
) -> None:
    headers = await _admin_headers(auth_headers, factories)
    seed = await _seed_over_limit(factories, db_factory, tue_end=time(15, 0))
    offering_id = seed["offering"].id
    await test_db_session.commit()

    down = await api_client.patch(
        f"{OFFERINGS}/{offering_id}", json={"is_active": False}, headers=headers
    )
    assert down.status_code == 200

    untouched = await api_client.patch(
        f"{OFFERINGS}/{offering_id}",
        json={"classroom_name": "Room 202"},
        headers=headers,
    )
    assert untouched.status_code == 200, untouched.text
