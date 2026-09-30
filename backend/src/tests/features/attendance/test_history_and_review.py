"""Student attendance history and the admin liveness-review queue.

Two cohesive areas of `AttendanceService` that the scan tests do not reach,
both exercised against a real database so the derived rates are computed by
the same SQL production runs.

Student history (`get_history`) is a two-denominator calculation, and the
denominators are deliberately *not* filtered the same way:

- `_history_enrolled` counts distinct sessions the student was enrolled in.
- `_history_scanned` counts attendance rows in scope.
- Both take `_apply_offering_scope` — the offering-scoped half of the filter
  set, with `status` deliberately omitted so that adding `?status=present`
  cannot move the compliance rate.

That asymmetry is the whole point of the endpoint and is easy to break, so
each test below pins one side of it.

The review queue (`list_liveness_review` / `resolve_review`) splits its gate
in two, and the split is worth stating because it is easy to assume
otherwise: listing filters on `validation_status` only
(`_pending_review_filter`), while *resolving* additionally requires
`liveness_evidence["review"]` to be set (`_load_pending_review`). A pending
row that was not liveness-flagged is therefore visible in the queue but
rejects a resolve with 409 `review_not_pending`.

`get_history` takes a `users.id`, not a `students.id` — it resolves through
`Student.user_id`. Every test here links a real user so the lookup succeeds.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import ValidationStatus
from tests.conftest import Factories
from features.attendance.exceptions import (
    ReviewNotFoundException,
    ReviewNotPendingException,
)
from features.attendance.model import Attendance
from features.attendance.service import AttendanceService

PENDING = ValidationStatus.PENDING.value
PRESENT = ValidationStatus.PRESENT.value
LATE = ValidationStatus.LATE.value
ABSENT = ValidationStatus.ABSENT.value
EXCUSED = ValidationStatus.EXCUSED.value
REJECTED = ValidationStatus.REJECTED.value


def _service(session: AsyncSession) -> AttendanceService:
    return AttendanceService(session)


async def _seed_history(
    factories: Factories, *, statuses: list[str]
) -> tuple[dict[str, Any], Any, int]:
    """One linked student, one session + one scan per entry in `statuses`.

    Each status gets its own session, so a `status=` filter has something to
    discriminate on. The student is enrolled once: `enrollments` is unique on
    (student_id, offering_id, academic_year), and the enrolled denominator
    counts distinct *sessions*, not enrollments.

    Returns `(graph, user, enrolled)`. `enrolled` is the denominator the
    service should compute: `full_stack` already opens one session for the
    student before this helper adds `len(statuses)` more, so it is
    `len(statuses) + 1` — not `len(statuses)`. Getting that wrong is the
    easiest way to mis-assert a rate.
    """
    graph = await factories.full_stack()
    student = graph["student"]
    professor = graph["professor"]
    offering = graph["offering"]
    user = await factories.user(role="student")
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

    graph["user"] = user
    return graph, user, len(statuses) + 1


# -- sort validation -------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sort_by_is_rejected(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    user = await factories.user()
    student = await factories.student(year_level=await factories.year_level(program))
    student.user_id = user.id

    with pytest.raises(Exception) as exc_info:
        await _service(test_db_session).get_history(user_id=user.id, sort_by="nonsense")

    assert exc_info.value.code == "invalid_sort"
    assert exc_info.value.field == "sort_by"


@pytest.mark.asyncio
async def test_invalid_sort_dir_is_rejected(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    user = await factories.user()
    student = await factories.student(year_level=await factories.year_level(program))
    student.user_id = user.id

    with pytest.raises(Exception) as exc_info:
        await _service(test_db_session).get_history(
            user_id=user.id, sort_dir="sideways"
        )

    assert exc_info.value.code == "invalid_sort"
    assert exc_info.value.field == "sort_dir"


@pytest.mark.asyncio
async def test_history_for_an_unlinked_user_is_404(
    test_db_session: AsyncSession,
) -> None:
    from features.student.exceptions import StudentNotFoundException

    with pytest.raises(StudentNotFoundException) as exc_info:
        await _service(test_db_session).get_history(user_id=999_999)

    assert exc_info.value.code == "student_not_found"


# -- summary arithmetic ----------------------------------------------------


@pytest.mark.asyncio
async def test_empty_history_is_a_zeroed_summary_not_a_division_error(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    user = await factories.user()
    student = await factories.student(year_level=await factories.year_level(program))
    student.user_id = user.id

    page = await _service(test_db_session).get_history(user_id=user.id)

    assert page.items == []
    assert page.total == 0
    assert page.summary.counts.present == 0
    # No enrollments means a zero denominator; the rates must come back 0.0
    # rather than raising ZeroDivisionError (`_history_rates`).
    assert page.summary.compliance_rate == 0.0
    assert page.summary.participation_rate == 0.0


@pytest.mark.asyncio
async def test_counts_and_rates_split_present_from_participation(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """compliance = present/enrolled; participation = (present+late+excused)
    over enrolled."""
    _graph, user, enrolled = await _seed_history(
        factories,
        statuses=[PRESENT, PRESENT, LATE, EXCUSED, ABSENT],
    )

    page = await _service(test_db_session).get_history(user_id=user.id)

    counts = page.summary.counts
    assert counts.present == 2
    assert counts.late == 1
    assert counts.excused == 1
    assert counts.absent == 1
    # Five scans, but six enrolled sessions (the `full_stack` one has no
    # scan), so the denominator is larger than the row count.
    assert page.total == 5

    assert page.summary.compliance_rate == round(2 / enrolled, 4)
    assert page.summary.participation_rate == round((2 + 1 + 1) / enrolled, 4)


# -- filters ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_filter_narrows_items_but_not_the_denominator(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The documented asymmetry: `status` filters rows, not enrolled."""
    _graph, user, enrolled = await _seed_history(
        factories, statuses=[PRESENT, PRESENT, LATE, ABSENT]
    )
    service = _service(test_db_session)

    unfiltered = await service.get_history(user_id=user.id)
    filtered = await service.get_history(user_id=user.id, status=PRESENT)

    assert unfiltered.total == 4
    assert filtered.total == 2
    assert {i.status for i in filtered.items} == {ValidationStatus.PRESENT}

    # The denominator is every enrolled session in scope, not just the two
    # that matched, so the rate is 2/enrolled — and it does not move when the
    # filter is added.
    assert filtered.summary.compliance_rate == round(2 / enrolled, 4)
    assert unfiltered.summary.compliance_rate == round(2 / enrolled, 4)

    # The tallies *are* filtered: late drops out with `?status=present`.
    assert filtered.summary.counts.present == 2
    assert filtered.summary.counts.late == 0
    assert unfiltered.summary.counts.late == 1

    # `absent` is not tallied — an absence has no attendance row to count. It
    # is derived as `enrolled - scanned`, so it is deliberately independent of
    # the status filter and stays 1 in both views.
    assert filtered.summary.counts.absent == enrolled - 4
    assert unfiltered.summary.counts.absent == enrolled - 4


