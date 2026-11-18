"""`GET /student/attendance/history/export` — the CSV twin of the history list.

The paginated endpoint stops at `MAX_PAGE_SIZE`, so the riskiest thing about
this route is that it could quietly inherit that limit: the student would be
shown a `total` of N and handed a file with fewer than N rows. The export
therefore takes no page/size at all, and `test_export_is_unpaginated` seeds
past `MAX_PAGE_SIZE` to prove it rather than trusting that.

Also worth pinning because it is easy to get wrong in a CSV:

- nulls must render as empty cells, not the strings `None`;
- `scanned_at` must be ISO-8601. `csv.writer` would happily emit
  `str(datetime)` — space-separated, which spreadsheets read as text — so the
  service formats it explicitly;
- the header must match `HistoryItem`'s field order, since that is the order
  the paginated endpoint returns.

Seeded through the factories the same way `test_history_and_review.py` does:
`get_history` takes a `users.id` and resolves through `Student.user_id`.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import UserRole
from shared.pagination import MAX_PAGE_SIZE

from features.attendance.model import Attendance
from tests.conftest import Factories

HEADER = (
    "id,session_id,course_code,course_name,status,original_status,"
    "excuse_reason,scanned_at,scanned_via"
)


async def _seed(
    factories: Factories, statuses: list[str]
) -> tuple[dict[str, Any], Any]:
    """One linked student, one session + one scan per entry in `statuses`.

    Each status gets its own session so a `status=` filter has something to
    discriminate on. `full_stack` contributes a session but no attendance row,
    so the row count here is exactly `len(statuses)`.
    """

    graph = await factories.full_stack()
    student = graph["student"]
    professor = graph["professor"]
    offering = graph["offering"]
    user = await factories.user(role=UserRole.STUDENT.value)
    student.user_id = user.id
    now = factories.now

    for offset, status in enumerate(statuses):
        db_session = await factories.session(
            offering,
            professor,
            scheduled_start_time=now + timedelta(days=offset),
            scheduled_end_time=now + timedelta(days=offset, minutes=60),
            expires_at=now + timedelta(days=offset, minutes=60),
        )
        await factories.attendance(
            student,
            db_session,
            validation_status=status,
            timestamp=now + timedelta(days=offset, minutes=5),
        )

    return graph, user


def _rows(response: Any) -> list[list[str]]:
    """Parse the body properly — an excuse reason may contain commas."""

    return list(csv.reader(io.StringIO(response.text)))


async def _export(client: Any, headers: dict[str, str], **params: Any) -> Any:
    return await client.get(
        "/api/student/attendance/history/export", headers=headers, params=params
    )


# -- shape -----------------------------------------------------------------


async def test_export_serves_csv_with_the_history_header(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    _graph, user = await _seed(factories, ["present", "late", "absent"])

    response = await _export(api_client, await auth_headers(user))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "attendance-history.csv" in response.headers["content-disposition"]

    rows = _rows(response)
    assert ",".join(rows[0]) == HEADER
    assert len(rows) == 4  # header + three scans
    # course identity is joined in, not blank
    assert all(row[2] and row[3] for row in rows[1:])


async def test_export_row_count_matches_the_paginated_total(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """The two endpoints must never disagree about how many rows exist."""

    _graph, user = await _seed(factories, ["present", "late", "absent", "excused"])
    headers = await auth_headers(user)

    listed = await api_client.get(
        "/api/student/attendance/history?size=1", headers=headers
    )
    exported = await _export(api_client, headers)

    assert listed.json()["total"] == 4
    assert len(listed.json()["items"]) == 1  # paginated
    assert len(_rows(exported)) - 1 == 4  # exported: all of them


async def test_export_is_unpaginated(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Seed past `MAX_PAGE_SIZE` — the limit the export must not inherit."""

    over = MAX_PAGE_SIZE + 1
    graph = await factories.full_stack()
    student = graph["student"]
    professor = graph["professor"]
    offering = graph["offering"]
    user = await factories.user(role=UserRole.STUDENT.value)
    student.user_id = user.id
    now = factories.now

    for index in range(over):
        start = now + timedelta(minutes=index * 30)
        db_session = await factories.session(
            offering,
            professor,
            scheduled_start_time=start,
            scheduled_end_time=start + timedelta(minutes=30),
            expires_at=start + timedelta(minutes=30),
        )
        await factories.attendance(
            student, db_session, validation_status="present", timestamp=now
        )

    response = await _export(api_client, await auth_headers(user))

    assert response.status_code == 200
    assert len(_rows(response)) - 1 == over


