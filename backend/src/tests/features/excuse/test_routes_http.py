from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.attendance.model import Attendance
from features.excuse.service import ExcuseService
from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

QUICK_REASON = "Family emergency kept the student home today."
EVIDENCE_REASON = "Clinic visit with a medical certificate attached."
STUDENT_REASON = "Confined at the university clinic all morning with fever."
REVISED_REASON = "Updated wording after the parent called the department."
ABSENT = ValidationStatus.ABSENT.value


async def _seed(factories: Factories) -> dict[str, Any]:
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    admin = await factories.user(role=UserRole.ADMIN.value)

    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(user=professor_user)
    await factories.assignment(offering, professor, assigned_by=admin)

    student_user = await factories.user(role=UserRole.STUDENT.value)
    student = await factories.student(year_level, user=student_user)
    await factories.enrollment(student, offering)

    session = await factories.session(offering, professor)
    record = await factories.attendance(
        student, session, validation_status=ABSENT
    )
    return {
        "offering": offering,
        "professor": professor,
        "professor_user": professor_user,
        "student": student,
        "student_user": student_user,
        "session": session,
        "record": record,
    }


def _excuse_url(session_id: int, student_id: int) -> str:
    return f"/api/professor/sessions/{session_id}/attendance/{student_id}/excuse"


async def test_professor_quick_excuse_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])

    response = await api_client.post(
        _excuse_url(graph["session"].id, graph["student"].id),
        json={"reason": QUICK_REASON},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["new_status"] == "excused"
    assert body["excuse_request_id"] > 0


async def test_professor_excuse_with_evidence_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])

    response = await api_client.post(
        _excuse_url(graph["session"].id, graph["student"].id),
        json={
            "reason": EVIDENCE_REASON,
            "attachment_urls": ["https://files.test/cert.pdf"],
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["new_status"] == "excused"

    excuses = await ExcuseService(test_db_session).list_for_professor(
        user_id=graph["professor_user"].id, status=None, page=1, size=20
    )
    assert excuses.total == 1
    assert excuses.items[0].attachment_urls == ["https://files.test/cert.pdf"]


async def test_professor_excuse_empty_attachments_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])

    response = await api_client.post(
        _excuse_url(graph["session"].id, graph["student"].id),
        json={"reason": EVIDENCE_REASON, "attachment_urls": []},
        headers=headers,
    )

    assert response.status_code == 422


async def test_professor_excuse_malformed_json_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])

    response = await api_client.post(
        _excuse_url(graph["session"].id, graph["student"].id),
        content=b"{not-json",
        headers={**headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_professor_edit_and_revoke_over_http(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])
    url = _excuse_url(graph["session"].id, graph["student"].id)

    created = await api_client.post(
        url, json={"reason": QUICK_REASON}, headers=headers
    )
    assert created.status_code == 201

    edited = await api_client.patch(
        url, json={"reason": REVISED_REASON}, headers=headers
    )
    assert edited.status_code == 200
    assert edited.json()["reason"] == REVISED_REASON

    record = (
        await test_db_session.scalars(
            select(Attendance).where(
                Attendance.student_id == graph["student"].id,
                Attendance.session_id == graph["session"].id,
            )
        )
    ).one()
    assert record.excuse_reason == REVISED_REASON
    assert record.original_status == ABSENT

    revoked = await api_client.delete(url, headers=headers)
    assert revoked.status_code == 200

    await test_db_session.refresh(record)
    assert record.validation_status == ABSENT


async def test_professor_bulk_excuse_all_absent_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["professor_user"])

    response = await api_client.post(
        f"/api/professor/sessions/{graph['session'].id}/excuse-all-absent",
        json={"reason": QUICK_REASON},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["excused_count"] >= 1


async def test_professor_list_and_review_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    student_headers = await auth_headers(graph["student_user"])
    professor_headers = await auth_headers(graph["professor_user"])

    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=student_headers,
    )
    assert submitted.status_code == 201

    queued = await api_client.get(
        "/api/professor/excuse-requests", headers=professor_headers
    )
    assert queued.status_code == 200
    assert queued.json()["total"] == 1
    rid = queued.json()["items"][0]["id"]

    approved = await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "approved"},
        headers=professor_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    filtered = await api_client.get(
        "/api/professor/excuse-requests",
        params={"status": "approved"},
        headers=professor_headers,
    )
    assert filtered.json()["total"] == 1


async def test_professor_review_reject_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    student_headers = await auth_headers(graph["student_user"])
    professor_headers = await auth_headers(graph["professor_user"])

    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=student_headers,
    )
    assert submitted.status_code == 201

    queued = await api_client.get(
        "/api/professor/excuse-requests", headers=professor_headers
    )
    rid = queued.json()["items"][0]["id"]

    rejected = await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "rejected", "review_notes": "Insufficient evidence"},
        headers=professor_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


async def test_student_submit_list_and_detail_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    headers = await auth_headers(graph["student_user"])

    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=headers,
    )
    assert submitted.status_code == 201
    assert submitted.json()["status"] == "pending"

    listed = await api_client.get("/api/student/excuse-requests", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    rid = listed.json()["items"][0]["id"]

    fetched = await api_client.get(
        f"/api/student/excuse-requests/{rid}", headers=headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == rid


async def test_admin_list_excuses_over_http(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    admin_headers = await auth_headers(role=UserRole.ADMIN.value)

    student_headers = await auth_headers(graph["student_user"])
    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=student_headers,
    )
    assert submitted.status_code == 201

    listed = await api_client.get("/api/admin/excuses", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_excuse_routes_enforce_roles(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    student_headers = await auth_headers(graph["student_user"])

    denied = await api_client.post(
        _excuse_url(graph["session"].id, graph["student"].id),
        json={"reason": QUICK_REASON},
        headers=student_headers,
    )
    assert denied.status_code == 403

    anonymous = await api_client.get("/api/student/excuse-requests")
    assert anonymous.status_code in (401, 403)

    anonymous_admin = await api_client.get("/api/admin/excuses")
    assert anonymous_admin.status_code in (401, 403)


async def test_approve_preserves_original_status(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    graph = await _seed(factories)
    student_headers = await auth_headers(graph["student_user"])
    professor_headers = await auth_headers(graph["professor_user"])

    await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=student_headers,
    )
    queued = await api_client.get(
        "/api/professor/excuse-requests", headers=professor_headers
    )
    rid = queued.json()["items"][0]["id"]
    await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "approved"},
        headers=professor_headers,
    )

    record = (
        await test_db_session.scalars(
            select(Attendance).where(
                Attendance.student_id == graph["student"].id,
                Attendance.session_id == graph["session"].id,
            )
        )
    ).one()
    assert record.validation_status == "excused"
    assert record.original_status == ABSENT