@pytest.mark.asyncio
async def test_offering_scope_filter_applies_to_both_sides(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Unlike `status`, the offering scope filters items *and* denominators."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    user = await factories.user()
    student = await factories.student(year_level)
    student.user_id = user.id
    professor = await factories.professor()
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    now = factories.now

    other_program = await factories.program()
    other_year = await factories.year_level(other_program)
    other_course = await factories.course()
    other_offering = await factories.offering(other_course, other_program, other_year)

    for target in (offering, other_offering):
        db_session = await factories.session(
            target, professor, expires_at=now + timedelta(minutes=60)
        )
        await factories.enrollment(student, target)
        await factories.attendance(student, db_session)

    service = _service(test_db_session)

    everything = await service.get_history(user_id=user.id)
    scoped = await service.get_history(user_id=user.id, program_id=program.id)

    assert everything.total == 2
    assert everything.summary.compliance_rate == 1.0

    assert scoped.total == 1
    # One of two sessions survived the scope, so enrolled narrowed to 1 —
    # the denominator *did* move, unlike the status filter.
    assert scoped.summary.compliance_rate == 1.0
    assert scoped.items[0].course_code == course.course_code


@pytest.mark.asyncio
async def test_history_items_carry_course_and_excuse_fields(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    graph, user, _enrolled = await _seed_history(factories, statuses=[EXCUSED])
    course = graph["course"]

    record = await factories.attendance(
        graph["student"],
        graph["session"],
        validation_status=EXCUSED,
        original_status=ABSENT,
        excuse_reason="Medical certificate",
        scanned_via="manual_entry",
    )
    assert record.id is not None

    page = await _service(test_db_session).get_history(user_id=user.id)

    # Address the row by id: `_seed_history` already produced an EXCUSED row
    # with no original_status, so filtering by status alone would pick that one.
    item = next(i for i in page.items if i.id == record.id)
    assert item.status is ValidationStatus.EXCUSED
    assert item.course_code == course.course_code
    assert item.course_name == course.course_name
    assert item.original_status is ValidationStatus.ABSENT
    assert item.excuse_reason == "Medical certificate"
    assert item.scanned_via == "manual_entry"


@pytest.mark.asyncio
async def test_sort_by_date_orders_the_page_both_ways(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    _graph, user, _enrolled = await _seed_history(
        factories, statuses=[PRESENT, LATE, PRESENT]
    )

    service = _service(test_db_session)

    asc = await service.get_history(user_id=user.id, sort_by="date", sort_dir="asc")
    desc = await service.get_history(user_id=user.id, sort_by="date", sort_dir="desc")

    assert len(asc.items) == 3
    assert [i.scanned_at for i in asc.items] == sorted(
        i.scanned_at for i in asc.items
    )
    assert [i.scanned_at for i in desc.items] == sorted(
        (i.scanned_at for i in desc.items), reverse=True
    )


@pytest.mark.asyncio
async def test_pagination_slices_items_but_keeps_the_full_summary(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    _graph, user, _enrolled = await _seed_history(
        factories, statuses=[PRESENT, PRESENT, PRESENT, LATE]
    )

    service = _service(test_db_session)

    first = await service.get_history(user_id=user.id, page=1, size=2)
    second = await service.get_history(user_id=user.id, page=2, size=2)

    assert len(first.items) == 2
    assert len(second.items) == 2
    assert first.total == 4
    # The summary spans the whole filter set, not the page — that is the
    # documented behaviour of the envelope.
    assert first.summary.counts.present == 3
    assert second.summary.counts.present == 3
    assert (first.page, first.size) == (1, 2)
    assert (second.page, second.size) == (2, 2)


# -- liveness review queue -------------------------------------------------


async def _flag_for_review(
    factories: Factories, *, status: str, review: bool, **record_overrides: Any
) -> tuple[Attendance, dict[str, Any]]:
    graph = await factories.full_stack()
    record = await factories.attendance(
        graph["student"],
        graph["session"],
        validation_status=status,
        liveness_evidence={"review": review, "blink_detected": True},
        face_match_score=0.42,
        **record_overrides,
    )
    return record, graph


@pytest.mark.asyncio
async def test_pending_rows_appear_in_the_default_queue(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    record, graph = await _flag_for_review(factories, status=PENDING, review=True)
    assert record.id is not None

    page = await _service(test_db_session).list_liveness_review()

    assert page.total == 1
    item = page.items[0]
    assert item.id == record.id
    assert item.student_number == graph["student"].student_id
    assert item.student_name == (
        f"{graph['student'].first_name} {graph['student'].last_name}"
    )
    assert item.session_code == graph["session"].session_code
    assert item.course_code == graph["course"].course_code
    assert item.face_match_score == 0.42
    assert item.evidence["review"] is True


@pytest.mark.asyncio
async def test_resolved_statuses_leave_the_pending_queue(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A settled row is not pending, so it is out of the default queue.

    The `review` flag is *not* what removes it: the list filter keys on
    `validation_status` alone.
    """
    await _flag_for_review(
        factories, status=PRESENT, review=True, original_status=ABSENT
    )

    page = await _service(test_db_session).list_liveness_review()

    assert page.total == 0
    assert page.items == []


@pytest.mark.asyncio
async def test_approved_and_rejected_queues_key_on_original_status(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """`approved` = present/late with an original_status; same idea for rejected."""
    await _flag_for_review(
        factories, status=PRESENT, review=False, original_status=LATE
    )
    await _flag_for_review(
        factories, status=REJECTED, review=False, original_status=PRESENT
    )
    # No original_status, so it belongs to neither settled queue even though
    # it is present.
    await _flag_for_review(factories, status=PRESENT, review=False)

    service = _service(test_db_session)

    approved = await service.list_liveness_review(status="approved")
    rejected = await service.list_liveness_review(status="rejected")

    assert approved.total == 1
    assert rejected.total == 1


@pytest.mark.asyncio
async def test_review_status_filter_is_validated(test_db_session: AsyncSession) -> None:
    with pytest.raises(Exception) as exc_info:
        await _service(test_db_session).list_liveness_review(status="maybe")

    assert exc_info.value.code == "invalid_status"
    assert exc_info.value.field == "status"


@pytest.mark.asyncio
async def test_approving_restores_the_original_late_status(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """`original_status` is the answer whenever it is not PRESENT."""
    record, _graph = await _flag_for_review(
        factories, status=PENDING, review=True, original_status=LATE
    )
    assert record.id is not None

    result = await _service(test_db_session).resolve_review(
        record_id=record.id, decision="approve", actor_id=1
    )

    assert result.status is ValidationStatus.LATE

    await test_db_session.refresh(record)
    assert record.validation_status == LATE
    # The gate flag is cleared, so a re-list no longer treats it as flagged.
    assert (record.liveness_evidence or {}).get("review") is None


@pytest.mark.asyncio
async def test_rejecting_marks_the_row_rejected(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    record, _graph = await _flag_for_review(
        factories, status=PENDING, review=True, original_status=PRESENT
    )
    assert record.id is not None

    result = await _service(test_db_session).resolve_review(
        record_id=record.id, decision="reject", actor_id=1
    )

    assert result.status is ValidationStatus.REJECTED
    await test_db_session.refresh(record)
    assert record.validation_status == REJECTED


@pytest.mark.asyncio
async def test_present_original_status_is_recomputed_against_the_late_window(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """An originally-PRESENT row is re-evaluated, not trusted.

    `_compute_status` anchors on `session.created_at`, so the fixture sets
    `created_at` back by 20 minutes. The scan then sits past the 5-minute
    present window but inside the 30-minute late one, so approval must land
    on LATE even though `original_status` says PRESENT.
    """
    graph = await factories.full_stack()
    now = factories.now
    opened = now - timedelta(minutes=20)

    db_session = await factories.session(
        graph["offering"],
        graph["professor"],
        created_at=opened,
        scheduled_start_time=opened,
        scheduled_end_time=now + timedelta(minutes=40),
        expires_at=now + timedelta(minutes=40),
        present_window_minutes=5,
        late_window_minutes=30,
    )
    record = await factories.attendance(
        graph["student"],
        db_session,
        validation_status=PENDING,
        original_status=PRESENT,
        liveness_evidence={"review": True},
        timestamp=opened + timedelta(minutes=20),
    )
    assert record.id is not None
    assert db_session.created_at is not None

    result = await _service(test_db_session).resolve_review(
        record_id=record.id, decision="approve", actor_id=1
    )

    assert result.status is ValidationStatus.LATE


@pytest.mark.asyncio
async def test_present_original_status_stays_present_when_inside_the_window(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The recompute agrees with `original_status` when it should."""
    graph = await factories.full_stack()
    now = factories.now
    opened = now - timedelta(minutes=20)

    db_session = await factories.session(
        graph["offering"],
        graph["professor"],
        created_at=opened,
        scheduled_start_time=opened,
        scheduled_end_time=now + timedelta(minutes=40),
        expires_at=now + timedelta(minutes=40),
        present_window_minutes=30,
        late_window_minutes=30,
    )
    record = await factories.attendance(
        graph["student"],
        db_session,
        validation_status=PENDING,
        original_status=PRESENT,
        liveness_evidence={"review": True},
        timestamp=opened + timedelta(minutes=20),
    )
    assert record.id is not None

    result = await _service(test_db_session).resolve_review(
        record_id=record.id, decision="approve", actor_id=1
    )

    assert result.status is ValidationStatus.PRESENT


@pytest.mark.asyncio
async def test_recompute_falls_back_to_present_for_an_unusable_original(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """An `original_status` that is neither present nor late is not trusted."""
    record, _graph = await _flag_for_review(
        factories, status=PENDING, review=True, original_status=ABSENT
    )
    assert record.id is not None

    result = await _service(test_db_session).resolve_review(
        record_id=record.id, decision="approve", actor_id=1
    )

    # ABSENT is not restorable, so the session is recomputed; the fixture
    # session has a 5-minute present window and the scan is stamped at
    # `now`, i.e. essentially at the anchor, so it lands on present.
    assert result.status is ValidationStatus.PRESENT


@pytest.mark.asyncio
async def test_resolving_a_missing_row_is_404(test_db_session: AsyncSession) -> None:
    with pytest.raises(ReviewNotFoundException) as exc_info:
        await _service(test_db_session).resolve_review(
            record_id=999_999, decision="approve", actor_id=1
        )

    assert exc_info.value.code == "review_not_found"


@pytest.mark.asyncio
async def test_resolving_an_unflagged_pending_row_is_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The resolve gate is stricter than the list gate: it needs the flag."""
    record, _graph = await _flag_for_review(
        factories, status=PENDING, review=False, original_status=PRESENT
    )
    assert record.id is not None

    # Visible in the queue...
    listed = await _service(test_db_session).list_liveness_review()
    assert listed.total == 1

    # ...but not resolvable.
    with pytest.raises(ReviewNotPendingException) as exc_info:
        await _service(test_db_session).resolve_review(
            record_id=record.id, decision="approve", actor_id=1
        )

    assert exc_info.value.code == "review_not_pending"


@pytest.mark.asyncio
async def test_resolving_a_settled_row_is_409(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    record, _graph = await _flag_for_review(
        factories, status=PRESENT, review=True, original_status=ABSENT
    )
    assert record.id is not None

    with pytest.raises(ReviewNotPendingException) as exc_info:
        await _service(test_db_session).resolve_review(
            record_id=record.id, decision="approve", actor_id=1
        )

    assert exc_info.value.code == "review_not_pending"


@pytest.mark.asyncio
async def test_invalid_decision_is_rejected(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    record, _graph = await _flag_for_review(factories, status=PENDING, review=True)
    assert record.id is not None

    with pytest.raises(Exception) as exc_info:
        await _service(test_db_session).resolve_review(
            record_id=record.id, decision="maybe", actor_id=1
        )

    assert exc_info.value.code == "invalid_decision"
    assert exc_info.value.field == "decision"
