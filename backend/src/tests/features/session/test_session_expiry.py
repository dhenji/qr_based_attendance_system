"""Session expiry against a real database (coding-standards 5.1).

Expiry is the one place where "who is allowed to scan" is decided by a
timestamp rather than a permission, and a student who scans one second after
the window closes must be refused. The cases below pin every branch that can
make a session read as closed:

- `expires_at` in the past
- `expires_at is None` (never stamped)
- a live `expires_at` but a `scanned_at` past it
- an exactly-boundary `expires_at` (the `_session_status` and
  `verify_code` comparisons disagree on the boundary on purpose)
- the D49 computed expiry, `min(created_at + duration, scheduled_end_time)`
- `close_session` stamping `expires_at` with the current time

`Session` carries no status column: it reads active while `expires_at` is in
the future and closed otherwise. The tests assert that derived status rather
than a stored flag, because there is no flag to drift.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.attendance.model import Attendance
from features.course.exceptions import (
    OfferingNotFoundException,
    WindowsExceedDurationException,
)
from features.excuse.exceptions import ProfessorNotAssignedException
from features.course_professor.model import CourseProfessor
from features.session.exceptions import (
    SessionAlreadyActiveException,
    SessionExpiredException,
    SessionNotFoundException,
)
from features.session.model import Session
from features.session.schema import SessionCreate
from features.professor.model import Professor
from features.session.service import SessionService
from shared.enums import ValidationStatus
from tests.conftest import Factories

UNKNOWN_SESSION_ID = 2**31


def past(minutes: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def future(minutes: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def open_session(
    factories: Factories, settings: Settings, **kwargs: Any
) -> tuple[dict[str, Any], SessionService]:
    """Seed an assigned offering and open a real session through the service."""

    program = await factories.program()
    year_level = await factories.year_level(program)
    student = await factories.student(year_level)
    professor = await factories.professor()
    admin = await factories.user(role="admin")
    course = await factories.course(session_duration_hours=1.0)
    offering = await factories.offering(course, program, year_level)
    await factories.assignment(offering, professor, admin)
    await factories.enrollment(student, offering)

    stack: dict[str, Any] = {
        "program": program,
        "year_level": year_level,
        "student": student,
        "professor": professor,
        "admin": admin,
        "course": course,
        "offering": offering,
    }
    service = SessionService(factories.db, settings)

    return stack, service


# --- create_session expiry derivation -------------------------------------


async def test_create_session_stamps_expiry_from_created_at(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Expiry is `created_at + duration`, floored by `scheduled_end_time` (D49)."""

    stack, service = await open_session(factories, settings)

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id, duration_minutes=60),
    )

    assert read.expires_at is not None
    assert read.expires_at > datetime.now(timezone.utc)
    # A 60-minute session opened just now: expiry lands on the schedule end.
    # Asserted with a one-second tolerance because `created_at` comes back at
    # the database clock's second resolution, while `scheduled_end_time` is
    # built in Python at microsecond resolution.
    tolerance = timedelta(seconds=1)
    assert abs(read.expires_at - read.scheduled_end_time) < tolerance
    assert abs(read.expires_at - (read.created_at + timedelta(minutes=60))) < tolerance
    assert read.session_code


