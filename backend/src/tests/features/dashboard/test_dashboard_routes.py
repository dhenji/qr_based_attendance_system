"""The three dashboard summaries.

Each is an aggregate over features it does not own, which is why they live in
their own slice — see `features/dashboard/service.py`. What these tests protect
is mostly *agreement*: a dashboard that reports a different number from the page
sitting above it is worse than no dashboard at all, so the recurring assertion
here is "same as the component endpoint" rather than a hard-coded expectation.

Three areas deserve their own attention:

**Empty states divide by zero.** A new student with no enrollments, a professor
who has not opened a session, a system with no programs. Every rate has to come
back `0.0` and every list `[]`, never a 500. `_rates` already guards
`enrolled <= 0`; the dashboard's own counts are guarded by `or 0`.

**Identity comes from the token.** The student dashboard takes no parameter and
must never show another student's scans, and a student token on the professor or
admin dashboard is a 403.

**Roster size is not enrolled-and-in-scope.** `student_count` counts active
roster rows. It is deliberately *not* the analytics overview's `total_students`,
which counts students enrolled in a session inside a filter; conflating them
would make the dashboard disagree with the admin list page.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import QueueStatus, UserRole

from features.attendance.model import Attendance
from features.auth.model import User
from features.enrollment.model import Enrollment
from features.program.model import Program
from features.session.model import Session
from features.student.model import Student
from features.student.service import _meets_on
from features.sync.model import SyncQueue
from tests.conftest import Factories


async def _student_graph(
    factories: Factories, *, schedule_days: str = "MWF", scanned_today: int = 0
) -> dict[str, Any]:
    """A student with one offering, optionally with scans in and out of today.

    `full_stack` links the account to the roster row, which the dashboard needs
    because it resolves the student from `users.id`.
    """
    graph = await factories.full_stack()
    student = graph["student"]
    user = graph["user"]

    # `full_stack(**overrides)` forwards to `factories.session()`, not to the
    # offering, so `schedule_days` is set on the offering directly.
    graph["offering"].schedule_days = schedule_days

    for index in range(scanned_today):
        moment = datetime.now(timezone.utc) - timedelta(minutes=index)
        db_session = await factories.session(
            graph["offering"], graph["professor"], scheduled_start_time=moment
        )
        await factories.attendance(student, db_session, timestamp=moment)

    if scanned_today:
        # One scan yesterday, to prove `scans_today` is a window and not a total.
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        old = await factories.session(
            graph["offering"], graph["professor"], scheduled_start_time=yesterday
        )
        await factories.attendance(student, old, timestamp=yesterday)

    graph["user"] = user
    return graph


def _code(response: Any) -> str:
    return response.json()["detail"]["code"]


# -- the schedule-day alphabet (pure function, so testable for every weekday) --


def test_every_day_initial_maps_to_its_weekday() -> None:
    """All seven letters, checked against real dates rather than the live clock.

    The route tests can only ever assert today's letter, which is how a broken
    mapping for the other six would ship. `2026-10-05` is a Monday.
    """
    letters = "MTWHFSU"
    monday = date(2026, 10, 5)

    for index, letter in enumerate(letters):
        day = monday + timedelta(days=index)
        assert _meets_on(letter, day), f"{letter} should match {day:%A}"
        # And nothing else matches that day.
        others = [other for other in letters if other != letter]
        assert not any(_meets_on(other, day) for other in others), (
            f"{letter} should not be the only match confusion-free on {day:%A}"
        )


def test_multi_day_schedules_match_every_listed_day() -> None:
    monday = date(2026, 10, 5)

    assert _meets_on("MWF", monday)  # Monday
    assert _meets_on("MWF", monday + timedelta(days=2))  # Wednesday
    assert _meets_on("MWF", monday + timedelta(days=4))  # Friday
    assert not _meets_on("MWF", monday + timedelta(days=1))  # Tuesday
    assert not _meets_on("MWF", monday + timedelta(days=3))  # Thursday
    assert not _meets_on("MWF", monday + timedelta(days=5))  # Saturday


def test_t_is_tuesday_and_h_is_thursday() -> None:
    """The ambiguity, pinned.

    The seed writes "TF" for Tuesday/Friday, while wireframes.md:1387 writes
    "TTH" — where the trailing H stands in for Thursday precisely because T was
    already taken. Reading T as Thursday would put half the school on the wrong
    day.
    """
    monday = date(2026, 10, 5)

    assert _meets_on("T", monday + timedelta(days=1))  # Tuesday
    assert not _meets_on("T", monday + timedelta(days=3))  # not Thursday
    assert _meets_on("H", monday + timedelta(days=3))  # Thursday
    assert not _meets_on("H", monday + timedelta(days=1))  # not Tuesday

    # "TTH" therefore means Tuesday + Thursday.
    assert _meets_on("TTH", monday + timedelta(days=1))
    assert _meets_on("TTH", monday + timedelta(days=3))
    assert not _meets_on("TTH", monday)


def test_unrecognised_letters_match_nothing_rather_than_raising() -> None:
    """One offering with a typo must not break a student's whole dashboard."""
    day = date(2026, 10, 5)

    assert not _meets_on("XX", day)
    assert not _meets_on("", day)
    assert not _meets_on(None, day)
    # A valid letter alongside a junk one still matches.
    assert _meets_on("MX", day)


