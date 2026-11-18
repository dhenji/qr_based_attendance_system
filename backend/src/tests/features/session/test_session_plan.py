"""The session plan resolver (D93).

The plan is what a session inherits from its offering: the meeting it
belongs to, the next occurrence of that meeting, the attendance windows, the
classroom and the geofence radius. These tests pin the rules that decide
which of those apply:

* a meeting that is still running today is today's; one that has already
  ended rolls to the next meeting day;
* the day letters mean what `student/service.py::_meets_on` always meant
  (T = Tuesday, H = Thursday, U = Sunday);
* an offering with active components has no plan for a type it does not
  configure — the offering-level columns are a stale mirror, not a fallback;
* the radius resolves payload -> offering -> app setting -> env.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timezone
from typing import Any

from core.config import Settings

from shared.enums import SessionType
from shared.schedule import day_weekdays, meeting_length_minutes

from features.course.model import CourseOffering, OfferingComponent
from features.session.plan import (
    active_components,
    next_meeting,
    resolve_session_plan,
)
from features.system.model import AppSetting

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)  # a Wednesday
SETTINGS = Settings(debug=True, jwt_secret="test-secret-0123456789abcdef")


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    """Dispatches `scalars` on the queried entity, like the session tests."""

    def __init__(self, rows: dict | None = None) -> None:
        self.rows = rows or {}
        self.statements: list[Any] = []

    async def scalars(self, stmt: Any) -> _FakeResult:
        self.statements.append(stmt)
        entity = stmt.column_descriptions[0].get("entity")
        found = self.rows.get(entity, [])

        return _FakeResult(list(found))

    async def get(self, model: Any, ident: Any) -> Any:
        return None


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _offering(**overrides: Any) -> CourseOffering:
    values: dict[str, Any] = {
        "id": 10,
        "course_id": 1,
        "program_id": 1,
        "year_level_id": 1,
        "semester": "1ST",
        "academic_year": "2026-2027",
        "sessions_per_week": 3,
        "schedule_days": "MWF",
        "schedule_start_time": time(9, 0),
        "schedule_end_time": time(10, 0),
        "classroom_name": "Room 101",
        "classroom_lat": 14.5,
        "classroom_lng": 121.0,
        "default_present_window_minutes": 5,
        "default_late_window_minutes": 10,
        "default_classroom_radius_meters": None,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return CourseOffering(**values)


def _component(session_type: str = "lecture", **overrides: Any) -> OfferingComponent:
    values: dict[str, Any] = {
        "id": 1,
        "offering_id": 10,
        "session_type": session_type,
        "schedule_days": "MWF",
        "schedule_start_time": time(9, 0),
        "schedule_end_time": time(10, 30),
        "classroom_name": "Lab 2",
        "classroom_lat": 1.5,
        "classroom_lng": 2.5,
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return OfferingComponent(**values)


class _Course:
    """Just enough of a Course for the resolver's duration fallback."""

    def __init__(self, session_duration_hours: float = 2.0) -> None:
        self.session_duration_hours = session_duration_hours


# --- day letters ---------------------------------------------------------


def test_day_weekdays_maps_the_conventional_initials() -> None:
    assert day_weekdays("MWF") == {0, 2, 4}
    # T is Tuesday, H is Thursday (T was already taken), U is Sunday (S is
    # Saturday) — the reading `student/service.py::_meets_on` always used.
    assert day_weekdays("THU") == {1, 3, 6}
    assert day_weekdays("S") == {5}


def test_day_weekdays_ignores_unknown_letters_and_is_case_insensitive() -> None:
    assert day_weekdays("mwf") == {0, 2, 4}
    assert day_weekdays("MX") == {0}
    assert day_weekdays("") == set()
    assert day_weekdays(None) == set()


def test_meeting_length_minutes_is_zero_for_an_inverted_pair() -> None:
    assert meeting_length_minutes(time(9, 0), time(10, 30)) == 90
    assert meeting_length_minutes(time(10, 0), time(9, 0)) == 0
    assert meeting_length_minutes(time(9, 0), time(9, 0)) == 0


