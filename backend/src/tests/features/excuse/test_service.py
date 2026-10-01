"""The excuse record and the attendance row it stamps, kept consistent.

An approved excuse lives in two places: its own `excuse_requests` row, and the
copy of it on the `attendance_records` row the excuse was applied to. The two
routes that revise an existing excuse have to keep those in step, and both have
to resolve the same row.

Resolving "the" excuse from a (student, session) pair is not as unambiguous as
it looks, because both a professor-issued excuse and a student's own request can
exist for the same session, and neither route is keyed by excuse id. The
selector has to pick the professor's, or a professor revising a session would
silently rewrite or revoke the student's request instead.

Revising a reason must move the wording and nothing else. Re-applying the
excuse would overwrite the prior status with `excused` and lose the record of
what the student actually was, so the approval columns are asserted unchanged
alongside the field that is supposed to move.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.excuse.exceptions import ExcuseNotFoundException
from features.excuse.model import ExcuseRequest
from features.excuse.schema import QuickExcuseRequest, StudentExcuseRequest
from features.excuse.service import ExcuseService
from shared.enums import ExcuseInitiatedBy, ExcuseStatus, UserRole, ValidationStatus
from tests.conftest import Factories

ABSENT = ValidationStatus.ABSENT.value
EXCUSED = ValidationStatus.EXCUSED.value
PENDING = ExcuseStatus.PENDING.value
APPROVED = ExcuseStatus.APPROVED.value
REJECTED = ExcuseStatus.REJECTED.value

QUICK_REASON = "I was absent because of a family emergency."
REVISED_REASON = "I was absent because a flight was cancelled that morning."
STUDENT_REASON = "I was in the university clinic all morning with a fever."


def _service(session: AsyncSession) -> ExcuseService:
    return ExcuseService(session)


# -- seed ----------------------------------------------------------------


async def _seed(factories: Factories) -> dict[str, Any]:
    """One assigned professor, one enrolled student, one absent session row."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    admin = await factories.user(role=UserRole.ADMIN.value)

    professor_user = await factories.user(
        role=UserRole.PROFESSOR.value, email="professor.account@test"
    )
    professor = await factories.professor(
        user=professor_user, email="professor.roster@test"
    )
    await factories.assignment(offering, professor, assigned_by=admin)

    student_user = await factories.user(
        role=UserRole.STUDENT.value, email="student.account@test"
    )
    student = await factories.student(
        year_level,
        user=student_user,
        email="student.roster@test",
        last_name="Student0",
    )
    await factories.enrollment(student, offering)

    session = await factories.session(offering, professor)
    record = await factories.attendance(student, session, validation_status=ABSENT)

    return {
        "professor_user": professor_user,
        "session": session,
        "student": student,
        "student_user": student_user,
        "record": record,
    }


# -- actions -------------------------------------------------------------


async def _quick_excuse(session: AsyncSession, graph: dict[str, Any]) -> Any:
    return await _service(session).quick_excuse(
        user_id=graph["professor_user"].id,
        student_id=graph["student"].id,
        session_id=graph["session"].id,
        payload=QuickExcuseRequest(reason=QUICK_REASON),
    )


async def _student_request(session: AsyncSession, graph: dict[str, Any]) -> int:
    """File a student-initiated request; returns its id, not the response DTO."""
    submitted = await _service(session).submit_student_excuse(
        user_id=graph["student_user"].id,
        payload=StudentExcuseRequest(
            session_id=graph["session"].id,
            reason=STUDENT_REASON,
            attachment_urls=["/attachments/2026-03/abc123.pdf"],
        ),
    )

    return submitted.id


async def _excuse_for(test_db_session: AsyncSession, graph: dict[str, Any]) -> Any:
    """The single excuse row on the session, or None."""
    row: ExcuseRequest | None = (
        await test_db_session.scalars(
            select(ExcuseRequest).where(
                ExcuseRequest.student_id == graph["student"].id,
                ExcuseRequest.session_id == graph["session"].id,
            )
        )
    ).one_or_none()

    return row


async def _excuse_row(test_db_session: AsyncSession, excuse_id: int) -> ExcuseRequest:
    row: ExcuseRequest = await test_db_session.get(ExcuseRequest, excuse_id)
    await test_db_session.refresh(row)

    return row


def _stamp(record: Any) -> dict[str, Any]:
    """The excuse columns on the attendance row, for before/after comparison."""
    return {
        "validation_status": record.validation_status,
        "original_status": record.original_status,
        "excuse_reason": record.excuse_reason,
        "excused_by": record.excused_by,
        "excused_at": record.excused_at,
        "excuse_type": record.excuse_type,
        "excuse_request_id": record.excuse_request_id,
    }


# -- revising the reason -------------------------------------------------