# -- filters and ordering ---------------------------------------------------


async def test_export_honours_the_status_filter(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    _graph, user = await _seed(factories, ["present", "late", "absent"])
    headers = await auth_headers(user)

    listed = await api_client.get(
        "/api/student/attendance/history?status=late", headers=headers
    )
    exported = await _export(api_client, headers, status="late")

    assert len(listed.json()["items"]) == 1
    rows = _rows(exported)
    assert len(rows) == 2  # header + the one late scan
    assert rows[1][4] == "late"


async def test_export_honours_the_sort_order(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    _graph, user = await _seed(factories, ["present", "late", "absent"])
    headers = await auth_headers(user)

    descending = _rows(
        await _export(api_client, headers, sort_by="date", sort_dir="desc")
    )
    ascending = _rows(
        await _export(api_client, headers, sort_by="date", sort_dir="asc")
    )

    assert [row[0] for row in descending[1:]] == [
        row[0] for row in reversed(ascending[1:])
    ]


# -- cell rendering ---------------------------------------------------------


async def test_export_renders_nulls_as_empty_cells(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """A bare scan has no excuse and no original status.

    `csv.writer` already renders a Python `None` as an empty cell, so the
    service's `or ""` guards are belt-and-braces rather than load-bearing —
    what this pins is that the cell ends up empty and never the literal text
    "None", without depending on the writer's coercion. `scanned_via` is
    nulled explicitly because the factory seeds it with `qr_camera`, so
    leaving it alone would prove nothing about the nullable path.
    """

    _graph, user = await _seed(factories, ["present"])
    listed = await api_client.get(
        "/api/student/attendance/history", headers=await auth_headers(user)
    )
    session_id = listed.json()["items"][0]["session_id"]

    row = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.session_id == session_id)
        )
    ).one()
    row.scanned_via = None
    await test_db_session.commit()

    exported = _rows(await _export(api_client, await auth_headers(user)))[1]

    assert exported[4] == "present"
    assert exported[5] == ""  # original_status
    assert exported[6] == ""  # excuse_reason
    assert exported[8] == ""  # scanned_via
    assert "None" not in " ".join(exported)


async def test_export_writes_scanned_at_as_iso8601(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """`str(datetime)` would emit a space separator and lose the type."""

    _graph, user = await _seed(factories, ["present"])
    rows = _rows(await _export(api_client, await auth_headers(user)))

    scanned_at = rows[1][7]
    assert "T" in scanned_at, scanned_at
    assert " " not in scanned_at, scanned_at


async def test_export_carries_excuse_detail_when_present(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """The excused columns are the reason a student exports this at all."""

    _graph, user = await _seed(factories, ["excused"])
    headers = await auth_headers(user)
    listed = await api_client.get("/api/student/attendance/history", headers=headers)
    session_id = listed.json()["items"][0]["session_id"]

    row = (
        await test_db_session.scalars(
            select(Attendance).where(Attendance.session_id == session_id)
        )
    ).one()
    row.original_status = "absent"
    row.excuse_reason = "Clinic visit, certificate attached"
    row.scanned_via = "qr_camera"
    await test_db_session.commit()

    exported = _rows(await _export(api_client, headers))[1]

    assert exported[4] == "excused"
    assert exported[5] == "absent"
    assert exported[6] == "Clinic visit, certificate attached"
    assert exported[8] == "qr_camera"


# -- gating -----------------------------------------------------------------


async def test_export_is_student_only(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    _graph, _user = await _seed(factories, ["present"])
    headers = await auth_headers(role=UserRole.PROFESSOR.value)
    await test_db_session.commit()

    response = await _export(api_client, headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_export_requires_authentication(
    api_client: Any, factories: Factories
) -> None:
    _graph, _user = await _seed(factories, ["present"])

    response = await api_client.get("/api/student/attendance/history/export")

    assert response.status_code in (401, 403)


async def test_export_only_covers_the_calling_student(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """Identity comes from the token, never from a parameter."""

    _graph, _user = await _seed(factories, ["present"])

    # A second student with a scan of their own, in the same offering.
    graph = await factories.full_stack()
    other_user = await factories.user(role=UserRole.STUDENT.value)
    graph["student"].user_id = other_user.id
    await factories.attendance(
        graph["student"], graph["session"], validation_status="present"
    )

    mine = _rows(await _export(api_client, await auth_headers(_user)))
    theirs = _rows(await _export(api_client, await auth_headers(other_user)))

    assert len(mine) == 2  # only my own scan
    assert len(theirs) == 2  # only theirs
    assert mine[1][0] != theirs[1][0]