# --- next meeting --------------------------------------------------------


def test_next_meeting_is_today_while_the_class_is_still_running() -> None:
    # NOW is Wednesday 2026-10-21 12:00Z; the class runs 13:00-14:30.
    found = next_meeting(
        days="MWF",
        start=time(13, 0),
        end=time(14, 30),
        now=NOW,
        zone=timezone.utc,
    )

    assert found is not None
    day, start, end = found
    assert day == date(2026, 10, 21)
    assert start == datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 21, 14, 30, tzinfo=timezone.utc)


def test_next_meeting_rolls_to_the_next_meeting_day_once_the_class_ended() -> None:
    # A 09:00-10:00 class that ended at 10:00Z is over by noon.
    found = next_meeting(
        days="MWF",
        start=time(9, 0),
        end=time(10, 0),
        now=NOW,
        zone=timezone.utc,
    )

    assert found is not None
    day, _start, _end = found
    assert day == date(2026, 10, 23)  # Friday


def test_next_meeting_skips_to_the_next_meeting_day_when_today_is_not_one() -> None:
    # Monday-only meeting, opened on a Wednesday.
    found = next_meeting(
        days="M",
        start=time(9, 0),
        end=time(10, 0),
        now=NOW,
        zone=timezone.utc,
    )

    assert found is not None
    day, _start, _end = found
    assert day == date(2026, 10, 26)  # the following Monday


def test_next_meeting_is_none_without_a_usable_schedule() -> None:
    assert (
        next_meeting(
            days="", start=time(9, 0), end=time(10, 0), now=NOW, zone=timezone.utc
        )
        is None
    )
    assert (
        next_meeting(
            days="MWF",
            start=time(10, 0),
            end=time(9, 0),
            now=NOW,
            zone=timezone.utc,
        )
        is None
    )


def test_next_meeting_interprets_wall_clock_in_the_given_zone() -> None:
    from zoneinfo import ZoneInfo

    # 08:30 in Manila is 00:30Z, so the 09:00 Manila class is still ahead.
    now = datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc)
    found = next_meeting(
        days="W",
        start=time(9, 0),
        end=time(10, 0),
        now=now,
        zone=ZoneInfo("Asia/Manila"),
    )

    assert found is not None
    day, start, end = found
    assert day == date(2026, 10, 21)
    assert start == datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)


# --- source selection ----------------------------------------------------


def test_plan_uses_the_matching_component() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(),
            course=_Course(),
            components=[_component("lecture")],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.source == "component"
    assert plan.has_meeting
    assert plan.start_time == time(9, 0)
    assert plan.end_time == time(10, 30)
    assert plan.duration_minutes == 90
    # The component's room wins over the offering's.
    assert plan.classroom_name == "Lab 2"
    assert plan.classroom_lat == 1.5


def test_plan_falls_back_to_the_offering_columns_without_components() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.source == "offering_legacy"
    assert plan.has_meeting
    assert plan.duration_minutes == 60
    assert plan.classroom_name == "Room 101"


def test_plan_has_no_meeting_for_a_type_the_offering_does_not_configure() -> None:
    # A lecture-only offering has no laboratory schedule to inherit, and the
    # offering-level columns are a stale mirror of the lone lecture meeting.
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(),
            course=_Course(),
            components=[_component("lecture")],
            session_type=SessionType.LAB,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.source == "course_default"
    assert not plan.has_meeting
    assert plan.scheduled_start is None
    # The duration still falls back to the course template.
    assert plan.duration_minutes == 120


def test_plan_falls_back_to_the_course_duration_for_an_unusable_schedule() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(schedule_days="", schedule_end_time=time(8, 0)),
            course=_Course(session_duration_hours=1.5),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.source == "course_default"
    assert not plan.has_meeting
    assert plan.duration_minutes == 90


