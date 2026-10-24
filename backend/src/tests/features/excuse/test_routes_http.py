from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.attendance.model import Attendance
from features.excuse.model import ExcuseRequest
from features.excuse.service import ExcuseService
from features.system.model import AuditLog
from shared.enums import AuditAction, AuditEntity, UserRole, ValidationStatus
from tests.conftest import Factories

QUICK_REASON = "Family emergency kept the student home today."
EVIDENCE_REASON = "Clinic visit with a medical certificate attached."
STUDENT_REASON = "Confined at the university clinic all morning with fever."
REVISED_REASON = "Updated wording after the parent called the department."
RACE_REASON = "Applied by the parallel quick excuse."
ABSENT = ValidationStatus.ABSENT.value
EXCUSED = ValidationStatus.EXCUSED.value


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
        "course": course,
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


# --- the queues name the people and the classes -----------------------------
#
# The read model used to carry ids only, so the admin queue rendered
# "Student #4" and "Session #38" and the professor queue "Student #4". The
# slice now resolves the display identity itself (ADR-088) — the same rule
# `LivenessReviewItem` follows.


async def test_excuse_queues_name_the_student_and_the_class(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    admin_headers = await auth_headers(role=UserRole.ADMIN.value)
    professor_headers = await auth_headers(graph["professor_user"])

    student_headers = await auth_headers(graph["student_user"])
    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": graph["session"].id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=student_headers,
    )
    assert submitted.status_code == 201

    for path, headers in (
        ("/api/admin/excuses", admin_headers),
        ("/api/professor/excuse-requests", professor_headers),
    ):
        listed = await api_client.get(path, headers=headers)
        assert listed.status_code == 200
        (row,) = listed.json()["items"]

        # The student, by the number an administrator actually types.
        assert row["student_number"] == graph["student"].student_id
        assert row["student_name"]
        assert "Student #" not in row["student_name"]

        # The class.
        assert row["session_code"] == graph["session"].session_code
        assert row["course_code"] == graph["course"].course_code
        assert row["course_name"] == graph["course"].course_name

        # Still pending, so nobody has reviewed it yet.
        assert row["reviewed_by_name"] is None


async def test_a_reviewed_excuse_names_its_reviewer(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    graph = await _seed(factories)
    admin_headers = await auth_headers(role=UserRole.ADMIN.value)
    professor_headers = await auth_headers(graph["professor_user"])

    student_headers = await auth_headers(graph["student_user"])
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

    approved = await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "approved"},
        headers=professor_headers,
    )
    assert approved.status_code == 200
    # The response of the decision names its reviewer too.
    assert approved.json()["reviewed_by_name"]

    listed = await api_client.get("/api/admin/excuses", headers=admin_headers)
    (row,) = listed.json()["items"]
    assert row["reviewed_by_name"]
    assert row["reviewed_by_name"] != f"User #{row['reviewed_by']}"
    # The raw id stays in the response: the per-record paths key on it.
    assert row["reviewed_by"] == graph["professor_user"].id


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


async def _reload_attendance(
    test_db_session: AsyncSession, student_id: int, session_id: int
) -> Attendance:
    """Re-read the attendance row.

    Every read after a rolled-back request has to go back to the database: the
    rollback leaves the session's identity map holding objects the transaction
    never committed.
    """

    return (
        await test_db_session.scalars(
            select(Attendance).where(
                Attendance.student_id == student_id,
                Attendance.session_id == session_id,
            )
        )
    ).one()


async def test_approve_rolls_back_when_record_is_no_longer_excusable(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: AsyncSession,
) -> None:
    """A late rejection must undo the review's own writes, not just skip them.

    `review_excuse` is the one method in this slice that writes before it has
    finished validating: it flips the excuse to approved and flushes
    (`service.py:347-351`) and records the audit (`:353`) before
    `_require_excusable` can still refuse at `:371`. All of it lands in one
    transaction, so `_get_db`'s rollback is the only thing standing between a
    failed review and an approved excuse whose attendance row was never
    stamped. Nothing else in the suite exercises that path.
    """

    graph = await _seed(factories)
    student_id = graph["student"].id
    session_id = graph["session"].id
    professor_headers = await auth_headers(graph["professor_user"])

    submitted = await api_client.post(
        "/api/student/excuse-requests",
        json={"session_id": session_id, "reason": STUDENT_REASON,
              "attachment_urls": ["https://files.test/clinic.pdf"]},
        headers=await auth_headers(graph["student_user"]),
    )
    assert submitted.status_code == 201
    rid = submitted.json()["id"]

    # A parallel quick excuse won the race after the request was filed. The
    # commit is load-bearing: `api_client` shares `test_db_session`, so the
    # failed review below rolls that session back and would otherwise erase
    # this setup too, leaving the assertions below to pass vacuously.
    record = graph["record"]
    record.validation_status = EXCUSED
    record.excuse_reason = RACE_REASON
    record.excused_by = graph["professor_user"].id
    await test_db_session.commit()

    denied = await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "approved"},
        headers=professor_headers,
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "already_excused"

    excuse = (
        await test_db_session.scalars(
            select(ExcuseRequest).where(ExcuseRequest.id == rid)
        )
    ).one()
    assert excuse.status == "pending"
    assert excuse.reviewed_at is None
    assert excuse.reviewed_by is None

    record = await _reload_attendance(test_db_session, student_id, session_id)
    assert record.validation_status == EXCUSED
    assert record.excuse_reason == RACE_REASON
    assert record.excuse_request_id is None
    assert record.original_status is None

    # Scoped to APPROVE, not just to the excuse: filing the request already
    # wrote a CREATE row for this id, and that one is supposed to survive.
    audits = (
        await test_db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == AuditEntity.EXCUSE.value,
                AuditLog.entity_id == rid,
                AuditLog.action == AuditAction.APPROVE.value,
            )
        )
    ).all()
    assert not audits, "the APPROVE audit row outlived the rolled-back review"

    # The rollback has to leave the request usable, not merely unflipped: put
    # the record back in an excusable state and the same review now succeeds.
    record = await _reload_attendance(test_db_session, student_id, session_id)
    record.validation_status = ABSENT
    await test_db_session.commit()

    approved = await api_client.post(
        f"/api/professor/excuse-requests/{rid}/review",
        json={"status": "approved"},
        headers=professor_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    record = await _reload_attendance(test_db_session, student_id, session_id)
    assert record.validation_status == EXCUSED
    assert record.original_status == ABSENT