# -- student ----------------------------------------------------------------


async def test_student_dashboard_reports_the_history_compliance_rate(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The headline must be the same number the history endpoint reports."""

    graph = await _student_graph(factories, scanned_today=3)
    headers = await auth_headers(graph["user"])

    dashboard = await api_client.get("/api/student/dashboard", headers=headers)
    history = await api_client.get("/api/student/attendance/history", headers=headers)

    assert dashboard.status_code == 200
    assert (
        dashboard.json()["compliance_rate"]
        == history.json()["summary"]["compliance_rate"]
    )


async def test_student_dashboard_counts_today_separately_from_all_time(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _student_graph(factories, scanned_today=3)

    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(graph["user"])
        )
    ).json()

    assert body["scans_today"] == 3
    assert body["total_scans"] == 4  # three today plus one yesterday


async def test_student_dashboard_lists_todays_classes_only(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """`today_schedule` filters by weekday; an MWF class must not show on a Sunday.

    The letters come from `schedule_days`, and the day boundary is UTC — see the
    service module docstring.
    """
    today = datetime.now(timezone.utc)
    weekday_letters = "MTWHFSU"
    meets_today = weekday_letters[today.weekday()]

    graph = await _student_graph(factories, schedule_days=meets_today)
    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(graph["user"])
        )
    ).json()

    assert len(body["today_schedule"]) == 1
    assert body["today_schedule"][0]["course_code"] == graph["course"].course_code


async def test_student_dashboard_omits_classes_that_do_not_meet_today(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    today = datetime.now(timezone.utc)
    # Pick two weekdays that are definitely not today.
    others = [letter for i, letter in enumerate("MTWHFSU") if i != today.weekday()][:2]

    graph = await _student_graph(factories, schedule_days="".join(others))
    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(graph["user"])
        )
    ).json()

    assert body["today_schedule"] == []


async def test_student_dashboard_recent_activity_is_newest_first(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _student_graph(factories, scanned_today=3)

    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(graph["user"])
        )
    ).json()

    stamps = [entry["scanned_at"] for entry in body["recent_activity"]]
    assert stamps == sorted(stamps, reverse=True)
    assert all(entry["status"] for entry in body["recent_activity"])


async def test_student_dashboard_never_shows_another_student(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    mine = await _student_graph(factories, scanned_today=2)
    theirs_graph = await factories.full_stack()
    their_user = theirs_graph["user"]
    their_user.email = "dash.other@isu.edu.ph"
    await factories.attendance(
        theirs_graph["student"],
        theirs_graph["session"],
        timestamp=datetime.now(timezone.utc),
    )

    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(mine["user"])
        )
    ).json()

    session_ids = {entry["session_id"] for entry in body["recent_activity"]}
    assert session_ids
    assert theirs_graph["session"].id not in session_ids


async def test_student_dashboard_handles_an_empty_account(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """No scans and no enrollments: zeros and empty lists, not a 500."""
    program = await factories.program()
    user = await factories.user(role=UserRole.STUDENT.value)
    student = await factories.student(year_level=await factories.year_level(program))
    student.user_id = user.id

    response = await api_client.get(
        "/api/student/dashboard", headers=await auth_headers(user)
    )

    assert response.status_code == 200
    assert response.json() == {
        "compliance_rate": 0.0,
        "scans_today": 0,
        "total_scans": 0,
        "today_schedule": [],
        "recent_activity": [],
    }


async def test_student_dashboard_requires_a_student(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await auth_headers(role=UserRole.ADMIN.value)

    response = await api_client.get("/api/student/dashboard", headers=headers)

    assert response.status_code == 403
    assert _code(response) == "insufficient_permissions"


# -- professor --------------------------------------------------------------


async def test_professor_dashboard_counts_todays_sessions(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await factories.full_stack()
    professor = graph["professor"]
    user = await factories.user(
        email="dash.prof@isu.edu.ph", role=UserRole.PROFESSOR.value
    )
    professor.user_id = user.id

    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = now - midnight
    for index in range(2):
        # Started *and* expired in the past, so both read as closed. Sessions
        # have no status column: closed means `expires_at` is past.
        # Anchored to fractions of the elapsed day, not fixed offsets: a fixed
        # `now - 60min` falls on yesterday for any suite run inside the first
        # hour after midnight UTC, and the dashboard counts `created_at` by UTC
        # calendar day. The `expires_at` cap keeps "closed" true even there,
        # when `started + 20min` would otherwise land in the future.
        started = midnight + elapsed * (index + 1) // 3
        db_session = await factories.session(
            graph["offering"],
            professor,
            # `created_at` is the column every session query filters on, and it
            # is a server default -- a past `scheduled_start_time` alone would
            # still insert the row "now".
            created_at=started,
            scheduled_start_time=started,
            scheduled_end_time=started + timedelta(minutes=30),
            expires_at=min(started + timedelta(minutes=20), now - timedelta(minutes=1)),
        )
        await factories.attendance(graph["student"], db_session, timestamp=started)

    body = (
        await api_client.get(
            "/api/professor/dashboard", headers=await auth_headers(user)
        )
    ).json()

    # `full_stack` opens one session of its own (still live, so active), and this
    # test adds two expired ones: three today, two of them closed. Asserting 2
    # rather than 3 is what proves `sessions_completed` is derived from
    # `expires_at` instead of just mirroring `sessions_today`.
    assert body["sessions_today"] == 3
    assert body["sessions_completed"] == 2
    assert body["total_students"] == 1
    assert len(body["today_sessions"]) == 3
    # Only the two this test created carry a scan.
    assert sorted(tile["scanned"] for tile in body["today_sessions"]) == [0, 1, 1]
    assert all(tile["enrolled"] == 1 for tile in body["today_sessions"])


async def test_professor_dashboard_excludes_yesterdays_sessions(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await factories.full_stack()
    professor = graph["professor"]
    user = await factories.user(
        email="dash.prof@isu.edu.ph", role=UserRole.PROFESSOR.value
    )
    professor.user_id = user.id

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    stale = await factories.session(
        graph["offering"],
        professor,
        # The dashboard filters `created_at`, not `scheduled_start_time`.
        created_at=yesterday,
        scheduled_start_time=yesterday,
        scheduled_end_time=yesterday + timedelta(hours=1),
        expires_at=yesterday + timedelta(hours=1),
    )

    today_session = graph["session"]
    body = (
        await api_client.get(
            "/api/professor/dashboard", headers=await auth_headers(user)
        )
    ).json()

    # Only `full_stack`'s own session (created today) is in scope; yesterday's
    # must not be counted, and the tile list must not merely be the right length.
    assert body["sessions_today"] == 1
    assert [tile["session_id"] for tile in body["today_sessions"]] == [today_session.id]
    assert stale.id not in {tile["session_id"] for tile in body["today_sessions"]}


async def test_professor_dashboard_handles_a_professor_with_nothing(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    professor = await factories.professor()
    user = await factories.user(
        email="dash.idle@isu.edu.ph", role=UserRole.PROFESSOR.value
    )
    professor.user_id = user.id
    professor.year_level_id = year.id

    response = await api_client.get(
        "/api/professor/dashboard", headers=await auth_headers(user)
    )

    assert response.status_code == 200
    assert response.json() == {
        "sessions_today": 0,
        "sessions_completed": 0,
        "total_students": 0,
        "avg_rate": 0.0,
        "today_sessions": [],
    }


async def test_professor_dashboard_avg_rate_matches_the_reports_endpoint(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The headline rate is the reports figure, not a second implementation."""
    graph = await factories.full_stack()
    professor = graph["professor"]
    user = await factories.user(
        email="dash.prof@isu.edu.ph", role=UserRole.PROFESSOR.value
    )
    professor.user_id = user.id

    now = datetime.now(timezone.utc)
    for index, status in enumerate(["present", "present", "late"]):
        started = now - timedelta(days=index, minutes=5)
        db_session = await factories.session(
            graph["offering"],
            professor,
            created_at=started,
            scheduled_start_time=started,
            scheduled_end_time=started + timedelta(hours=1),
            expires_at=started + timedelta(hours=1),
        )
        await factories.attendance(
            graph["student"], db_session, validation_status=status, timestamp=started
        )

    headers = await auth_headers(user)
    dashboard = await api_client.get("/api/professor/dashboard", headers=headers)
    reports = await api_client.get(
        "/api/professor/reports/all-courses", headers=headers
    )

    assert dashboard.json()["avg_rate"] == reports.json()["avg_compliance"]


async def test_professor_dashboard_requires_a_professor(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    response = await api_client.get(
        "/api/professor/dashboard",
        headers=await auth_headers(role=UserRole.STUDENT.value),
    )

    assert response.status_code == 403
    assert _code(response) == "insufficient_permissions"


async def test_professor_dashboard_rejects_an_unclaimed_account(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """A professor token with no roster row cannot be resolved to a professor."""
    user = await factories.user(role=UserRole.PROFESSOR.value)

    response = await api_client.get(
        "/api/professor/dashboard", headers=await auth_headers(user)
    )

    assert response.status_code == 404
    assert _code(response) == "professor_not_found"


# -- admin ------------------------------------------------------------------


async def test_admin_dashboard_counts_the_active_roster(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    await factories.student(year_level=year)
    await factories.student(year_level=year, is_active=False)
    await factories.professor()
    await factories.user(
        email="dash.prof2@isu.edu.ph", role=UserRole.PROFESSOR.value, is_active=False
    )
    await test_db_session.commit()

    body = (
        await api_client.get(
            "/api/admin/dashboard",
            headers=await auth_headers(role=UserRole.ADMIN.value),
        )
    ).json()

    assert body["student_count"] == 1  # the archived one does not count
    assert body["professor_count"] == 1
    assert body["program_count"] == 1


async def test_admin_dashboard_excludes_archived_programs(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    await factories.program()
    await factories.program(is_active=False)

    body = (
        await api_client.get(
            "/api/admin/dashboard",
            headers=await auth_headers(role=UserRole.ADMIN.value),
        )
    ).json()

    assert body["program_count"] == 1


async def test_admin_dashboard_counts_scans_today_and_backlog(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    graph = await _student_graph(factories, scanned_today=2)
    test_db_session.add(
        SyncQueue(
            status=QueueStatus.PENDING.value,
            record_data={"student_id": graph["student"].id},
        )
    )
    await test_db_session.commit()

    body = (
        await api_client.get(
            "/api/admin/dashboard",
            headers=await auth_headers(role=UserRole.ADMIN.value),
        )
    ).json()

    assert body["scans_today"] == 2
    assert body["pending_sync"] == 1
    assert body["recent_scans"]


async def test_admin_dashboard_pending_sync_matches_the_settings_endpoint(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Both read the same number, so the two admin pages cannot disagree."""
    headers = await auth_headers(role=UserRole.ADMIN.value)

    dashboard = await api_client.get("/api/admin/dashboard", headers=headers)
    settings = await api_client.get("/api/admin/system/settings", headers=headers)

    assert dashboard.json()["pending_sync"] == settings.json()["pending_sync_count"]


async def test_admin_dashboard_avg_rate_matches_the_analytics_overview(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Compliance, not participation.

    Both are 0.0 on an empty system, so the agreement is only meaningful once
    there are scans — and the two numbers genuinely differ, since participation
    counts late and excused as attended.
    """
    graph = await factories.full_stack()
    now = datetime.now(timezone.utc)

    for index, status in enumerate(["present", "present", "late", "excused"]):
        started = now - timedelta(days=index, minutes=5)
        db_session = await factories.session(
            graph["offering"],
            graph["professor"],
            created_at=started,
            scheduled_start_time=started,
            scheduled_end_time=started + timedelta(hours=1),
            expires_at=started + timedelta(hours=1),
        )
        await factories.attendance(
            graph["student"], db_session, validation_status=status, timestamp=started
        )

    headers = await auth_headers(role=UserRole.ADMIN.value)
    dashboard = await api_client.get("/api/admin/dashboard", headers=headers)
    overview = await api_client.get("/api/admin/analytics/overview", headers=headers)

    assert dashboard.json()["avg_rate"] == overview.json()["avg_compliance_rate"]
    # Guard the guard: if these ever matched, the assertion above would be vacuous.
    assert (
        overview.json()["avg_compliance_rate"]
        != overview.json()["avg_participation_rate"]
    )


async def test_admin_dashboard_handles_an_empty_system(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    response = await api_client.get(
        "/api/admin/dashboard", headers=await auth_headers(role=UserRole.ADMIN.value)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["student_count"] == 0
    assert body["avg_rate"] == 0.0
    assert body["recent_scans"] == []


async def test_admin_dashboard_requires_an_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    response = await api_client.get(
        "/api/admin/dashboard",
        headers=await auth_headers(role=UserRole.PROFESSOR.value),
    )

    assert response.status_code == 403
    assert _code(response) == "insufficient_permissions"


async def test_super_admin_may_read_the_admin_dashboard(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    response = await api_client.get(
        "/api/admin/dashboard",
        headers=await auth_headers(role=UserRole.SUPER_ADMIN.value),
    )

    assert response.status_code == 200


# -- the read-only guarantee ------------------------------------------------


async def test_dashboard_reads_do_not_write_settings(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """`GET /admin/dashboard` must not create AppSetting rows.

    `SystemService.get_system_settings` seeds missing rows from env and flushes,
    which is why the dashboard calls `pending_sync_total` directly instead. This
    pins that choice: a GET that inserts is a GET that takes a write lock.
    """
    from features.system.model import AppSetting

    await api_client.get(
        "/api/admin/dashboard", headers=await auth_headers(role=UserRole.ADMIN.value)
    )

    rows = (await test_db_session.scalars(select(AppSetting))).all()
    assert rows == []


async def test_dashboard_counts_are_scoped_to_the_caller(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Two students, two different totals — no shared/global counter."""
    mine = await _student_graph(factories, scanned_today=1)
    other = await factories.full_stack()
    other["user"].email = "dash.third@isu.edu.ph"
    await factories.attendance(
        other["student"], other["session"], timestamp=datetime.now(timezone.utc)
    )

    body = (
        await api_client.get(
            "/api/student/dashboard", headers=await auth_headers(mine["user"])
        )
    ).json()

    # `_student_graph` adds a yesterday scan alongside the one today scan.
    assert body["scans_today"] == 1
    assert body["total_scans"] == 2


async def test_unused_imports_are_not_shadowed_by_the_dashboard(
    factories: Factories, test_db_session: AsyncSession
) -> None:
    """Guard the model imports the count helpers use.

    `_professor_student_count` and the roster counts import their models inside
    the function bodies to keep the module's import graph readable; if one of
    those local imports is dropped, the endpoint 500s at call time rather than
    at import time, which no collection-time check would catch.
    """
    assert Attendance.__tablename__ == "attendance_records"
    assert Enrollment.__tablename__ == "enrollments"
    assert Session.__tablename__ == "sessions"
    assert Program.__tablename__ == "programs"
    assert Student.__tablename__ == "students"
    assert User.__tablename__ == "users"
