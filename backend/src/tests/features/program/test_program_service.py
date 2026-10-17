from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from features.program.exceptions import (
    ProgramCodeExistsException,
    ProgramHasOfferingsException,
    ProgramHasStudentsException,
    ProgramNotArchivedException,
    ProgramNotFoundException,
    YearLevelHasCoursesException,
    YearLevelNotFoundException,
    YearLevelNumberExistsException,
)
from features.program.schema import (
    ProgramCreate,
    ProgramUpdate,
    YearLevelCreate,
    YearLevelUpdate,
)
from features.program.service import ProgramService
from tests.conftest import Factories


def _program_payload(code: str = "BSCS", **overrides: Any) -> ProgramCreate:
    values: dict[str, Any] = {
        "code": code,
        "name": "BS Computer Science",
        "description": None,
        "total_years": 4,
    }
    values.update(overrides)
    return ProgramCreate(**values)


def _year_payload(year_number: int = 1, **overrides: Any) -> YearLevelCreate:
    values: dict[str, Any] = {
        "year_number": year_number,
        "label": f"Year {year_number}",
        "term_structure": {
            "terms": [
                {"code": "1ST", "label": "1st Sem"},
                {"code": "2ND", "label": "2nd Sem"},
            ]
        },
    }
    values.update(overrides)
    return YearLevelCreate(**values)


async def test_create_program(test_db_session: AsyncSession) -> None:
    service = ProgramService(test_db_session)
    created = await service.create(payload=_program_payload(code="BSCS"))

    assert created.id is not None
    assert created.code == "BSCS"
    assert created.is_active is True
    assert created.year_level_count == 0
    assert created.terms_count == 0
    assert created.course_count == 0


async def test_create_normalizes_code(test_db_session: AsyncSession) -> None:
    service = ProgramService(test_db_session)
    created = await service.create(payload=_program_payload(code="  bscs  "))

    assert created.code == "BSCS"


async def test_create_duplicate_code_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    await factories.program(code="BSCS")
    service = ProgramService(test_db_session)

    with pytest.raises(ProgramCodeExistsException):
        await service.create(payload=_program_payload(code="BSCS"))


async def test_get_program_with_nested_years(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    await factories.year_level(program, year_number=1)
    await factories.year_level(program, year_number=2)

    detail = await ProgramService(test_db_session).get(program_id=program.id)

    assert detail.code == "BSCS"
    assert detail.year_level_count == 2
    assert detail.terms_count == 4
    assert len(detail.year_levels) == 2
    assert [yl.year_number for yl in detail.year_levels] == [1, 2]


async def test_get_missing_program_404(test_db_session: AsyncSession) -> None:
    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).get(program_id=9999)


