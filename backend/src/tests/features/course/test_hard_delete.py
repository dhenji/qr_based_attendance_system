"""DB-backed cover for course + offering hard deletes.

`DELETE /admin/courses/{id}` and `DELETE /admin/offerings/{id}` are permanent
deletes guarded server-side — only archived rows with no dependents go through.
Archive itself is `PATCH is_active=false`; the `archive()` helpers are gone.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import AuditAction, AuditEntity, UserRole

from features.course.exceptions import (
    CourseHasOfferingsException,
    CourseNotArchivedException,
    CourseNotFoundException,
    OfferingHasAssignmentsException,
    OfferingHasEnrollmentsException,
    OfferingHasSessionsException,
    OfferingNotArchivedException,
    OfferingNotFoundException,
)
from features.course.model import CourseOffering, OfferingComponent
from features.course.schema import CourseUpdate, OfferingUpdate
from features.course.service import CourseService
from features.system.model import AuditLog
from tests.conftest import Factories


async def _archive_course(session: AsyncSession, course_id: int) -> None:
    await CourseService(session).update(
        course_id=course_id, payload=CourseUpdate(is_active=False)
    )


async def _archive_offering(session: AsyncSession, offering_id: int) -> None:
    await CourseService(session).update_offering(
        offering_id=offering_id, payload=OfferingUpdate(is_active=False)
    )


# -- course ---------------------------------------------------------------


async def test_course_hard_delete_active_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    course = await factories.course()

    with pytest.raises(CourseNotArchivedException):
        await CourseService(test_db_session).hard_delete(course_id=course.id)


async def test_course_hard_delete_missing_404(test_db_session: AsyncSession) -> None:
    with pytest.raises(CourseNotFoundException):
        await CourseService(test_db_session).hard_delete(course_id=9999)


async def test_course_hard_delete_blocked_by_offerings(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    course = await factories.course()
    await factories.offering(course, program, year)
    await _archive_course(test_db_session, course.id)

    with pytest.raises(CourseHasOfferingsException):
        await CourseService(test_db_session).hard_delete(course_id=course.id)


async def test_course_hard_delete_clean_writes_audit(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    course = await factories.course()
    await _archive_course(test_db_session, course.id)

    await CourseService(test_db_session).hard_delete(course_id=course.id)
    await test_db_session.flush()

    with pytest.raises(CourseNotFoundException):
        await CourseService(test_db_session).get(course_id=course.id)

    rows = (
        await test_db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == AuditEntity.COURSE.value,
                AuditLog.entity_id == course.id,
                AuditLog.action == AuditAction.DELETE.value,
            )
        )
    ).all()
    assert len(rows) == 1


async def test_course_hard_delete_routes_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    headers = await auth_headers(role="admin")

    created = await api_client.post(
        "/api/admin/courses",
        json={
            "course_code": "DEL101",
            "course_name": "Delete Me",
            "units": 3,
            "session_duration_hours": 1.5,
        },
        headers=headers,
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    active = await api_client.delete(f"/api/admin/courses/{course_id}", headers=headers)
    assert active.status_code == 409
    assert active.json()["detail"]["code"] == "not_archived"

    archived = await api_client.patch(
        f"/api/admin/courses/{course_id}", json={"is_active": False}, headers=headers
    )
    assert archived.status_code == 200

    deleted = await api_client.delete(
        f"/api/admin/courses/{course_id}", headers=headers
    )
    assert deleted.status_code == 204

    fetched = await api_client.get(f"/api/admin/courses/{course_id}", headers=headers)
    assert fetched.status_code == 404

    missing = await api_client.delete("/api/admin/courses/9999", headers=headers)
    assert missing.status_code == 404


async def test_course_hard_delete_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    course = await factories.course()
    headers = await auth_headers(role="student")

    response = await api_client.delete(
        f"/api/admin/courses/{course.id}", headers=headers
    )

    assert response.status_code == 403


# -- offering -------------------------------------------------------------


async def _offering_seed(factories: Factories) -> dict[str, Any]:
    program = await factories.program()
    year = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year)
    return {"program": program, "year": year, "course": course, "offering": offering}


async def test_offering_hard_delete_active_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    seed = await _offering_seed(factories)

    with pytest.raises(OfferingNotArchivedException):
        await CourseService(test_db_session).hard_delete_offering(
            offering_id=seed["offering"].id
        )


async def test_offering_hard_delete_missing_404(test_db_session: AsyncSession) -> None:
    with pytest.raises(OfferingNotFoundException):
        await CourseService(test_db_session).hard_delete_offering(offering_id=9999)


async def test_offering_hard_delete_blocked_by_enrollments(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    seed = await _offering_seed(factories)
    student = await factories.student(seed["year"])
    await factories.enrollment(student, seed["offering"])
    await _archive_offering(test_db_session, seed["offering"].id)

    with pytest.raises(OfferingHasEnrollmentsException):
        await CourseService(test_db_session).hard_delete_offering(
            offering_id=seed["offering"].id
        )


async def test_offering_hard_delete_blocked_by_sessions(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    seed = await _offering_seed(factories)
    professor = await factories.professor()
    await factories.session(seed["offering"], professor)
    await _archive_offering(test_db_session, seed["offering"].id)

    with pytest.raises(OfferingHasSessionsException):
        await CourseService(test_db_session).hard_delete_offering(
            offering_id=seed["offering"].id
        )


async def test_offering_hard_delete_blocked_by_assignments(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    seed = await _offering_seed(factories)
    professor = await factories.professor()
    admin = await factories.user(role=UserRole.ADMIN.value)
    await factories.assignment(seed["offering"], professor, admin)
    await _archive_offering(test_db_session, seed["offering"].id)

    with pytest.raises(OfferingHasAssignmentsException):
        await CourseService(test_db_session).hard_delete_offering(
            offering_id=seed["offering"].id
        )


async def test_offering_hard_delete_clean_removes_components_and_audits(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    seed = await _offering_seed(factories)
    offering_id = seed["offering"].id
    # The factory row carries no components; attach one so the cascade path is
    # exercised even for rows that predate the component backfill.
    test_db_session.add(
        OfferingComponent(
            offering_id=offering_id,
            session_type="lecture",
            schedule_days="MWF",
            schedule_start_time=seed["offering"].schedule_start_time,
            schedule_end_time=seed["offering"].schedule_end_time,
        )
    )
    await test_db_session.flush()
    await _archive_offering(test_db_session, offering_id)

    await CourseService(test_db_session).hard_delete_offering(offering_id=offering_id)
    await test_db_session.flush()

    with pytest.raises(OfferingNotFoundException):
        await CourseService(test_db_session).get_offering(offering_id=offering_id)

    assert await test_db_session.get(CourseOffering, offering_id) is None
    remaining = (
        await test_db_session.scalars(
            select(OfferingComponent).where(
                OfferingComponent.offering_id == offering_id
            )
        )
    ).all()
    assert remaining == []

    rows = (
        await test_db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == AuditEntity.COURSE_OFFERING.value,
                AuditLog.entity_id == offering_id,
                AuditLog.action == AuditAction.DELETE.value,
            )
        )
    ).all()
    assert len(rows) == 1


async def test_offering_hard_delete_routes_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    headers = await auth_headers(role="admin")
    seed = await _offering_seed(factories)
    offering_id = seed["offering"].id
    # The first DELETE below 409s, and a failing request rolls back the seed
    # through the api_client override (which mirrors _get_db) — commit first
    # so the rows survive it.
    await test_db_session.commit()

    active = await api_client.delete(
        f"/api/admin/offerings/{offering_id}", headers=headers
    )
    assert active.status_code == 409
    assert active.json()["detail"]["code"] == "not_archived"

    archived = await api_client.patch(
        f"/api/admin/offerings/{offering_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert archived.status_code == 200

    deleted = await api_client.delete(
        f"/api/admin/offerings/{offering_id}", headers=headers
    )
    assert deleted.status_code == 204

    fetched = await api_client.get(
        f"/api/admin/offerings/{offering_id}", headers=headers
    )
    assert fetched.status_code == 404

    missing = await api_client.delete("/api/admin/offerings/9999", headers=headers)
    assert missing.status_code == 404


async def test_offering_hard_delete_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _offering_seed(factories)
    headers = await auth_headers(role="student")

    response = await api_client.delete(
        f"/api/admin/offerings/{seed['offering'].id}", headers=headers
    )

    assert response.status_code == 403
