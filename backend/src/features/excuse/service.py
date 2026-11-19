from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.datetimes import end_of_day, ensure_aware
from shared.email import OutboundEmail, dispatch_emails
from shared.enums import (
    AuditAction,
    AuditEntity,
    ExcuseInitiatedBy,
    ExcuseInitiatedVia,
    ExcuseStatus,
    ValidationStatus,
)
from shared.pagination import PaginatedResponse, normalize_paging, paginate_scalars
from shared.query import ilike_any

from features.attendance.model import Attendance
from features.auth.model import User
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.excuse import notifications
from features.excuse.constants import (
    EXCUSE_TYPE_QUICK,
    EXCUSE_TYPE_REQUEST_APPROVED,
    EXCUSE_TYPE_WITH_EVIDENCE,
)
from features.excuse.exceptions import (
    AlreadyExcusedException,
    AttendanceNotFoundException,
    DuplicateExcuseException,
    ExcuseNotEligibleException,
    ExcuseNotFoundException,
    ExcuseNotPendingException,
    NotEnrolledException,
    ProfessorNotAssignedException,
    ProfessorNotFoundException,
    SessionNotFoundException,
    StudentNotFoundException,
)
from features.excuse.model import ExcuseRequest
from features.excuse.schema import (
    BulkExcuseRequest,
    BulkExcuseResponse,
    ExcuseActionResponse,
    ExcuseRequestRead,
    ExcuseReviewRequest,
    ProfWithEvidenceRequest,
    QuickExcuseRequest,
    RevokeExcuseResponse,
    StudentExcuseRequest,
    StudentSubmitResponse,
)
from features.professor.model import Professor
from features.session.model import Session
from features.student.model import Student


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _full_name(
    first_name: str | None, middle_name: str | None, last_name: str | None
) -> str:
    return " ".join(part for part in (first_name, middle_name, last_name) if part)


@dataclass
class _Account:
    """A `users` row with the name its roster carries, if any.

    The `users` table has no name columns — a person's name lives on their
    student or professor row — so the name is outer-joined in, exactly as
    `features/admin/service.py::_users_stmt` does it.
    """

    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None

    @property
    def name(self) -> str:
        return _full_name(self.first_name, None, self.last_name) or self.email


def _session_date(session: Session) -> str:
    """The session's calendar day, as it reads in a notification.

    `scheduled_start_time` rather than `created_at`: a session opened late is
    still about the day it was scheduled for, and the student recognises that
    date on their timetable. Rendered without a year so the message stays short;
    a session the reader cannot place is not one they will recognise either way.
    """

    return session.scheduled_start_time.strftime("%d %b %Y")