# --- windows, classroom and radius ---------------------------------------


def test_plan_inherits_the_offering_windows() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(
                default_present_window_minutes=40, default_late_window_minutes=30
            ),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.present_window_minutes == 40
    assert plan.late_window_minutes == 30


def test_plan_falls_back_to_the_app_window_defaults() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(
                default_present_window_minutes=None, default_late_window_minutes=None
            ),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.present_window_minutes == SETTINGS.default_present_window_minutes
    assert plan.late_window_minutes == SETTINGS.default_late_window_minutes


def test_radius_prefers_the_offering_value() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(default_classroom_radius_meters=120),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.radius_meters == 120


def _setting(key: str, value: str) -> AppSetting:
    return AppSetting(id=1, key=key, value=value, created_at=NOW, updated_at=NOW)


def test_the_windows_follow_the_system_default_when_the_offering_has_none() -> None:
    """D93: NULL on the offering means "follow the system default".

    The app setting an administrator edits in Admin -> System Settings used
    to be dead for the windows — the offering's NOT NULL default always won
    — exactly like the geofence radius.
    """
    session = _FakeSession(
        rows={AppSetting: [_setting("present_window_default", "12")]}
    )

    plan = _run(
        resolve_session_plan(
            session,
            offering=_offering(
                default_present_window_minutes=None, default_late_window_minutes=None
            ),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.present_window_minutes == 12
    assert plan.late_window_minutes == SETTINGS.default_late_window_minutes


def test_an_explicit_offering_window_beats_the_system_default() -> None:
    session = _FakeSession(
        rows={AppSetting: [_setting("present_window_default", "12")]}
    )

    plan = _run(
        resolve_session_plan(
            session,
            offering=_offering(
                default_present_window_minutes=7, default_late_window_minutes=3
            ),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.present_window_minutes == 7
    assert plan.late_window_minutes == 3


def test_the_late_window_follows_the_system_default_too() -> None:
    session = _FakeSession(rows={AppSetting: [_setting("late_window_default", "20")]})

    plan = _run(
        resolve_session_plan(
            session,
            offering=_offering(
                default_present_window_minutes=None, default_late_window_minutes=None
            ),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.late_window_minutes == 20


def test_radius_falls_back_to_the_app_setting() -> None:
    """The admin's System Settings radius used to be ignored entirely."""
    session = _FakeSession(
        rows={
            AppSetting: [
                AppSetting(
                    id=1,
                    key="geofence_default_radius",
                    value="75",
                    created_at=NOW,
                    updated_at=NOW,
                )
            ]
        }
    )

    plan = _run(
        resolve_session_plan(
            session,
            offering=_offering(),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.radius_meters == 75


def test_radius_falls_back_to_the_environment_default() -> None:
    plan = _run(
        resolve_session_plan(
            _FakeSession(),
            offering=_offering(),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.radius_meters == SETTINGS.default_geofence_radius_meters


def test_a_broken_app_setting_falls_back_to_the_environment_default() -> None:
    session = _FakeSession(
        rows={
            AppSetting: [
                AppSetting(
                    id=1,
                    key="geofence_default_radius",
                    value="not-a-number",
                    created_at=NOW,
                    updated_at=NOW,
                )
            ]
        }
    )

    plan = _run(
        resolve_session_plan(
            session,
            offering=_offering(),
            course=_Course(),
            components=[],
            session_type=SessionType.LECTURE,
            now=NOW,
            settings=SETTINGS,
        )
    )

    assert plan.radius_meters == SETTINGS.default_geofence_radius_meters


# --- the components query ------------------------------------------------


def test_active_components_queries_only_the_active_rows_of_the_offering() -> None:
    session = _FakeSession(rows={OfferingComponent: [_component("lecture")]})

    rows = _run(active_components(session, offering_id=10))

    assert [row.session_type for row in rows] == ["lecture"]
    sql = str(session.statements[0])
    assert "offering_components" in sql
    assert "is_active" in sql
