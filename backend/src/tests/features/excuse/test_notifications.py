"""The excuse notification layer: who gets told, and what they read.

Four events in excuse-workflow.md §8 send mail, and each is asserted here at the
service level - `ExcuseService` decides the recipient list and the copy, then
hands the batch to `shared.email.dispatch_emails`. The dispatcher is replaced,
so these tests never touch the executor thread, SMTP, or the network;
`tests/shared/test_email.py` covers what happens on the other side of the
hand-off.

Two rules are worth stating because both are easy to get wrong:

- Recipients come from `users.email` (the address the person signs in with), not
  from the `students.email` / `professors.email` roster column. The seed gives
  every row *different* values in each place, so a test fails if that
  preference is inverted. The roster column is the fallback for a profile with
  no linked account.
- A professor hears about a request only while their assignment on the offering
  is effective. §8 says "assigned professor(s)", so a co-teacher is told as well
  as the session's own professor - but a professor whose assignment has ended is
  not.

Notifications are queued last in each method, so a request that raises must
leave nothing queued. The last two tests pin that.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from shared.email import OutboundEmail
from shared.enums import UserRole, ValidationStatus

from features.course_professor.model import CourseProfessor
from features.excuse import notifications
from features.excuse import service as excuse_service
from features.excuse.exceptions import DuplicateExcuseException
from features.excuse.schema import (
    BulkExcuseRequest,
    ExcuseReviewRequest,
    QuickExcuseRequest,
    StudentExcuseRequest,
)
from features.excuse.service import ExcuseService
from tests.conftest import Factories

SESSION_DATE = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)
SESSION_DATE_TEXT = "14 Mar 2026"

ABSENT = ValidationStatus.ABSENT.value
APPROVED = "approved"
REJECTED = "rejected"

STUDENT_REASON = "I was in the university clinic all morning with a fever."
BULK_REASON = "Class cancelled because of the storm warning."
QUICK_REASON = "I was absent because of a family emergency."
REVIEW_NOTES = "The certificate is for a different course."


def _service(session: AsyncSession) -> ExcuseService:
    return ExcuseService(session)


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[OutboundEmail]:
    """Every message `ExcuseService` handed to the dispatcher.

    The dispatcher is replaced rather than the sender, because the batch
    boundaries are themselves part of what is under test: a bulk excuse is one
    dispatch, not one per student, and that has to survive to the recording
    point to be assertable.
    """

    sent: list[OutboundEmail] = []

    def _record(messages: Any, **kwargs: Any) -> None:
        sent.extend(messages)

    monkeypatch.setattr(excuse_service, "dispatch_emails", _record)

    return sent


# -- seed ----------------------------------------------------------------


async def _seed_student(
    factories: Factories, year_level: Any, offering: Any, index: int
) -> tuple[Any, Any]:
    """A student with two addresses: the account one and the roster one.

    The pair is returned rather than read back off `student.user`, because the
    relationship is lazily loaded and this helper has no event loop to load it
    on.
    """

    user = await factories.user(
        role=UserRole.STUDENT.value, email=f"student{index}.account@test"
    )
    student = await factories.student(
        year_level,
        user=user,
        email=f"student{index}.roster@test",
        first_name="Test",
        middle_name="Q" if index == 0 else None,
        last_name=f"Student{index}",
    )

    return student, user


async def _seed(
    factories: Factories,
    *,
    status: str = ABSENT,
    extra_students: int = 0,
) -> dict[str, Any]:
    """One offering, an assigned professor, enrolled students, one session.

    The returned `graph` carries `session` (the test database session is passed
    separately), so every test asserts against the same ids.
    """

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

    session = await factories.session(
        offering,
        professor,
        scheduled_start_time=SESSION_DATE,
        scheduled_end_time=SESSION_DATE + timedelta(minutes=60),
        expires_at=SESSION_DATE + timedelta(minutes=60),
    )

    seeded = [
        await _seed_student(factories, year_level, offering, index)
        for index in range(1 + extra_students)
    ]
    students = [student for student, _ in seeded]
    records = []

    for student in students:
        await factories.enrollment(student, offering)
        records.append(
            await factories.attendance(
                student, session, validation_status=status, timestamp=SESSION_DATE
            )
        )

    return {
        "admin": admin,
        "course": course,
        "offering": offering,
        "professor": professor,
        "professor_user": professor_user,
        "session": session,
        "student": students[0],
        "student_user": seeded[0][1],
        "record": records[0],
        "other_students": students[1:],
        "other_records": records[1:],
    }


async def _add_coteacher(
    factories: Factories,
    graph: dict[str, Any],
    *,
    effective_to: date | None = None,
) -> Any:
    """A second professor assigned to the offering, with a linked account."""

    user = await factories.user(
        role=UserRole.PROFESSOR.value, email="coteacher.account@test"
    )
    professor = await factories.professor(user=user, email="coteacher.roster@test")
    await factories.assignment(
        graph["offering"],
        professor,
        assigned_by=graph["admin"],
        effective_from=factories.now.date() - timedelta(days=30),
        effective_to=effective_to,
    )

    return professor


# -- actions -------------------------------------------------------------


async def _submit(session: AsyncSession, graph: dict[str, Any]) -> Any:
    return await _service(session).submit_student_excuse(
        user_id=graph["student_user"].id,
        payload=StudentExcuseRequest(
            session_id=graph["session"].id,
            reason=STUDENT_REASON,
            attachment_urls=["/attachments/2026-03/abc123.pdf"],
        ),
    )


async def _review(
    session: AsyncSession,
    graph: dict[str, Any],
    queued: list[OutboundEmail],
    *,
    status: str = APPROVED,
    review_notes: str | None = None,
) -> Any:
    """File a request, then act on it.

    `queued` is emptied in between: the submit already notifies the professor,
    and only the review decision is under test here.
    """

    pending = await _submit(session, graph)
    queued.clear()

    return await _service(session).review_excuse(
        user_id=graph["professor_user"].id,
        request_id=pending.id,
        payload=ExcuseReviewRequest(status=status, review_notes=review_notes),
    )


def _addresses(sent: list[OutboundEmail]) -> list[str]:
    return [message.to for message in sent]


# -- student submits -----------------------------------------------------


@pytest.mark.asyncio
async def test_submit_notifies_the_assigned_professor(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)

    await _submit(test_db_session, graph)

    assert _addresses(queued) == ["professor.account@test"]
    message = queued[0]
    assert message.subject == f"New excuse request: {graph['course'].course_code}"
    assert "Test Q Student0" in message.body
    assert SESSION_DATE_TEXT in message.body
    assert STUDENT_REASON in message.body


@pytest.mark.asyncio
async def test_submit_also_notifies_a_co_teacher(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    """§8 says "assigned professor(s)", so a co-teacher is a recipient too."""

    graph = await _seed(factories)
    await _add_coteacher(factories, graph)

    await _submit(test_db_session, graph)

    assert sorted(_addresses(queued)) == [
        "coteacher.account@test",
        "professor.account@test",
    ]
    # Both read the same copy.
    assert len({message.body for message in queued}) == 1


@pytest.mark.asyncio
async def test_submit_skips_a_professor_rotated_off_the_offering(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)
    await _add_coteacher(
        factories, graph, effective_to=factories.now.date() - timedelta(days=1)
    )

    await _submit(test_db_session, graph)

    assert _addresses(queued) == ["professor.account@test"]


@pytest.mark.asyncio
async def test_submit_ignores_an_assignment_that_has_not_started(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)
    user = await factories.user(
        role=UserRole.PROFESSOR.value, email="future.account@test"
    )
    professor = await factories.professor(user=user, email="future.roster@test")
    await factories.assignment(
        graph["offering"],
        professor,
        assigned_by=graph["admin"],
        effective_from=factories.now.date() + timedelta(days=30),
    )

    await _submit(test_db_session, graph)

    assert _addresses(queued) == ["professor.account@test"]


@pytest.mark.asyncio
async def test_submit_falls_back_to_the_roster_email(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    """A professor imported before their account exists still has an address."""

    graph = await _seed(factories)
    orphan = await factories.professor(user=None, email="orphan.roster@test")
    await factories.assignment(
        graph["offering"],
        orphan,
        assigned_by=graph["admin"],
        effective_from=factories.now.date() - timedelta(days=30),
    )

    await _submit(test_db_session, graph)

    assert "orphan.roster@test" in _addresses(queued)


@pytest.mark.asyncio
async def test_submit_sends_nothing_when_the_offering_has_no_professor(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)
    await factories.db.execute(
        delete(CourseProfessor).where(
            CourseProfessor.offering_id == graph["offering"].id
        )
    )

    await _submit(test_db_session, graph)

    assert queued == []


# -- professor reviews ---------------------------------------------------


@pytest.mark.asyncio
async def test_approval_notifies_the_student(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)

    await _review(test_db_session, graph, queued, status=APPROVED)

    assert _addresses(queued) == ["student0.account@test"]
    message = queued[0]
    assert message.subject == f"Excuse approved: {graph['course'].course_code}"
    assert SESSION_DATE_TEXT in message.body
    assert "approved" in message.body


@pytest.mark.asyncio
async def test_rejection_carries_the_review_notes(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories)

    await _review(
        test_db_session, graph, queued, status=REJECTED, review_notes=REVIEW_NOTES
    )

    message = queued[0]
    assert message.subject == f"Excuse rejected: {graph['course'].course_code}"
    assert REVIEW_NOTES in message.body


@pytest.mark.asyncio
async def test_rejection_without_notes_still_states_a_reason(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    """An empty "Reason:" reads like a truncated mail."""

    graph = await _seed(factories)

    await _review(test_db_session, graph, queued, status=REJECTED, review_notes=None)

    assert notifications.REJECTION_WITHOUT_NOTES in queued[0].body


# -- bulk ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_excuse_notifies_every_student_in_one_batch(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories, extra_students=2)

    response = await _service(test_db_session).bulk_excuse_all_absent(
        user_id=graph["professor_user"].id,
        session_id=graph["session"].id,
        payload=BulkExcuseRequest(reason=BULK_REASON),
    )

    assert response.excused_count == 3
    assert sorted(_addresses(queued)) == [
        "student0.account@test",
        "student1.account@test",
        "student2.account@test",
    ]
    for message in queued:
        assert (
            message.subject == f"You have been excused: {graph['course'].course_code}"
        )
        assert BULK_REASON in message.body
        assert SESSION_DATE_TEXT in message.body


@pytest.mark.asyncio
async def test_bulk_excuse_sends_nothing_when_nobody_was_absent(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    graph = await _seed(factories, status=ValidationStatus.PRESENT.value)

    response = await _service(test_db_session).bulk_excuse_all_absent(
        user_id=graph["professor_user"].id,
        session_id=graph["session"].id,
        payload=BulkExcuseRequest(reason=BULK_REASON),
    )

    assert response.excused_count == 0
    assert queued == []


# -- events that deliberately send nothing -------------------------------


@pytest.mark.asyncio
async def test_quick_excuse_sends_nothing(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    """The professor just did it, and §8 lists no notice for it."""

    graph = await _seed(factories)

    await _service(test_db_session).quick_excuse(
        user_id=graph["professor_user"].id,
        student_id=graph["student"].id,
        session_id=graph["session"].id,
        payload=QuickExcuseRequest(reason=QUICK_REASON),
    )

    assert queued == []


@pytest.mark.asyncio
async def test_a_failed_submit_queues_nothing(
    test_db_session: AsyncSession, factories: Factories, queued: list[OutboundEmail]
) -> None:
    """A duplicate request raises, so no professor may hear about it."""

    graph = await _seed(factories)
    await _submit(test_db_session, graph)

    with pytest.raises(DuplicateExcuseException):
        await _submit(test_db_session, graph)

    # Only the first, successful submit queued anything.
    assert _addresses(queued) == ["professor.account@test"]