class ExcuseService:
    """Professor-issued excuses and student excuse requests.

    Every mutation updates ``excuse_requests`` and ``attendance_records``
    in one transaction, preserving the scanned value in
    ``attendance_records.original_status`` before overwriting it. Only
    ``flush()`` is used here; commit/rollback stays in the request
    dependency.

    The four events in excuse-workflow.md §8 also queue an email, always as the
    last step of the method so a notification cannot go out for work that then
    failed. Delivery is fire-and-forget on an executor thread, so the extra
    recipient lookups are the only cost these add to the request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._excuses: BaseCRUD[ExcuseRequest] = BaseCRUD(ExcuseRequest, session)
        self._attendance: BaseCRUD[Attendance] = BaseCRUD(Attendance, session)
        # The display identity of the records a page of excuses refers to.
        # Resolved once per request, batched per kind — the same shape the
        # audit trail's resolver uses (ADR-088).
        self._students_by_id: dict[int, Student] = {}
        self._sessions_by_id: dict[int, Session] = {}
        self._offerings_by_id: dict[int, CourseOffering] = {}
        self._courses_by_id: dict[int, Course] = {}
        self._accounts_by_id: dict[int, _Account] = {}

    async def quick_excuse(
        self,
        *,
        user_id: int,
        student_id: int,
        session_id: int,
        payload: QuickExcuseRequest,
    ) -> ExcuseActionResponse:
        """Record a professor-issued excuse made from direct knowledge."""
        professor: Professor = await self._resolve_professor(user_id)
        session: Session = await self._get_session_or_404(session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )
        record: Attendance = await self._get_attendance_or_404(student_id, session_id)
        self._require_excusable(record, student_id, session_id)

        excuse: ExcuseRequest = await self._insert_excuse(
            student_id=student_id,
            session_id=session_id,
            initiated_by=ExcuseInitiatedBy.PROFESSOR.value,
            initiated_via=ExcuseInitiatedVia.QUICK.value,
            reason=payload.reason,
            attachment_urls=None,
            status=ExcuseStatus.APPROVED.value,
            reviewed_by=user_id,
            reviewed_at=_utcnow(),
            actor_id=user_id,
        )
        original: str | None = self._apply_excuse(
            record,
            excuse_id=excuse.id,
            reason=payload.reason,
            actor_id=user_id,
            excuse_type=EXCUSE_TYPE_QUICK,
        )

        await record_audit(
            self._session,
            actor_id=user_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.ATTENDANCE_RECORD,
            entity_id=record.id,
            old_value={"validation_status": original},
            new_value={"validation_status": record.validation_status},
        )

        return ExcuseActionResponse(
            excuse_request_id=excuse.id,
            status=ExcuseStatus.APPROVED.value,
            original_status=original,
            new_status=ValidationStatus.EXCUSED.value,
        )

    async def excuse_with_evidence(
        self,
        *,
        user_id: int,
        student_id: int,
        session_id: int,
        payload: ProfWithEvidenceRequest,
    ) -> ExcuseActionResponse:
        """Record a professor-issued excuse backed by held evidence."""
        professor: Professor = await self._resolve_professor(user_id)
        session: Session = await self._get_session_or_404(session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )
        record: Attendance = await self._get_attendance_or_404(student_id, session_id)
        self._require_excusable(record, student_id, session_id)

        excuse: ExcuseRequest = await self._insert_excuse(
            student_id=student_id,
            session_id=session_id,
            initiated_by=ExcuseInitiatedBy.PROFESSOR.value,
            initiated_via=ExcuseInitiatedVia.PROF_WITH_EVIDENCE.value,
            reason=payload.reason,
            attachment_urls=list(payload.attachment_urls),
            status=ExcuseStatus.APPROVED.value,
            reviewed_by=user_id,
            reviewed_at=_utcnow(),
            actor_id=user_id,
        )
        original: str | None = self._apply_excuse(
            record,
            excuse_id=excuse.id,
            reason=payload.reason,
            actor_id=user_id,
            excuse_type=EXCUSE_TYPE_WITH_EVIDENCE,
        )

        await record_audit(
            self._session,
            actor_id=user_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.ATTENDANCE_RECORD,
            entity_id=record.id,
            old_value={"validation_status": original},
            new_value={"validation_status": record.validation_status},
        )

        return ExcuseActionResponse(
            excuse_request_id=excuse.id,
            status=ExcuseStatus.APPROVED.value,
            original_status=original,
            new_status=ValidationStatus.EXCUSED.value,
        )

    async def bulk_excuse_all_absent(
        self,
        *,
        user_id: int,
        session_id: int,
        payload: BulkExcuseRequest,
    ) -> BulkExcuseResponse:
        """Excuse every still-absent record in one session.

        Idempotent: rows already excused no longer read as absent, so a
        repeat run excuses zero new rows instead of failing.
        """
        professor: Professor = await self._resolve_professor(user_id)
        session: Session = await self._get_session_or_404(session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )
        now: datetime = _utcnow()
        rows: Sequence[Attendance] = (
            await self._session.scalars(
                select(Attendance).where(
                    Attendance.session_id == session_id,
                    Attendance.validation_status == ValidationStatus.ABSENT.value,
                )
            )
        ).all()

        excused_ids: list[int] = []
        count: int = 0
        for record in rows:
            excuse: ExcuseRequest = await self._insert_excuse(
                student_id=record.student_id,
                session_id=session_id,
                initiated_by=ExcuseInitiatedBy.PROFESSOR.value,
                initiated_via=ExcuseInitiatedVia.QUICK.value,
                reason=payload.reason,
                attachment_urls=None,
                status=ExcuseStatus.APPROVED.value,
                reviewed_by=user_id,
                reviewed_at=now,
                actor_id=user_id,
            )
            original: str | None = self._apply_excuse(
                record,
                excuse_id=excuse.id,
                reason=payload.reason,
                actor_id=user_id,
                excuse_type=EXCUSE_TYPE_QUICK,
                now=now,
            )

            await record_audit(
                self._session,
                actor_id=user_id,
                action=AuditAction.UPDATE,
                entity_type=AuditEntity.ATTENDANCE_RECORD,
                entity_id=record.id,
                old_value={"validation_status": original},
                new_value={"validation_status": record.validation_status},
            )

            excused_ids.append(record.student_id)
            count += 1

        if excused_ids:
            await self._notify_bulk_excused(
                session=session,
                student_ids=excused_ids,
                reason=payload.reason,
            )

        return BulkExcuseResponse(excused_count=count, reason=payload.reason)

    async def submit_student_excuse(
        self, *, user_id: int, payload: StudentExcuseRequest
    ) -> StudentSubmitResponse:
        """File a student excuse request for the caller's own record.

        The student is resolved from the authenticated user, never from a
        body-supplied identifier. The attendance row is untouched until a
        professor approves.
        """
        student: Student = await self._resolve_student(user_id)
        session: Session = await self._get_session_or_404(payload.session_id)
        await self._require_enrollment(
            student_id=student.id, offering_id=session.offering_id
        )
        record: Attendance = await self._get_attendance_or_404(student.id, session.id)
        self._require_reviewable(record, student.id, session.id)
        await self._require_no_open_request(student.id, session.id)

        excuse: ExcuseRequest = await self._insert_excuse(
            student_id=student.id,
            session_id=session.id,
            initiated_by=ExcuseInitiatedBy.STUDENT.value,
            initiated_via=ExcuseInitiatedVia.REQUEST.value,
            reason=payload.reason,
            attachment_urls=list(payload.attachment_urls),
            status=ExcuseStatus.PENDING.value,
            reviewed_by=None,
            reviewed_at=None,
            actor_id=user_id,
        )
        await self._session.refresh(excuse)

        await self._notify_request_submitted(excuse=excuse, session=session)

        return StudentSubmitResponse(
            id=excuse.id,
            status=excuse.status,
            requested_at=excuse.requested_at,
        )

    async def review_excuse(
        self, *, user_id: int, request_id: int, payload: ExcuseReviewRequest
    ) -> ExcuseRequestRead:
        """Approve or reject a pending student request.

        Approval mutates the attendance row; rejection leaves it alone.
        """
        professor: Professor = await self._resolve_professor(user_id)
        excuse: ExcuseRequest = await self._get_excuse_or_404(request_id)
        session: Session = await self._get_session_or_404(excuse.session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )

        if excuse.status != ExcuseStatus.PENDING.value:
            raise ExcuseNotPendingException(request_id)

        now: datetime = _utcnow()
        old_value: dict[str, Any] = self._excuse_snapshot(excuse)
        excuse.status = payload.status
        excuse.reviewed_by = user_id
        excuse.reviewed_at = now
        excuse.review_notes = payload.review_notes
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=user_id,
            action=(
                AuditAction.APPROVE
                if payload.status == ExcuseStatus.APPROVED.value
                else AuditAction.REJECT
            ),
            entity_type=AuditEntity.EXCUSE,
            entity_id=excuse.id,
            old_value=old_value,
            new_value=self._excuse_snapshot(excuse),
        )

        if payload.status == ExcuseStatus.APPROVED.value:
            record: Attendance = await self._get_attendance_or_404(
                excuse.student_id, excuse.session_id
            )
            self._require_excusable(record, excuse.student_id, excuse.session_id)
            previous: str | None = self._apply_excuse(
                record,
                excuse_id=excuse.id,
                reason=excuse.reason,
                actor_id=user_id,
                excuse_type=EXCUSE_TYPE_REQUEST_APPROVED,
                now=now,
            )

            await record_audit(
                self._session,
                actor_id=user_id,
                action=AuditAction.UPDATE,
                entity_type=AuditEntity.ATTENDANCE_RECORD,
                entity_id=record.id,
                old_value={"validation_status": previous},
                new_value={"validation_status": record.validation_status},
            )

        await self._session.refresh(excuse)
        await self._notify_reviewed(excuse=excuse, session=session)

        await self._resolve_names([excuse])
        return self._to_read(excuse)

    async def edit_excuse(
        self,
        *,
        user_id: int,
        student_id: int,
        session_id: int,
        reason: str | None = None,
        review_notes: str | None = None,
    ) -> ExcuseRequestRead:
        """Update the reason or notes on an existing excuse."""
        professor: Professor = await self._resolve_professor(user_id)
        session: Session = await self._get_session_or_404(session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )
        excuse: ExcuseRequest = await self._get_professor_excuse(
            student_id, session_id, approved_only=False
        )

        old_value: dict[str, Any] = self._excuse_snapshot(excuse)

        if reason is not None:
            excuse.reason = reason
            # The attendance row carries its own copy of the reason as the audit
            # record, so a revision has to land on both tables or the two drift
            # apart permanently. Only the wording moves: the status, who excused
            # the student and when stay as the originals, so editing an approved
            # excuse never rewrites the approval.
            record: Attendance | None = await self._find_attendance(
                student_id, session_id
            )
            if record is not None and record.excuse_request_id == excuse.id:
                record.excuse_reason = reason

        if review_notes is not None:
            excuse.review_notes = review_notes

        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=user_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.EXCUSE,
            entity_id=excuse.id,
            old_value=old_value,
            new_value=self._excuse_snapshot(excuse),
        )

        await self._session.refresh(excuse)

        await self._resolve_names([excuse])
        return self._to_read(excuse)

    async def revoke_excuse(
        self, *, user_id: int, student_id: int, session_id: int
    ) -> RevokeExcuseResponse:
        """Revoke a professor-issued excuse and restore the prior status.

        The revoked request is marked `rejected` (there is no distinct
        `revoked` status by design — rejection is the terminal state and
        `original_status` on the attendance row preserves the audit trail).
        """
        professor: Professor = await self._resolve_professor(user_id)
        session: Session = await self._get_session_or_404(session_id)
        await self._require_assignment(
            offering_id=session.offering_id, professor_id=professor.id
        )
        excuse: ExcuseRequest = await self._get_professor_excuse(
            student_id, session_id, approved_only=True
        )
        record: Attendance = await self._get_attendance_or_404(student_id, session_id)
        old_value: dict[str, Any] = self._excuse_snapshot(excuse)

        # Clearing the excuse columns is only correct for the excuse that is
        # actually stamped here. Doing it unconditionally would drop an audit
        # trail this revoke has no business touching.
        reverted: str | None = None
        touched_attendance: bool = record.excuse_request_id == excuse.id

        if touched_attendance:
            reverted = record.original_status
            record.validation_status = (
                record.original_status or record.validation_status
            )
            record.original_status = None
            record.excuse_reason = None
            record.excused_by = None
            record.excused_at = None
            record.excuse_type = None
            record.excuse_request_id = None

        excuse.status = ExcuseStatus.REJECTED.value
        excuse.reviewed_by = user_id
        excuse.reviewed_at = _utcnow()
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=user_id,
            action=AuditAction.REVOKE,
            entity_type=AuditEntity.EXCUSE,
            entity_id=excuse.id,
            old_value=old_value,
            new_value=self._excuse_snapshot(excuse),
        )

        # Only when this revoke actually touched the row: the guard may have
        # declined because a different excuse is stamped there, and then no
        # attendance status moved.
        if touched_attendance:
            await record_audit(
                self._session,
                actor_id=user_id,
                action=AuditAction.UPDATE,
                entity_type=AuditEntity.ATTENDANCE_RECORD,
                entity_id=record.id,
                old_value={"validation_status": ValidationStatus.EXCUSED.value},
                new_value={"validation_status": record.validation_status},
            )

        return RevokeExcuseResponse(reverted_to=reverted)

    async def list_for_professor(
        self,
        *,
        user_id: int,
        status: str | None,
        page: int,
        size: int,
        search: str | None = None,
        course: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        section: str | None = None,
        initiated_via: str | None = None,
        has_evidence: bool | None = None,
        original_status: str | None = None,
        reviewer: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        reviewed_from: datetime | None = None,
        reviewed_to: datetime | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> PaginatedResponse[ExcuseRequestRead]:
        """List excuse requests for the offerings the professor is assigned to.

        Scoped by effective teaching assignment rather than by session ownership,
        matching what the other professor methods will let this professor act on:
        a co-teacher is a recipient of a request and is told to review it, so the
        queue has to show it to them.

        The assignment test is an EXISTS rather than a join because a professor
        can hold several assignments on one offering, and joining would repeat
        every request once per row.
        """
        professor: Professor = await self._resolve_professor(user_id)
        today: date = date.today()
        assigned = (
            select(CourseProfessor.offering_id)
            .where(
                CourseProfessor.offering_id == Session.offering_id,
                CourseProfessor.professor_id == professor.id,
                CourseProfessor.effective_from <= today,
                or_(
                    CourseProfessor.effective_to.is_(None),
                    CourseProfessor.effective_to >= today,
                ),
            )
            .exists()
        )
        stmt = (
            select(ExcuseRequest)
            .join(Session, Session.id == ExcuseRequest.session_id)
            .join(CourseOffering, CourseOffering.id == Session.offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
            .outerjoin(Student, Student.id == ExcuseRequest.student_id)
            .outerjoin(
                Attendance,
                (Attendance.student_id == ExcuseRequest.student_id)
                & (Attendance.session_id == ExcuseRequest.session_id),
            )
            .outerjoin(User, User.id == ExcuseRequest.reviewed_by)
            .where(assigned)
        )
        if status is not None:
            stmt = stmt.where(ExcuseRequest.status == status)

        if initiated_via is not None and initiated_via.strip():
            stmt = stmt.where(ExcuseRequest.initiated_via == initiated_via.strip())

        if course is not None and course.strip():
            stmt = stmt.where(Course.course_code == course.strip().upper())

        if section is not None and section.strip():
            stmt = stmt.where(Student.section == section.strip())

        if has_evidence is True:
            stmt = stmt.where(
                func.coalesce(func.jsonb_array_length(ExcuseRequest.attachment_urls), 0)
                > 0
            )
        elif has_evidence is False:
            stmt = stmt.where(
                func.coalesce(func.jsonb_array_length(ExcuseRequest.attachment_urls), 0)
                == 0
            )

        if original_status is not None and original_status.strip():
            stmt = stmt.where(
                func.coalesce(Attendance.original_status, Attendance.validation_status)
                == original_status.strip()
            )

        if date_from is not None:
            bound_from = ensure_aware(date_from)
            stmt = stmt.where(Session.created_at >= bound_from)

        if date_to is not None:
            bound_to = end_of_day(ensure_aware(date_to))
            stmt = stmt.where(Session.created_at <= bound_to)

        if submitted_from is not None:
            bound = ensure_aware(submitted_from)
            stmt = stmt.where(ExcuseRequest.requested_at >= bound)

        if submitted_to is not None:
            bound = end_of_day(ensure_aware(submitted_to))
            stmt = stmt.where(ExcuseRequest.requested_at <= bound)

        if reviewed_from is not None:
            bound = ensure_aware(reviewed_from)
            stmt = stmt.where(ExcuseRequest.reviewed_at >= bound)

        if reviewed_to is not None:
            bound = end_of_day(ensure_aware(reviewed_to))
            stmt = stmt.where(ExcuseRequest.reviewed_at <= bound)

        if reviewer is not None and reviewer.strip():
            try:
                reviewer_id = int(reviewer.strip())
            except ValueError:
                reviewer_id = None
            conditions = [
                ilike_any(
                    reviewer.strip(),
                    User.first_name,
                    User.last_name,
                    User.email,
                )
            ]
            if reviewer_id is not None:
                conditions.append(ExcuseRequest.reviewed_by == reviewer_id)
            stmt = stmt.where(or_(*conditions))

        if search is not None and search.strip():
            search_conditions = [
                ilike_any(
                    search.strip(),
                    Student.first_name,
                    Student.last_name,
                    Student.student_id,
                    Session.session_code,
                    Course.course_code,
                )
            ]
            try:
                search_conditions.append(ExcuseRequest.id == int(search.strip()))
            except ValueError:
                pass
            stmt = stmt.where(or_(*search_conditions))

        page, size = normalize_paging(page, size)

        sort_column_map = {
            "requested_at": ExcuseRequest.requested_at,
            "reviewed_at": ExcuseRequest.reviewed_at,
            "status": ExcuseRequest.status,
            "id": ExcuseRequest.id,
        }
        sort_col = sort_column_map.get(
            sort_by or "requested_at", ExcuseRequest.requested_at
        )
        if sort_by == "student_name":
            sort_col = Student.last_name
        descending = (sort_dir or "desc").lower() != "asc"
        order_expr = sort_col.desc() if descending else sort_col.asc()

        rows, total = await paginate_scalars(
            self._session,
            stmt.order_by(order_expr),
            page=page,
            size=size,
        )

        await self._resolve_names(rows)

        return PaginatedResponse[ExcuseRequestRead](
            items=[self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def list_for_student(
        self, *, user_id: int, page: int, size: int
    ) -> PaginatedResponse[ExcuseRequestRead]:
        """List the caller's own excuse requests."""
        student: Student = await self._resolve_student(user_id)
        stmt = select(ExcuseRequest).where(ExcuseRequest.student_id == student.id)

        return await self._paginate(stmt, page=page, size=size)

    async def list_for_admin(
        self, *, status: str | None, page: int, size: int
    ) -> PaginatedResponse[ExcuseRequestRead]:
        """List excuse requests system-wide."""
        stmt = select(ExcuseRequest)
        if status is not None:
            stmt = stmt.where(ExcuseRequest.status == status)

        return await self._paginate(stmt, page=page, size=size)

    async def get_for_student(
        self, *, user_id: int, request_id: int
    ) -> ExcuseRequestRead:
        """Read one of the caller's own excuse requests."""
        student: Student = await self._resolve_student(user_id)
        excuse: ExcuseRequest = await self._get_excuse_or_404(request_id)

        if excuse.student_id != student.id:
            raise ExcuseNotFoundException(request_id)

        await self._resolve_names([excuse])
        return self._to_read(excuse)

    # -- notifications (excuse-workflow.md §8) ---------------------------

    async def _notify_request_submitted(
        self, *, excuse: ExcuseRequest, session: Session
    ) -> None:
        """Tell the offering's professors a request is waiting on them.

        Recipients are every currently-effective assignment on the offering, not
        only the professor who opened the session: a co-teacher owns part of the
        class and the request is theirs to action too.
        """

        recipients: list[str] = await self._assigned_professor_emails(
            session.offering_id
        )

        if not recipients:
            return

        student: Student = await self._get_student_or_404(excuse.student_id)
        subject, body = notifications.request_submitted(
            student_name=_full_name(
                student.first_name, student.middle_name, student.last_name
            ),
            course=await self._course_label(session),
            session_date=_session_date(session),
            reason=excuse.reason,
        )
        dispatch_emails(
            [OutboundEmail(to=to, subject=subject, body=body) for to in recipients]
        )

    async def _notify_reviewed(
        self, *, excuse: ExcuseRequest, session: Session
    ) -> None:
        """Tell the student their request was approved or rejected."""

        to: str | None = await self._student_email(excuse.student_id)

        if not to:
            return

        course: str = await self._course_label(session)
        session_date: str = _session_date(session)

        if excuse.status == ExcuseStatus.APPROVED.value:
            subject, body = notifications.request_approved(
                course=course, session_date=session_date
            )
        elif excuse.status == ExcuseStatus.REJECTED.value:
            subject, body = notifications.request_rejected(
                course=course,
                session_date=session_date,
                review_notes=excuse.review_notes,
            )
        else:
            # `ExcuseReviewRequest` admits nothing else today, and this branch
            # only exists so that widening that pattern cannot start reporting
            # a new status to the student as a rejection.
            return

        dispatch_emails([OutboundEmail(to=to, subject=subject, body=body)])

    async def _notify_bulk_excused(
        self, *, session: Session, student_ids: Sequence[int], reason: str
    ) -> None:
        """Tell every student a bulk excuse covered, in one dispatch.

        One batch rather than one call per student: the executor takes the whole
        list off the request and works through it on a single thread.
        """

        addresses: dict[int, str] = await self._student_emails(student_ids)

        if not addresses:
            return

        course: str = await self._course_label(session)
        subject, body = notifications.bulk_excused(
            course=course, session_date=_session_date(session), reason=reason
        )
        dispatch_emails(
            [
                OutboundEmail(to=addresses[student_id], subject=subject, body=body)
                for student_id in dict.fromkeys(student_ids)
                if student_id in addresses
            ]
        )

    async def _assigned_professor_emails(self, offering_id: int) -> list[str]:
        """Effective assignment emails for one offering, deduplicated.

        Same effective-date window as `_require_assignment`, so a professor who
        has been rotated off the offering is not told about its excuses.
        `users.email` wins over `professors.email`: it is the address the person
        signs in with, and the profile column only fills in for an assignment
        whose professor has no linked account.
        """

        today: date = date.today()
        rows: Sequence[str] = (
            await self._session.scalars(
                select(func.coalesce(User.email, Professor.email))
                .select_from(CourseProfessor)
                .join(Professor, Professor.id == CourseProfessor.professor_id)
                .outerjoin(User, User.id == Professor.user_id)
                .where(
                    CourseProfessor.offering_id == offering_id,
                    CourseProfessor.effective_from <= today,
                    or_(
                        CourseProfessor.effective_to.is_(None),
                        CourseProfessor.effective_to >= today,
                    ),
                )
            )
        ).all()

        return list(dict.fromkeys(address for address in rows if address))

    async def _student_email(self, student_id: int) -> str | None:
        addresses: dict[int, str] = await self._student_emails([student_id])

        return addresses.get(student_id)

    async def _student_emails(self, student_ids: Sequence[int]) -> dict[int, str]:
        """Email address per student id, preferring the linked user row.

        `users.email` is the address the student signs in with and so the one
        they read; `students.email` is the official address from the roster and
        covers a student row imported without an account.
        """

        wanted: list[int] = list(dict.fromkeys(student_ids))

        if not wanted:
            return {}

        rows = (
            await self._session.execute(
                select(Student.id, func.coalesce(User.email, Student.email))
                .outerjoin(User, User.id == Student.user_id)
                .where(Student.id.in_(wanted))
            )
        ).all()

        return {student_id: address for student_id, address in rows if address}

    async def _course_label(self, session: Session) -> str:
        """The offering's course code, for the notification subject lines."""

        code: str | None = await self._session.scalar(
            select(Course.course_code)
            .select_from(CourseOffering)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(CourseOffering.id == session.offering_id)
        )

        return code or "your course"

    # -- internals --------------------------------------------------------

    async def _resolve_names(self, excuses: Sequence[ExcuseRequest]) -> None:
        """Resolve the display identity of a page of excuses.

        ONE query per kind for the whole page, not one per row: the student
        names, the session codes, the courses behind them, and the accounts
        that reviewed them. A reference that cannot be resolved is simply
        absent from the maps, and the caller renders it in a labelled id
        form rather than a blank.
        """
        wanted_students = {
            excuse.student_id for excuse in excuses
        } - self._students_by_id.keys()
        wanted_sessions = {
            excuse.session_id for excuse in excuses
        } - self._sessions_by_id.keys()
        wanted_reviewers = {
            excuse.reviewed_by for excuse in excuses if excuse.reviewed_by is not None
        } - self._accounts_by_id.keys()

        if wanted_students:
            self._students_by_id.update(
                {
                    student.id: student
                    for student in (
                        await self._session.scalars(
                            select(Student).where(Student.id.in_(wanted_students))
                        )
                    ).all()
                }
            )

        if wanted_sessions:
            self._sessions_by_id.update(
                {
                    session.id: session
                    for session in (
                        await self._session.scalars(
                            select(Session).where(Session.id.in_(wanted_sessions))
                        )
                    ).all()
                }
            )
            # The course behind a session lives on its offering, so the
            # offerings and their courses are resolved next.
            offering_ids = {
                session.offering_id for session in self._sessions_by_id.values()
            }
            if offering_ids:
                self._offerings_by_id.update(
                    {
                        offering.id: offering
                        for offering in (
                            await self._session.scalars(
                                select(CourseOffering).where(
                                    CourseOffering.id.in_(offering_ids)
                                )
                            )
                        ).all()
                    }
                )
            course_ids = {
                offering.course_id for offering in self._offerings_by_id.values()
            }
            if course_ids:
                self._courses_by_id.update(
                    {
                        course.id: course
                        for course in (
                            await self._session.scalars(
                                select(Course).where(Course.id.in_(course_ids))
                            )
                        ).all()
                    }
                )

        if wanted_reviewers:
            # The reviewer's name is on their student or professor row, so
            # the accounts are outer-joined the way
            # `features/admin/service.py::_users_stmt` does it.
            rows = (
                await self._session.execute(
                    select(
                        User,
                        Student.first_name,
                        Student.last_name,
                        Professor.first_name,
                        Professor.last_name,
                    )
                    .outerjoin(Student, Student.user_id == User.id)
                    .outerjoin(Professor, Professor.user_id == User.id)
                    .where(User.id.in_(wanted_reviewers))
                )
            ).all()
            self._accounts_by_id.update(
                {
                    row[0].id: _Account(
                        id=row[0].id,
                        email=row[0].email,
                        first_name=row[1] or row[3],
                        last_name=row[2] or row[4],
                    )
                    for row in rows
                }
            )

    def _to_read(self, excuse: ExcuseRequest) -> ExcuseRequestRead:
        """One excuse row, with its display identity resolved.

        The caller resolves first — `_resolve_names` is the batched pass, and
        running it per row would turn one query per kind into one per row.
        """
        read = ExcuseRequestRead.model_validate(excuse)

        student = self._students_by_id.get(excuse.student_id)
        if student is not None:
            read.student_name = _full_name(
                student.first_name, student.middle_name, student.last_name
            )
            read.student_number = student.student_id
            read.student_section = student.section or ""
        else:
            read.student_name = f"Student #{excuse.student_id}"
            read.student_number = f"#{excuse.student_id}"

        session = self._sessions_by_id.get(excuse.session_id)
        if session is not None:
            read.session_code = session.session_code
            # The class's date, as the queues date their filters. The session
            # row's `created_at` is the column the session queries filter on
            # (`scheduled_start_time` is a different thing).
            read.session_date = session.created_at.isoformat()
        if not read.session_date:
            read.session_date = excuse.requested_at.isoformat()

        course = self._course_for_session(session)
        if course is not None:
            read.course_code = course.course_code
            read.course_name = course.course_name

        if excuse.reviewed_by is not None:
            account = self._accounts_by_id.get(excuse.reviewed_by)
            read.reviewed_by_name = (
                account.name if account is not None else f"User #{excuse.reviewed_by}"
            )

        return read

    def _course_for_session(self, session: Session | None) -> Course | None:
        """The course behind a session, through its offering."""
        if session is None:
            return None
        offering = self._offerings_by_id.get(session.offering_id)
        if offering is None:
            return None
        return self._courses_by_id.get(offering.course_id)

    async def _paginate(
        self, stmt, *, page: int, size: int
    ) -> PaginatedResponse[ExcuseRequestRead]:
        page, size = normalize_paging(page, size)
        rows, total = await paginate_scalars(
            self._session,
            stmt.order_by(ExcuseRequest.id.desc()),
            page=page,
            size=size,
        )

        await self._resolve_names(rows)

        return PaginatedResponse[ExcuseRequestRead](
            items=[self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def _insert_excuse(
        self,
        *,
        student_id: int,
        session_id: int,
        initiated_by: str,
        initiated_via: str,
        reason: str,
        attachment_urls: list[str] | None,
        status: str,
        reviewed_by: int | None,
        reviewed_at: datetime | None,
        actor_id: int,
    ) -> ExcuseRequest:
        excuse: ExcuseRequest = await self._excuses.create(
            student_id=student_id,
            session_id=session_id,
            initiated_by=initiated_by,
            initiated_via=initiated_via,
            reason=reason,
            attachment_urls=attachment_urls,
            status=status,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )

        # One row per excuse, including inside a bulk run: each is an
        # independently revocable entity with its own id, unlike the students a
        # roster import creates.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.EXCUSE,
            entity_id=excuse.id,
            new_value=self._excuse_snapshot(excuse),
        )

        return excuse

    @staticmethod
    def _excuse_snapshot(excuse: ExcuseRequest) -> dict[str, Any]:
        """The audited columns of an excuse request.

        `reason` is included because it is the substance of the decision, but
        `attachment_urls` is reduced to a count: the URLs point at
        content-addressed objects and the list itself is noise in a trail.
        """
        return {
            "student_id": excuse.student_id,
            "session_id": excuse.session_id,
            "initiated_by": excuse.initiated_by,
            "initiated_via": excuse.initiated_via,
            "reason": excuse.reason,
            "attachment_count": len(excuse.attachment_urls or []),
            "status": excuse.status,
            "reviewed_by": excuse.reviewed_by,
            "review_notes": excuse.review_notes,
        }

    def _apply_excuse(
        self,
        record: Attendance,
        *,
        excuse_id: int,
        reason: str,
        actor_id: int,
        excuse_type: str,
        now: datetime | None = None,
    ) -> str | None:
        """Stamp an approved excuse onto the attendance row."""
        original: str | None = record.validation_status
        stamped: datetime = now or _utcnow()
        record.original_status = record.validation_status
        record.validation_status = ValidationStatus.EXCUSED.value
        record.excuse_reason = reason
        record.excused_by = actor_id
        record.excused_at = stamped
        record.excuse_type = excuse_type
        record.excuse_request_id = excuse_id

        return original

    async def _get_session_or_404(self, session_id: int) -> Session:
        row: Session | None = await self._session.get(Session, session_id)

        if row is None:
            raise SessionNotFoundException(session_id)

        return row

    async def _require_assignment(self, *, offering_id: int, professor_id: int) -> None:
        today: date = date.today()
        row: CourseProfessor | None = (
            await self._session.scalars(
                select(CourseProfessor)
                .where(
                    CourseProfessor.offering_id == offering_id,
                    CourseProfessor.professor_id == professor_id,
                    CourseProfessor.effective_from <= today,
                    or_(
                        CourseProfessor.effective_to.is_(None),
                        CourseProfessor.effective_to >= today,
                    ),
                )
                .order_by(CourseProfessor.effective_from.desc())
                .limit(1)
            )
        ).one_or_none()

        if row is None:
            raise ProfessorNotAssignedException(offering_id)

    async def _resolve_professor(self, user_id: int) -> Professor:
        professor: Professor | None = (
            await self._session.scalars(
                select(Professor).where(Professor.user_id == user_id).limit(1)
            )
        ).one_or_none()

        if professor is None or not professor.is_active:
            raise ProfessorNotFoundException(user_id)

        return professor

    async def _resolve_student(self, user_id: int) -> Student:
        student: Student | None = (
            await self._session.scalars(
                select(Student).where(Student.user_id == user_id).limit(1)
            )
        ).one_or_none()

        if student is None:
            raise StudentNotFoundException(user_id)

        return student

    async def _get_student_or_404(self, student_id: int) -> Student:
        row: Student | None = await self._session.get(Student, student_id)

        if row is None:
            raise StudentNotFoundException(student_id)

        return row

    async def _require_enrollment(self, *, student_id: int, offering_id: int) -> None:
        enrollment: Enrollment | None = (
            await self._session.scalars(
                select(Enrollment)
                .where(
                    Enrollment.student_id == student_id,
                    Enrollment.offering_id == offering_id,
                )
                .limit(1)
            )
        ).one_or_none()

        if enrollment is None:
            raise NotEnrolledException(student_id, offering_id)

    async def _find_attendance(
        self, student_id: int, session_id: int
    ) -> Attendance | None:
        row: Attendance | None = (
            await self._session.scalars(
                select(Attendance)
                .where(
                    Attendance.student_id == student_id,
                    Attendance.session_id == session_id,
                )
                .limit(1)
            )
        ).one_or_none()

        return row

    async def _get_attendance_or_404(
        self, student_id: int, session_id: int
    ) -> Attendance:
        record: Attendance | None = await self._find_attendance(student_id, session_id)

        if record is None:
            raise AttendanceNotFoundException(student_id, session_id)

        return record

    @staticmethod
    def _require_excusable(
        record: Attendance, student_id: int, session_id: int
    ) -> None:
        if record.validation_status == ValidationStatus.EXCUSED.value:
            raise AlreadyExcusedException(student_id, session_id)

        if record.validation_status not in (
            ValidationStatus.ABSENT.value,
            ValidationStatus.LATE.value,
            ValidationStatus.REJECTED.value,
        ):
            raise ExcuseNotEligibleException(student_id, session_id)

    @staticmethod
    def _require_reviewable(
        record: Attendance, student_id: int, session_id: int
    ) -> None:
        if record.validation_status == ValidationStatus.EXCUSED.value:
            raise AlreadyExcusedException(student_id, session_id)

        if record.validation_status not in (
            ValidationStatus.ABSENT.value,
            ValidationStatus.LATE.value,
            ValidationStatus.REJECTED.value,
        ):
            raise ExcuseNotEligibleException(student_id, session_id)

    async def _require_no_open_request(self, student_id: int, session_id: int) -> None:
        existing: ExcuseRequest | None = (
            await self._session.scalars(
                select(ExcuseRequest)
                .where(
                    ExcuseRequest.student_id == student_id,
                    ExcuseRequest.session_id == session_id,
                    ExcuseRequest.status == ExcuseStatus.PENDING.value,
                )
                .limit(1)
            )
        ).one_or_none()

        if existing is not None:
            raise DuplicateExcuseException(student_id, session_id)

    async def _get_excuse_or_404(self, request_id: int) -> ExcuseRequest:
        row: ExcuseRequest | None = await self._excuses.get(request_id)

        if row is None:
            raise ExcuseNotFoundException(request_id)

        return row

    async def _get_professor_excuse(
        self, student_id: int, session_id: int, *, approved_only: bool
    ) -> ExcuseRequest:
        """Resolve the professor-issued excuse a revise or revoke acts on.

        Both routes are scoped to a professor-initiated excuse, and neither is
        keyed by excuse id, so the student and session alone do not identify the
        row: a student can have their own request open against the same session.
        Resolving by recency instead would let a professor revise or revoke the
        student's request, which belongs to them rather than to the professor.

        `approved_only` narrows to the applied state. Every professor-issued
        excuse is approved and stamped as it is filed, so revoke can insist on
        it. Edit does not, so it keeps working if that ever stops holding.
        """
        conditions = [
            ExcuseRequest.student_id == student_id,
            ExcuseRequest.session_id == session_id,
            ExcuseRequest.initiated_by == ExcuseInitiatedBy.PROFESSOR.value,
        ]
        if approved_only:
            conditions.append(ExcuseRequest.status == ExcuseStatus.APPROVED.value)

        row: ExcuseRequest | None = (
            await self._session.scalars(
                select(ExcuseRequest)
                .where(*conditions)
                .order_by(ExcuseRequest.id.desc())
                .limit(1)
            )
        ).one_or_none()

        if row is None:
            raise ExcuseNotFoundException(student_id=student_id, session_id=session_id)

        return row