async def test_list_search_and_status_filter(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    await factories.program(code="BSCS", name="BS Computer Science")
    await factories.program(code="BSIT", name="BS Information Technology")
    archived = await factories.program(code="BSECE", name="BS ECE")
    archived.is_active = False
    await test_db_session.flush()

    service = ProgramService(test_db_session)

    searched = await service.list(search="computer", is_active=None, page=1, size=20)
    assert searched.total == 1
    assert searched.items[0].code == "BSCS"

    active = await service.list(search=None, is_active=True, page=1, size=20)
    assert active.total == 2

    inactive = await service.list(search=None, is_active=False, page=1, size=20)
    assert inactive.total == 1
    assert inactive.items[0].code == "BSECE"


async def test_list_pagination(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    for i in range(3):
        await factories.program(code=f"P{i:02d}")

    page2 = await ProgramService(test_db_session).list(
        search=None, is_active=None, page=2, size=2
    )

    assert page2.total == 3
    assert page2.page == 2
    assert len(page2.items) == 1


async def test_list_carries_aggregates(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    await factories.year_level(program, year_number=1)

    result = await ProgramService(test_db_session).list(
        search=None, is_active=None, page=1, size=20
    )

    assert result.total == 1
    assert result.items[0].year_level_count == 1
    assert result.items[0].terms_count == 2


async def test_update_program(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS", name="Old Name")

    updated = await ProgramService(test_db_session).update(
        program_id=program.id,
        payload=ProgramUpdate(name="New Name"),
    )

    assert updated.name == "New Name"
    assert updated.code == "BSCS"
    assert updated.updated_at is not None


async def test_update_missing_program_404(test_db_session: AsyncSession) -> None:
    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).update(
            program_id=9999, payload=ProgramUpdate(name="Nope")
        )


async def test_archive_via_update_flips_flag_only(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)

    await ProgramService(test_db_session).update(
        program_id=program.id, payload=ProgramUpdate(is_active=False)
    )
    await test_db_session.flush()
    assert program.is_active is False

    listed = await ProgramService(test_db_session).list_years(
        program_id=program.id, page=1, size=20
    )
    assert listed.total == 1
    assert listed.items[0].id == year.id


async def test_hard_delete_active_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")

    with pytest.raises(ProgramNotArchivedException):
        await ProgramService(test_db_session).hard_delete(program_id=program.id)


async def test_hard_delete_missing_program_404(
    test_db_session: AsyncSession,
) -> None:
    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).hard_delete(program_id=9999)


async def test_hard_delete_blocked_by_offerings(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)
    course = await factories.course()
    await factories.offering(course, program, year)
    await ProgramService(test_db_session).update(
        program_id=program.id, payload=ProgramUpdate(is_active=False)
    )

    with pytest.raises(ProgramHasOfferingsException):
        await ProgramService(test_db_session).hard_delete(program_id=program.id)


async def test_hard_delete_blocked_by_students(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)
    await factories.student(year)
    await ProgramService(test_db_session).update(
        program_id=program.id, payload=ProgramUpdate(is_active=False)
    )

    with pytest.raises(ProgramHasStudentsException):
        await ProgramService(test_db_session).hard_delete(program_id=program.id)


async def test_hard_delete_clean_cascades_empty_years(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    from features.system.model import AuditLog
    from shared.enums import AuditAction, AuditEntity
    from sqlalchemy import select

    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)
    await ProgramService(test_db_session).update(
        program_id=program.id, payload=ProgramUpdate(is_active=False)
    )

    await ProgramService(test_db_session).hard_delete(program_id=program.id)
    await test_db_session.flush()

    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).get(program_id=program.id)

    # The program row is gone, so the nested year read 404s on the program
    # scope first; the cascade itself is proven by the row being unqueryable.
    from features.program.model import YearLevel

    assert await test_db_session.get(YearLevel, year.id) is None

    audit_rows = (
        await test_db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == AuditEntity.PROGRAM.value,
                AuditLog.entity_id == program.id,
                AuditLog.action == AuditAction.DELETE.value,
            )
            .order_by(AuditLog.id)
        )
    ).all()
    assert len(audit_rows) == 1


async def test_course_count_distinct_and_active_only(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)
    course = await factories.course(course_code="CS101")
    other_course = await factories.course(course_code="CS102")

    await factories.offering(course, program, year, semester="1ST", is_active=True)
    await factories.offering(course, program, year, semester="2ND", is_active=True)
    await factories.offering(
        other_course, program, year, semester="1ST", is_active=False
    )

    detail = await ProgramService(test_db_session).get(program_id=program.id)

    assert detail.course_count == 1


