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

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from features.excuse.exceptions import (
    ExcuseNotFoundException,
    ProfessorNotAssignedException,
)
from features.excuse.model import ExcuseRequest
from features.excuse.schema import (
    ExcuseReviewRequest,
    QuickExcuseRequest,
    StudentExcuseRequest,
)
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
        "admin": admin,
        "offering": offering,
        "professor": professor,
        "professor_user": professor_user,
        "session": session,
        "student": student,
        "student_user": student_user,
        "record": record,
    }


async def _second_professor(
    factories: Factories,
    graph: dict[str, Any],
    *,
    assigned: bool = True,
    effective_to: date | None = None,
) -> tuple[Any, Any]:
    """A second professor on the offering, and their account.

    Assigned by default so the co-teaching cases read as a professor acting on
    a session they share; `assigned=False` and a lapsed `effective_to` cover the
    two ways the assignment check has to say no.
    """
    user = await factories.user(
        role=UserRole.PROFESSOR.value, email="second.account@test"
    )
    professor = await factories.professor(
        user=user, email="second.roster@test", last_name="Second"
    )
    if assigned:
        await factories.assignment(
            graph["offering"],
            professor,
            assigned_by=graph["admin"],
            effective_to=effective_to,
        )

    return professor, user


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


# -- the display identity -------------------------------------------------


@pytest.mark.asyncio
async def test_a_read_row_names_the_student_and_the_class(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The read model carries names, not ids.

    The queues used to render `Student #<id>` and `Session #<id>`, because
    the read model carried no display identity at all. The slice resolves it
    now, the same rule the audit trail follows (ADR-088).
    """
    graph = await _seed(factories)
    excuse_id = await _student_request(test_db_session, graph)
    excuse = await _excuse_row(test_db_session, excuse_id)

    service = _service(test_db_session)
    await service._resolve_names([excuse])
    read = service._to_read(excuse)

    assert read.student_number == graph["student"].student_id
    assert read.student_name == "Test Student0"
    assert "Student #" not in read.student_name
    assert read.session_code == graph["session"].session_code
    assert read.course_code
    assert read.course_name
    # Nobody has reviewed it yet.
    assert read.reviewed_by_name is None


@pytest.mark.asyncio
async def test_a_reviewed_row_names_its_reviewer(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The reviewer's name comes from their roster row, not their id."""
    graph = await _seed(factories)
    excuse_id = await _student_request(test_db_session, graph)
    excuse = await _excuse_row(test_db_session, excuse_id)

    service = _service(test_db_session)
    await service._resolve_names([excuse])
    read = service._to_read(excuse)

    assert read.reviewed_by_name is None

    await _service(test_db_session).review_excuse(
        user_id=graph["professor_user"].id,
        request_id=excuse_id,
        payload=ExcuseReviewRequest(status=APPROVED),
    )
    excuse = await _excuse_row(test_db_session, excuse_id)

    service = _service(test_db_session)
    await service._resolve_names([excuse])
    read = service._to_read(excuse)

    assert read.reviewed_by_name
    assert read.reviewed_by_name != f"User #{graph['professor_user'].id}"
    # The raw id stays: the per-record paths key on it.
    assert read.reviewed_by == graph["professor_user"].id


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


# -- who is allowed to act ----------------------------------------------


@pytest.mark.asyncio
async def test_a_coteacher_can_approve_a_request(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Assignment is what authorizes the action, not owning the session.

    A co-teacher is a recipient when a request is filed, and the mail tells
    them to review it, so they have to be able to.
    """
    graph = await _seed(factories)
    request_id = await _student_request(test_db_session, graph)
    _, second_user = await _second_professor(factories, graph)

    reviewed = await _service(test_db_session).review_excuse(
        user_id=second_user.id,
        request_id=request_id,
        payload=ExcuseReviewRequest(
            status=APPROVED, review_notes="Medical certificate checks out."
        ),
    )

    assert reviewed.status == APPROVED
    await test_db_session.refresh(graph["record"])
    assert graph["record"].validation_status == EXCUSED
    assert graph["record"].original_status == ABSENT
    assert graph["record"].excused_by == second_user.id


@pytest.mark.asyncio
async def test_a_coteacher_sees_the_request_in_their_queue(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The queue has to show what the other methods will let them act on."""
    graph = await _seed(factories)
    request_id = await _student_request(test_db_session, graph)
    _, second_user = await _second_professor(factories, graph)

    queue = await _service(test_db_session).list_for_professor(
        user_id=second_user.id, status=PENDING, page=1, size=20
    )

    assert [row.id for row in queue.items] == [request_id]
    assert queue.total == 1


@pytest.mark.asyncio
async def test_an_unassigned_professor_cannot_approve(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Widening this to the teaching team must not open it to any professor."""
    graph = await _seed(factories)
    request_id = await _student_request(test_db_session, graph)
    _, second_user = await _second_professor(factories, graph, assigned=False)

    with pytest.raises(ProfessorNotAssignedException) as caught:
        await _service(test_db_session).review_excuse(
            user_id=second_user.id,
            request_id=request_id,
            payload=ExcuseReviewRequest(status=APPROVED),
        )

    assert caught.value.status_code == 403
    assert caught.value.code == "not_assigned"
    assert (await _excuse_row(test_db_session, request_id)).status == PENDING


@pytest.mark.asyncio
async def test_a_lapsed_assignment_cannot_approve(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The window is the assignment's, so an ended one is not a current one."""
    graph = await _seed(factories)
    request_id = await _student_request(test_db_session, graph)
    _, second_user = await _second_professor(
        factories,
        graph,
        effective_to=factories.now.date() - timedelta(days=1),
    )

    with pytest.raises(ProfessorNotAssignedException):
        await _service(test_db_session).review_excuse(
            user_id=second_user.id,
            request_id=request_id,
            payload=ExcuseReviewRequest(status=APPROVED),
        )

    assert (await _excuse_row(test_db_session, request_id)).status == PENDING


@pytest.mark.asyncio
async def test_an_unassigned_professor_sees_an_empty_queue(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The list is scoped the same way the actions are."""
    graph = await _seed(factories)
    await _student_request(test_db_session, graph)
    _, second_user = await _second_professor(factories, graph, assigned=False)

    queue = await _service(test_db_session).list_for_professor(
        user_id=second_user.id, status=None, page=1, size=20
    )

    assert queue.items == []
    assert queue.total == 0
