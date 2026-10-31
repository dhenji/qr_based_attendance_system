"""HTTP-level cover for POST /professor/reports/export.

Pins the export to the same union scope the ledger and aggregates read
(sessions opened plus current assignments), the include-driven column mask,
and the CSV-only response path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


async def _teaching_setup(
    factories: Factories, *, with_assignment: bool = True
) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    admin = await factories.user(role=UserRole.ADMIN.value)

    if with_assignment:
        await factories.assignment(offering, professor, admin)

    session = await factories.session(
        offering, professor, created_at=NOW, expires_at=NOW
    )
    student_user = await factories.user()
    student = await factories.student(year_level, student_user)
    await factories.enrollment(student, offering)
    await factories.attendance(
        student,
        session,
        timestamp=NOW,
        gps_lat=14.5,
        gps_lng=121.0,
        face_match_score=0.92,
    )
    return {
        "course": course,
        "offering": offering,
        "professor": professor,
        "professor_user": professor_user,
        "session": session,
        "student": student,
    }


async def test_export_returns_csv_with_all_columns(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export", json={"format": "csv"}, headers=headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert len(lines) == 2
    header = lines[0].split(",")
    assert header == [
        "session_id",
        "session_type",
        "student_id",
        "name",
        "timestamp",
        "gps_lat",
        "gps_lng",
        "face_match_score",
        "status",
    ]
    row = lines[1].split(",")
    assert row[0] == str(setup["session"].id)
    assert row[1] == "lecture"
    assert row[2] == setup["student"].student_id
    assert setup["student"].first_name in row[3]
    assert row[-1] == ValidationStatus.PRESENT.value


async def test_export_include_masks_columns(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export",
        json={"format": "csv", "include": ["name", "timestamp"]},
        headers=headers,
    )

    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0].split(",") == ["session_id", "session_type", "name", "timestamp", "status"]
    assert len(lines) == 2


async def test_export_statuses_filter(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export",
        json={"format": "csv", "statuses": [ValidationStatus.LATE.value]},
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 1


async def test_export_pdf_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export", json={"format": "pdf"}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "format"


async def test_export_owned_session_visible_without_assignment(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories, with_assignment=False)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export", json={"format": "csv"}, headers=headers
    )

    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 2


async def test_export_excludes_unrelated_offering(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    other_professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    other_professor = await factories.professor(other_professor_user)
    other_course = await factories.course()
    program_year = await factories.program()
    other_year = await factories.year_level(program_year)
    other_offering = await factories.offering(
        other_course, program_year, other_year
    )
    other_student = await factories.student(other_year, await factories.user())
    await factories.enrollment(other_student, other_offering)
    other_session = await factories.session(
        other_offering, other_professor, created_at=NOW
    )
    await factories.attendance(other_student, other_session, timestamp=NOW)

    response = await api_client.post(
        "/api/professor/reports/export",
        json={"format": "csv"},
        headers=await auth_headers(setup["professor_user"]),
    )

    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert len(lines) == 2
    header = lines[0].split(",")
    session_idx = header.index("session_id")
    session_ids = {line.split(",")[session_idx] for line in lines[1:]}
    assert session_ids == {str(setup["session"].id)}


async def test_export_requires_professor_role(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    await _teaching_setup(factories)
    student_headers = await auth_headers(await factories.user())
    admin_headers = await auth_headers(
        await factories.user(role=UserRole.ADMIN.value)
    )
    await test_db_session.commit()

    for headers in (student_headers, admin_headers):
        response = await api_client.post(
            "/api/professor/reports/export",
            json={"format": "csv"},
            headers=headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_export_reversed_date_range_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    setup = await _teaching_setup(factories)
    headers = await auth_headers(setup["professor_user"])

    response = await api_client.post(
        "/api/professor/reports/export",
        json={
            "format": "csv",
            "date_from": NOW.isoformat(),
            "date_to": "2026-01-01T00:00:00+00:00",
        },
        headers=headers,
    )

    assert response.status_code == 422