@pytest.mark.asyncio
async def test_edit_reasons_mirrors_onto_the_attendance_row(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A revised reason has to reach both tables, or the audit copy goes stale."""
    graph = await _seed(factories)
    issued = await _quick_excuse(test_db_session, graph)
    record = graph["record"]

    assert record.excuse_reason == QUICK_REASON
    assert record.excuse_request_id == issued.excuse_request_id

    before = _stamp(record)
    edited = await _service(test_db_session).edit_excuse(
        user_id=graph["professor_user"].id,
        student_id=graph["student"].id,
        session_id=graph["session"].id,
        reason=REVISED_REASON,
    )

    assert edited.reason == REVISED_REASON
    await test_db_session.refresh(record)
    after = _stamp(record)
    assert after["excuse_reason"] == REVISED_REASON

    # The wording moved. The approval did not: re-stamping the excuse would have
    # overwritten `original_status` with `excused` and lost what the student was.
    assert after["validation_status"] == EXCUSED
    assert after["original_status"] == before["original_status"] == ABSENT
    assert after["excused_by"] == before["excused_by"]
    assert after["excused_at"] == before["excused_at"]
    assert after["excuse_type"] == before["excuse_type"]
    assert after["excuse_request_id"] == before["excuse_request_id"]


@pytest.mark.asyncio
async def test_edit_notes_only_does_not_touch_attendance(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Review notes live on the request only; they are not part of the stamp."""
    graph = await _seed(factories)
    await _quick_excuse(test_db_session, graph)
    record = graph["record"]
    before = _stamp(record)

    edited = await _service(test_db_session).edit_excuse(
        user_id=graph["professor_user"].id,
        student_id=graph["student"].id,
        session_id=graph["session"].id,
        review_notes="Confirmed with the registrar by phone.",
    )

    assert edited.review_notes == "Confirmed with the registrar by phone."
    await test_db_session.refresh(record)
    assert _stamp(record) == before


# -- picking the right excuse -------------------------------------------


@pytest.mark.asyncio
async def test_revoke_prefers_the_professor_excuse_over_a_pending_request(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Both rows can exist for one session; the professor's is the one to act on."""
    graph = await _seed(factories)
    student_request_id = await _student_request(test_db_session, graph)
    issued = await _quick_excuse(test_db_session, graph)
    record = graph["record"]

    assert record.excuse_request_id == issued.excuse_request_id
    assert (await _excuse_row(test_db_session, student_request_id)).status == PENDING

    result = await _service(test_db_session).revoke_excuse(
        user_id=graph["professor_user"].id,
        student_id=graph["student"].id,
        session_id=graph["session"].id,
    )

    assert result.reverted_to == ABSENT
    await test_db_session.refresh(record)
    after = _stamp(record)
    assert after["validation_status"] == ABSENT
    assert after["original_status"] is None
    assert after["excuse_reason"] is None
    assert after["excuse_request_id"] is None

    # The professor's excuse is what got revoked...
    assert (await _excuse_row(test_db_session, issued.excuse_request_id)).status == (
        REJECTED
    )

    # ...and the student's request is still awaiting review.
    student_request = await _excuse_row(test_db_session, student_request_id)
    assert student_request.status == PENDING
    assert student_request.reason == STUDENT_REASON


@pytest.mark.asyncio
async def test_revoke_will_not_reject_a_student_request(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """With no professor excuse, a revoke is a miss, not a rejection of the student's."""
    graph = await _seed(factories)
    student_request_id = await _student_request(test_db_session, graph)
    record = graph["record"]

    with pytest.raises(ExcuseNotFoundException):
        await _service(test_db_session).revoke_excuse(
            user_id=graph["professor_user"].id,
            student_id=graph["student"].id,
            session_id=graph["session"].id,
        )

    student_request = await _excuse_row(test_db_session, student_request_id)
    assert student_request.status == PENDING
    assert student_request.reason == STUDENT_REASON

    await test_db_session.refresh(record)
    assert record.validation_status == ABSENT
    assert record.excuse_request_id is None


@pytest.mark.asyncio
async def test_edit_will_not_rewrite_a_student_request(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A professor revising a session must not edit the student's own request."""
    graph = await _seed(factories)
    student_request_id = await _student_request(test_db_session, graph)

    with pytest.raises(ExcuseNotFoundException) as caught:
        await _service(test_db_session).edit_excuse(
            user_id=graph["professor_user"].id,
            student_id=graph["student"].id,
            session_id=graph["session"].id,
            reason=REVISED_REASON,
        )

    assert caught.value.code == "excuse_not_found"

    student_request = await _excuse_row(test_db_session, student_request_id)
    assert student_request.reason == STUDENT_REASON
    assert student_request.status == PENDING


@pytest.mark.asyncio
async def test_edit_needs_a_professor_excuse_to_exist(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """An unexcused session has nothing to revise."""
    graph = await _seed(factories)

    with pytest.raises(ExcuseNotFoundException):
        await _service(test_db_session).edit_excuse(
            user_id=graph["professor_user"].id,
            student_id=graph["student"].id,
            session_id=graph["session"].id,
            reason=REVISED_REASON,
        )


@pytest.mark.asyncio
async def test_a_miss_names_the_student_and_session(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """These routes are keyed by student and session, so the 404 has to say which."""
    graph = await _seed(factories)

    with pytest.raises(ExcuseNotFoundException) as caught:
        await _service(test_db_session).revoke_excuse(
            user_id=graph["professor_user"].id,
            student_id=graph["student"].id,
            session_id=graph["session"].id,
        )

    assert caught.value.status_code == 404
    assert caught.value.code == "excuse_not_found"
    assert "request 0" not in caught.value.message
    assert str(graph["student"].id) in caught.value.message
    assert str(graph["session"].id) in caught.value.message
    assert await _excuse_for(test_db_session, graph) is None


@pytest.mark.asyncio
async def test_a_known_excuse_id_still_reports_that_id(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The by-id lookup keeps its message; only the by-record lookup changed."""
    with pytest.raises(ExcuseNotFoundException) as caught:
        await _service(test_db_session)._get_excuse_or_404(4321)  # noqa: SLF001

    assert caught.value.message == "Excuse request 4321 not found"


@pytest.mark.asyncio
async def test_initiated_by_is_preserved_on_the_professor_excuse(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The selector keys off `initiated_by`, so the column has to be written."""
    graph = await _seed(factories)
    await _quick_excuse(test_db_session, graph)

    professor_excuse = await _excuse_for(test_db_session, graph)

    assert professor_excuse.initiated_by == ExcuseInitiatedBy.PROFESSOR.value
    assert professor_excuse.status == APPROVED