async def test_terms_count_sums_terms_list(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    await factories.year_level(
        program,
        year_number=1,
        term_structure={"terms": [{"code": "A", "label": "A"}]},
    )
    await factories.year_level(
        program,
        year_number=2,
        term_structure={
            "terms": [
                {"code": "B", "label": "B"},
                {"code": "C", "label": "C"},
                {"code": "D", "label": "D"},
            ]
        },
    )
    await factories.year_level(program, year_number=3, term_structure={"terms": []})

    detail = await ProgramService(test_db_session).get(program_id=program.id)

    assert detail.year_level_count == 3
    assert detail.terms_count == 4


async def test_create_year_defaults_sort_order(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")

    created = await ProgramService(test_db_session).create_year(
        program_id=program.id, payload=_year_payload(year_number=2)
    )

    assert created.sort_order == 2
    assert len(created.term_structure.terms) == 2


async def test_create_year_duplicate_number_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    await factories.year_level(program, year_number=1)

    with pytest.raises(YearLevelNumberExistsException):
        await ProgramService(test_db_session).create_year(
            program_id=program.id, payload=_year_payload(year_number=1)
        )


async def test_create_year_missing_program_404(
    test_db_session: AsyncSession,
) -> None:
    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).create_year(
            program_id=9999, payload=_year_payload(year_number=1)
        )


async def test_get_year_scoped_to_program(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    first = await factories.program(code="AAA")
    second = await factories.program(code="BBB")
    year = await factories.year_level(first, year_number=1)

    with pytest.raises(YearLevelNotFoundException):
        await ProgramService(test_db_session).get_year(
            program_id=second.id, year_id=year.id
        )


async def test_update_year(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)

    updated = await ProgramService(test_db_session).update_year(
        program_id=program.id,
        year_id=year.id,
        payload=YearLevelUpdate(label="First Year"),
    )

    assert updated.label == "First Year"


async def test_delete_year_guarded_by_offerings(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)
    course = await factories.course()
    await factories.offering(course, program, year)

    with pytest.raises(YearLevelHasCoursesException):
        await ProgramService(test_db_session).delete_year(
            program_id=program.id, year_id=year.id
        )


async def test_delete_year_clean(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    year = await factories.year_level(program, year_number=1)

    await ProgramService(test_db_session).delete_year(
        program_id=program.id, year_id=year.id
    )

    with pytest.raises(YearLevelNotFoundException):
        await ProgramService(test_db_session).get_year(
            program_id=program.id, year_id=year.id
        )


async def test_list_years_paginated_and_ordered(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program(code="BSCS")
    await factories.year_level(program, year_number=3)
    await factories.year_level(program, year_number=1)
    await factories.year_level(program, year_number=2)

    result = await ProgramService(test_db_session).list_years(
        program_id=program.id, page=1, size=20
    )

    assert result.total == 3
    assert [row.year_number for row in result.items] == [1, 2, 3]


async def test_list_years_missing_program_404(
    test_db_session: AsyncSession,
) -> None:
    with pytest.raises(ProgramNotFoundException):
        await ProgramService(test_db_session).list_years(
            program_id=9999, page=1, size=20
        )


async def test_program_routes_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await auth_headers(role="admin")

    create_response = await api_client.post(
        "/api/admin/programs",
        json={
            "code": "BSCS",
            "name": "BS Computer Science",
            "description": None,
            "total_years": 4,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    program_id = create_response.json()["id"]

    duplicate = await api_client.post(
        "/api/admin/programs",
        json={
            "code": "BSCS",
            "name": "Duplicate",
            "description": None,
            "total_years": 4,
        },
        headers=headers,
    )
    assert duplicate.status_code == 409

    listed = await api_client.get("/api/admin/programs", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = await api_client.get(
        f"/api/admin/programs/{program_id}", headers=headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["code"] == "BSCS"

    missing = await api_client.get("/api/admin/programs/9999", headers=headers)
    assert missing.status_code == 404

    forbidden = await api_client.get("/api/admin/programs")
    assert forbidden.status_code in (401, 403)


async def test_program_hard_delete_routes_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await auth_headers(role="admin")

    create_response = await api_client.post(
        "/api/admin/programs",
        json={
            "code": "DEL1",
            "name": "Delete Me",
            "description": None,
            "total_years": 4,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    program_id = create_response.json()["id"]

    # Active programs cannot be hard-deleted.
    active_delete = await api_client.delete(
        f"/api/admin/programs/{program_id}", headers=headers
    )
    assert active_delete.status_code == 409
    assert active_delete.json()["detail"]["code"] == "not_archived"

    # Archive via PATCH, then the hard delete succeeds.
    archived = await api_client.patch(
        f"/api/admin/programs/{program_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert archived.status_code == 200

    deleted = await api_client.delete(
        f"/api/admin/programs/{program_id}", headers=headers
    )
    assert deleted.status_code == 204

    fetched = await api_client.get(
        f"/api/admin/programs/{program_id}", headers=headers
    )
    assert fetched.status_code == 404

    missing = await api_client.delete("/api/admin/programs/9999", headers=headers)
    assert missing.status_code == 404
