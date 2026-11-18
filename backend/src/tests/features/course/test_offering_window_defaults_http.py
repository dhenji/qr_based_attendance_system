"""The offering's attendance windows over HTTP (D93).

The offering's window columns are nullable, and NULL means "follow the
system default" — the `app_settings` row an administrator edits in Admin ->
System Settings. These cases pin the round trip an administrator actually
performs: set a value, read it back, clear it, read it back as null.
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole

from tests.conftest import Factories


async def _seed(factories: Factories) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course(session_duration_hours=2.0)
    offering = await factories.offering(course, program, year_level)
    admin = await factories.user(role=UserRole.ADMIN.value)
    return {"offering": offering, "admin": admin}


async def test_the_windows_round_trip_and_clear(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await auth_headers(seed["admin"])
    path = f"/api/admin/offerings/{seed['offering'].id}"

    # A new offering carries no window of its own — it follows the system
    # default until an administrator says otherwise.
    read = await api_client.get(path, headers=headers)
    assert read.status_code == 200
    assert read.json()["default_present_window_minutes"] is None
    assert read.json()["default_late_window_minutes"] is None

    # An explicit value is stored and read back.
    response = await api_client.patch(
        path,
        json={
            "default_present_window_minutes": 8,
            "default_late_window_minutes": 4,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default_present_window_minutes"] == 8
    assert body["default_late_window_minutes"] == 4

    # An explicit null puts the offering back on the system default.
    cleared = await api_client.patch(
        path,
        json={
            "default_present_window_minutes": None,
            "default_late_window_minutes": None,
        },
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["default_present_window_minutes"] is None
    assert cleared.json()["default_late_window_minutes"] is None


async def test_the_radius_round_trips_and_clears(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """D93: the radius override follows the same inherit/override shape."""
    seed = await _seed(factories)
    headers = await auth_headers(seed["admin"])
    path = f"/api/admin/offerings/{seed['offering'].id}"

    response = await api_client.patch(
        path, json={"default_classroom_radius_meters": 120}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["default_classroom_radius_meters"] == 120

    cleared = await api_client.patch(
        path, json={"default_classroom_radius_meters": None}, headers=headers
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["default_classroom_radius_meters"] is None