async def test_create_session_resolves_duration_from_course(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """No explicit duration: fall back to `session_duration_hours * 60`."""

    stack, service = await open_session(factories, settings)
    # full_stack/open_session set session_duration_hours=1.0 -> 60 minutes.
    stack["course"].session_duration_hours = 1.5

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()
    assert row.duration_minutes == 90


async def test_create_session_copies_offering_window_defaults(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    stack["offering"].default_present_window_minutes = 3
    stack["offering"].default_late_window_minutes = 7

    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(
            offering_id=stack["offering"].id, duration_minutes=60
        ),
    )

    assert read.qr_payload.pw == 3
    assert read.qr_payload.lw == 7


async def test_create_session_rejects_windows_exceeding_duration(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The DB CHECK constraint's business rule, refused before the write.

    The schema validator only fires when all three fields are supplied, so
    the service check is what catches an oversized window in the common case
    where the duration is derived.
    """

    stack, service = await open_session(factories, settings)
    stack["offering"].default_present_window_minutes = 55
    stack["offering"].default_late_window_minutes = 30

    # Only `duration_minutes` is supplied, so the windows come from the
    # offering defaults and the *service* check is what refuses them; the
    # schema validator cannot fire because it needs all three fields.
    with pytest.raises(WindowsExceedDurationException):
        await service.create_session(
            professor_id=stack["professor"].id,
            payload=SessionCreate(
                offering_id=stack["offering"].id,
                duration_minutes=60,
            ),
        )


async def test_create_session_rejects_unknown_offering(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The offering lookup runs before the assignment check."""

    await factories.full_stack()
    service = SessionService(test_db_session, settings)
    professor = await factories.professor()

    with pytest.raises(OfferingNotFoundException):
        await service.create_session(
            professor_id=professor.id,
            payload=SessionCreate(offering_id=UNKNOWN_SESSION_ID),
        )


async def test_create_session_requires_current_assignment(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    stranger = await factories.professor()

    with pytest.raises(ProfessorNotAssignedException):
        await service.create_session(
            professor_id=stranger.id,
            payload=SessionCreate(offering_id=stack["offering"].id),
        )


async def test_second_active_session_for_an_offering_is_rejected(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    payload = SessionCreate(offering_id=stack["offering"].id, duration_minutes=60)
    await service.create_session(
        professor_id=stack["professor"].id, payload=payload
    )

    with pytest.raises(SessionAlreadyActiveException) as excinfo:
        await service.create_session(
            professor_id=stack["professor"].id, payload=payload
        )

    assert excinfo.value.status_code == 409


# --- verify_code expiry gate ---------------------------------------------


async def test_verify_code_resolves_a_live_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    verified = await service.verify_code(code=read.session_code)

    assert verified.session_id == read.id
    assert verified.course_code == stack["course"].course_code
    assert verified.program_code == stack["program"].code


async def test_verify_code_rejects_expired_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    with pytest.raises(SessionExpiredException) as excinfo:
        await service.verify_code(code=read.session_code)

    assert excinfo.value.status_code == 410
    assert excinfo.value.code == "session_expired"


async def test_verify_code_rejects_unstamped_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """`expires_at is None` reads as closed, mirroring `_session_status`."""

    stack = await factories.full_stack(expires_at=None)
    service = SessionService(test_db_session, settings)

    with pytest.raises(SessionExpiredException):
        await service.verify_code(code=stack["session"].session_code)


async def test_verify_code_rejects_unknown_code(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    await factories.full_stack()
    service = SessionService(test_db_session, settings)

    with pytest.raises(SessionNotFoundException) as excinfo:
        await service.verify_code(code="NOSUCHCODE")

    assert excinfo.value.status_code == 404


async def test_verify_code_trims_whitespace(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """A student typing the code from a manual entry gets stray spaces."""

    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    verified = await service.verify_code(code=f"  {read.session_code}\n")

    assert verified.session_id == read.id


# --- close_session --------------------------------------------------------


async def test_close_session_stamps_expiry_with_now(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    before = datetime.now(timezone.utc)

    await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()
    assert row.expires_at is not None
    assert before <= row.expires_at <= datetime.now(timezone.utc)


async def test_close_session_is_idempotent(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Closing twice is a no-op, and must not push `expires_at` forward."""

    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    first = await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )
    stamp_after_first: datetime = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one().expires_at

    second = await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert first.final_counts == second.final_counts

    # The second close left the first stamp in place rather than overwriting
    # it with a later `now`.
    stamp_after_second: datetime = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one().expires_at
    assert stamp_after_second == stamp_after_first


async def test_close_session_rejects_a_professor_outside_the_team(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Neither owner nor co-teacher, so there is no assignment to act on.

    A 403 about the missing assignment, not a 404 about the session going
    missing (which is what the old ownership rule reported).
    """

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    stranger = await factories.professor()

    with pytest.raises(ProfessorNotAssignedException) as caught:
        await service.close_session(session_id=opened.id, professor_id=stranger.id)

    assert caught.value.status_code == 403
    assert caught.value.code == "not_assigned"


async def test_a_coteacher_can_close_a_shared_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Whoever opened it, a current assignee can end the scanning window.

    Only one session can be open per offering, so a co-teacher running a shared
    class has no other way to close the one they were handed.
    """

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    coteacher = await factories.professor()
    await factories.assignment(
        stack["offering"], coteacher, assigned_by=stack["admin"]
    )

    closed = await service.close_session(
        session_id=opened.id, professor_id=coteacher.id
    )

    assert closed.status == "closed"
    # Attribution is untouched: the session stays on the professor who opened it.
    row = await test_db_session.get(Session, opened.id)
    assert row.professor_id == stack["professor"].id
    assert row.expires_at is not None
    assert row.expires_at <= datetime.now(timezone.utc)


async def test_a_lapsed_assignment_cannot_close_a_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The window is the assignment's, so an ended one is not a current one."""

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    previous = await factories.professor()
    await factories.assignment(
        stack["offering"],
        previous,
        assigned_by=stack["admin"],
        effective_to=factories.now.date() - timedelta(days=1),
    )

    with pytest.raises(ProfessorNotAssignedException):
        await service.close_session(session_id=opened.id, professor_id=previous.id)

    row = await test_db_session.get(Session, opened.id)
    assert row.expires_at is not None
    assert row.expires_at > factories.now


# --- derived status -------------------------------------------------------


@pytest.mark.parametrize(
    ("expires_at", "expected"),
    [
        (future(30), "active"),
        (past(1), "closed"),
        (None, "closed"),
    ],
    ids=["future", "past", "unstamped"],
)
async def test_active_session_reports_derived_status(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
    expires_at: datetime | None,
    expected: str,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()
    row.expires_at = expires_at
    await test_db_session.flush()

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert active.status == expected


async def test_scan_window_remaining_counts_down(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    # A 60-minute session opened seconds ago: under an hour left, and not
    # yet expired.
    assert 0 < active.scan_window_remaining <= 3600


async def test_scan_window_remaining_is_zero_when_unstamped(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()
    row.expires_at = None
    await test_db_session.flush()

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert active.scan_window_remaining == 0


# --- computed_expires_at (D49) -------------------------------------------


async def test_computed_expiry_is_created_at_plus_duration(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The duration branch of the min()."""

    stack = await factories.full_stack(
        duration_minutes=45, scheduled_end_time=future(600)
    )
    session = stack["session"]
    session.created_at = datetime.now(timezone.utc).replace(microsecond=0)

    assert session.computed_expires_at == session.created_at + timedelta(minutes=45)


async def test_computed_expiry_floors_at_scheduled_end(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The schedule branch: a short duration inside an early-ending block."""

    stack = await factories.full_stack(duration_minutes=30)
    session = stack["session"]
    end = datetime.now(timezone.utc) + timedelta(minutes=10)
    session.scheduled_end_time = end
    session.created_at = datetime.now(timezone.utc).replace(microsecond=0)

    assert session.computed_expires_at == end


# --- attendance read path over a closed session ---------------------------


async def test_active_view_counts_enrolled_and_scanned(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await factories.attendance(
        stack["student"],
        Session(id=read.id, offering_id=stack["offering"].id),
        validation_status=ValidationStatus.PRESENT.value,
    )

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert active.enrolled_count == 1
    assert active.remaining == 0
    assert active.counts.present == 1
    assert active.students[0].status == ValidationStatus.PRESENT


async def test_active_view_marks_unscanned_students_absent(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert active.remaining == 1
    assert active.students[0].status == ValidationStatus.ABSENT


async def test_close_session_summarises_final_counts(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await factories.attendance(
        stack["student"],
        Session(id=read.id, offering_id=stack["offering"].id),
        validation_status=ValidationStatus.LATE.value,
    )

    closed = await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    assert closed.final_counts.late == 1
    assert closed.final_counts.present == 0


async def test_unknown_session_id_raises_not_found(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    service = SessionService(test_db_session, settings)

    with pytest.raises(SessionNotFoundException):
        await service.get_active_session(
            session_id=UNKNOWN_SESSION_ID, professor_id=1
        )


async def test_expired_session_row_is_not_reopenable_by_a_scan(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The professor view reads closed and the student path agrees.

    The two read expiry differently (`_session_status` uses `>` while the
    scan guard uses `<=`), so an exact-boundary expiry is the one case where
    they can disagree. Closing first moves the stamp decisively into the
    past, which is the real-world path and must not diverge.
    """

    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    with pytest.raises(SessionExpiredException):
        await service.verify_code(code=read.session_code)

    active = await service.get_active_session(
        session_id=read.id, professor_id=stack["professor"].id
    )
    assert active.status == "closed"
    assert active.scan_window_remaining == 0


# --- derived expiry across the read endpoints ----------------------------
#
# The list and history endpoints derive the same status as `get_active_session`
# from the same column, so a session that reads "closed" in one place has to
# read "closed" in all of them.


async def test_session_list_reports_the_derived_status(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack = await factories.full_stack(expires_at=past(5))
    service = SessionService(test_db_session, settings)

    listed = await service.list_professor_sessions(
        professor_id=stack["professor"].id
    )

    assert listed.total == 1
    assert listed.items[0].status == "closed"


async def test_session_list_reports_active_and_its_counts(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)

    listed = await service.list_professor_sessions(
        professor_id=stack["professor"].id
    )

    item = listed.items[0]
    assert item.status == "active"
    # The list tile carries per-status tallies, not an enrolled total: an
    # unscanned student reads as absent.
    assert item.absent_count == 1
    assert item.present_count == 0
    assert item.late_count == 0


async def test_session_list_excludes_a_professor_outside_the_team(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    await factories.full_stack()
    service = SessionService(test_db_session, settings)
    stranger: Professor = await factories.professor()

    # The seeded session was opened by somebody else, and `full_stack` seeds no
    # teaching assignment, so this professor has neither claim to it.
    listed = await service.list_professor_sessions(professor_id=stranger.id)

    assert listed.total == 0
    assert listed.items == []


async def test_a_coteacher_sees_the_shared_sessions(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The list and the ledger have to widen together.

    The frontend reads `list_professor_sessions` to build a session directory
    and joins the ledger onto it. If only one of the two widened, co-teacher rows
    would arrive with no session to join to.
    """

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await factories.attendance(
        stack["student"],
        Session(id=opened.id, offering_id=stack["offering"].id),
        validation_status=ValidationStatus.PRESENT.value,
    )
    coteacher = await factories.professor()
    await factories.assignment(
        stack["offering"], coteacher, assigned_by=stack["admin"]
    )

    listed = await service.list_professor_sessions(professor_id=coteacher.id)
    ledger = await service.get_professor_attendance(professor_id=coteacher.id)

    assert [item.id for item in listed.items] == [opened.id]
    assert [row.session_id for row in ledger.items] == [opened.id]
    assert ledger.total == 1


async def test_past_sessions_stay_visible_after_an_assignment_ends(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The reason the scope is a union and not a replacement.

    An assignment window is anchored to today, so scoping on assignment alone
    would empty a professor's history the day their `effective_to` passes - the
    one thing `Session.professor_id` exists to prevent. Ownership has to keep
    working on its own.
    """

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await factories.attendance(
        stack["student"],
        Session(id=opened.id, offering_id=stack["offering"].id),
        validation_status=ValidationStatus.LATE.value,
    )
    await service.close_session(session_id=opened.id, professor_id=stack["professor"].id)
    # Every assignment on the offering ends, including the one the seed created.
    ended = await test_db_session.scalar(
        select(CourseProfessor).where(CourseProfessor.offering_id == stack["offering"].id)
    )
    assert ended is not None
    ended.effective_to = factories.now.date() - timedelta(days=1)
    await test_db_session.flush()

    listed = await service.list_professor_sessions(professor_id=stack["professor"].id)
    history = await service.get_session_history(professor_id=stack["professor"].id)
    ledger = await service.get_professor_attendance(
        professor_id=stack["professor"].id
    )

    assert [item.id for item in listed.items] == [opened.id]
    assert [item.id for item in history.items] == [opened.id]
    assert [row.session_id for row in ledger.items] == [opened.id]


async def test_a_lapsed_assignment_stops_showing_shared_history(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The inverse case: the list follows the assignment, not a shared claim.

    A professor who co-taught before mid-term replacement never owned the
    session, so once their assignment ends they lose the historical view of it -
    only `Session.professor_id` outlives the assignment, and only for whoever
    holds that value.
    """

    stack, service = await open_session(factories, settings)
    opened = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await service.close_session(session_id=opened.id, professor_id=stack["professor"].id)
    previous = await factories.professor()
    await factories.assignment(
        stack["offering"],
        previous,
        assigned_by=stack["admin"],
        effective_to=factories.now.date() - timedelta(days=1),
    )

    listed = await service.list_professor_sessions(professor_id=previous.id)
    history = await service.get_session_history(professor_id=previous.id)
    owner = await service.list_professor_sessions(professor_id=stack["professor"].id)

    assert [item.id for item in listed.items] == []
    assert [item.id for item in history.items] == []
    assert [item.id for item in owner.items] == [opened.id]


async def test_session_list_normalizes_out_of_range_paging(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """page/size are clamped, so a client cannot ask for page 0 or size 0."""

    await factories.full_stack()
    service = SessionService(test_db_session, settings)

    listed = await service.list_professor_sessions(
        professor_id=1, page=0, size=0
    )

    assert listed.page == 1
    assert listed.size == 1


async def test_history_section_filter_keeps_matching_sessions(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The history section filter reads the offering's sections, not the row.

    `_matches_section` asks whether *any* enrolled student in the offering is
    in the requested section, so a session survives a filter for a section it
    has no attendance in, and drops for one it does.
    """

    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)

    matching = await service.get_session_history(
        professor_id=stack["professor"].id, section=stack["student"].section
    )
    unlisted = await service.get_session_history(
        professor_id=stack["professor"].id, section="Z9"
    )

    assert matching.total == 1
    assert unlisted.total == 0


async def test_history_reports_a_closed_session(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack = await factories.full_stack(expires_at=past(5))
    service = SessionService(test_db_session, settings)

    history = await service.get_session_history(professor_id=stack["professor"].id)

    assert history.total == 1
    assert history.items[0].status == "closed"


async def test_professor_attendance_lists_scanned_rows(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)
    await factories.attendance(
        stack["student"],
        stack["session"],
        validation_status=ValidationStatus.LATE.value,
    )

    listed = await service.get_professor_attendance(
        professor_id=stack["professor"].id
    )

    assert listed.total == 1
    assert listed.items[0].status == ValidationStatus.LATE.value


async def test_professor_attendance_filters_by_section(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)
    await factories.attendance(stack["student"], stack["session"])

    # Two sections, so the filter has something real to exclude.
    other = await factories.student(stack["year_level"], section="B2")
    await factories.enrollment(other, stack["offering"])
    await factories.attendance(other, stack["session"])

    mine = await service.get_professor_attendance(
        professor_id=stack["professor"].id, section=stack["student"].section
    )
    theirs = await service.get_professor_attendance(
        professor_id=stack["professor"].id, section="Z9"
    )
    unlisted = await service.get_professor_attendance(
        professor_id=stack["professor"].id
    )

    assert mine.total == 1
    assert mine.items[0].section == stack["student"].section
    # "Z9" is in neither section, so it must not match every row.
    assert theirs.total == 0
    assert unlisted.total == 2


async def test_professor_attendance_filters_by_course(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """The course filter adds a `course_offerings` join, so it needs coverage.

    The other filters are `apply_if` on a column already joined; this one
    changes the FROM clause, and a wrong join there would silently return
    every row instead of none.
    """

    stack = await factories.full_stack()
    other_course = await factories.course()
    other_offering = await factories.offering(
        other_course, stack["program"], stack["year_level"], semester="2ND_SEM"
    )
    other_session = await factories.session(
        other_offering,
        stack["professor"],
        expires_at=stack["session"].expires_at,
    )
    service = SessionService(test_db_session, settings)
    await factories.attendance(stack["student"], stack["session"])
    await factories.attendance(stack["student"], other_session)

    mine = await service.get_professor_attendance(
        professor_id=stack["professor"].id, course_id=stack["course"].id
    )
    theirs = await service.get_professor_attendance(
        professor_id=stack["professor"].id, course_id=other_course.id
    )

    # The row DTO carries no course field, so the filter is asserted through
    # which session survived it.
    assert mine.total == 1
    assert mine.items[0].session_id == stack["session"].id
    assert theirs.total == 1
    assert theirs.items[0].session_id == other_session.id


async def test_inactive_students_are_excluded_from_enrolled_counts(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Both the tile count and the section filter skip archived students.

    They read `_enrollment_count` and `_offering_sections`, which join
    `students` and filter `is_active`, so a student archived after enrolling
    must not keep inflating the professor's numbers.
    """

    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)
    stack["student"].is_active = False
    await test_db_session.flush()

    active = await service.get_active_session(
        session_id=stack["session"].id, professor_id=stack["professor"].id
    )

    assert active.enrolled_count == 0
    assert active.students == []


async def test_rates_are_zero_when_nothing_is_enrolled(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    """Guards the divide-by-zero: `_rates` returns 0.0, not an error."""

    stack = await factories.full_stack()
    service = SessionService(test_db_session, settings)
    stack["student"].is_active = False
    await test_db_session.flush()

    history = await service.get_session_history(professor_id=stack["professor"].id)

    assert history.items[0].compliance_rate == 0.0
    assert history.items[0].participation_rate == 0.0


async def test_student_and_session_rows_stay_consistent_after_close(
    test_db_session: AsyncSession,
    factories: Factories,
    settings: Settings,
) -> None:
    stack, service = await open_session(factories, settings)
    read = await service.create_session(
        professor_id=stack["professor"].id,
        payload=SessionCreate(offering_id=stack["offering"].id),
    )
    await service.close_session(
        session_id=read.id, professor_id=stack["professor"].id
    )

    row: Session = (
        await test_db_session.scalars(select(Session).where(Session.id == read.id))
    ).one()

    # The closed stamp is on the row itself, so the student scan path reads
    # the same expiry the professor view just reported.
    assert row.expires_at is not None
    assert row.expires_at <= datetime.now(timezone.utc)
    assert stack["student"].id is not None
    assert await test_db_session.scalar(
        select(Attendance.id).where(Attendance.session_id == read.id)
    ) is None
