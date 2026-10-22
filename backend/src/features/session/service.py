from __future__ import annotations

import secrets
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import build_qr_payload, generate_session_code
from core.timezones import resolve_timezone
from features.attendance.model import Attendance
from features.course.exceptions import (
    OfferingNotFoundException,
    WindowsExceedDurationException,
)
from features.excuse.exceptions import ProfessorNotAssignedException
from features.course.model import Course, CourseOffering, OfferingComponent
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.program.model import Program, YearLevel
from features.session.constants import OVERRIDE_PAST_GRACE_MINUTES
from features.session.exceptions import (
    InvalidSessionTimeException,
    ScheduledStartInPastException,
    SessionAlreadyActiveException,
    SessionDateInPastException,
    SessionExpiredException,
    SessionNotFoundException,
    SessionOutsideScheduledTimeException,
    SessionTypeNotConfiguredException,
    LabCoordinatesRequiredException,
    OfferingScheduleMismatchException,
)
from features.session.model import Session
from features.session.plan import (
    SessionPlan,
    active_components,
    resolve_session_plan,
)
from features.session.schema import (
    ActiveStudentItem,
    ProfessorAttendanceItem,
    QRPayload,
    SessionActiveResponse,
    SessionCloseResponse,
    SessionCounts,
    SessionCreate,
    SessionHistoryItem,
    SessionListItem,
    SessionOfferingTile,
    SessionPlanRead,
    SessionRead,
    StartWindowRead,
    VerifyCodeResponse,
    VerifyGeofence,
)
from features.student.model import Student
from features.sync.model import SyncQueue
from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.enums import AuditAction, AuditEntity, QueueStatus, SessionType, ValidationStatus
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)
from shared.query import apply_if
from shared.rates import attendance_rates
from shared.schedule import meeting_minutes, openable_session_types


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_page(page: int, size: int) -> tuple[int, int]:
    return max(page, 1), min(max(size, 1), MAX_PAGE_SIZE)


_STATUS_COUNT_FIELDS: dict[str, str] = {
    ValidationStatus.PRESENT.value: "present",
    ValidationStatus.LATE.value: "late",
    ValidationStatus.PENDING.value: "pending",
    ValidationStatus.ABSENT.value: "absent",
    ValidationStatus.EXCUSED.value: "excused",
}


def _summarize(records: Sequence[Attendance]) -> tuple[SessionCounts, int]:
    """Fold attendance rows into status counts plus the scanned total.

    Rows with a status outside the five tiles (e.g. rejected) still count
    toward the scanned total so the remaining-seats math stays exact.
    """
    tallies: Counter[str] = Counter(record.validation_status for record in records)
    counts = SessionCounts(
        **{
            field: tallies.get(status, 0)
            for status, field in _STATUS_COUNT_FIELDS.items()
        }
    )

    return counts, len(records)


@dataclass(frozen=True)
class _SessionWindows:
    """The two scan windows, resolved payload -> offering -> app default."""

    present: int
    late: int


def _or_fallback[T](chosen: T | None, fallback: T | None) -> T | None:
    """First non-None of two values; `None` overrides are explicit `0` on purpose."""
    return fallback if chosen is None else chosen


def _session_type_of(row: Session) -> SessionType:
    """The row's lecture/lab type, defaulting to lecture when unset.

    Production rows always carry a value (`NOT NULL` + server default); the
    fallback covers hand-rolled fakes that never flush ORM column defaults,
    and any row written before the D77 backfill.
    """
    return SessionType(row.session_type or SessionType.LECTURE.value)


def _session_status(
    expires_at: datetime | None, now: datetime
) -> Literal["active", "closed"]:
    if expires_at is not None and expires_at > now:
        return "active"

    return "closed"


class SessionService:
    """Attendance sessions and the professor-facing views of them.

    ``Session.professor_id`` records who opened a session; it is attribution,
    not authorization. Access is the union of that and a current teaching
    assignment on the session's offering, so a co-teacher is not locked out of a
    session somebody else opened. The column is never rewritten, so history
    stays attributed to whoever opened it.

    Sessions carry no status column: a session reads as active while its
    ``expires_at`` lies in the future and closed otherwise. Closing stamps
    ``expires_at`` with the current time. Only ``flush()`` is used here;
    commit/rollback stays in the request dependency.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._sessions: BaseCRUD[Session] = BaseCRUD(Session, session)
        self._offerings: BaseCRUD[CourseOffering] = BaseCRUD(CourseOffering, session)

    async def create_session(
        self,
        *,
        professor_id: int,
        payload: SessionCreate,
        actor_id: int | None = None,
        now: datetime | None = None,
    ) -> SessionRead:
        """Open a new attendance session for an offering.

        The session inherits the offering's plan (D93): the meeting it
        belongs to, the next occurrence of that meeting, the attendance
        windows, the classroom and the geofence radius. A professor may
        override the scheduled time — and the date — for one session, which is
        recorded on the session and never written back to the offering.

        A session may only be opened while its class is running (D94). The
        plan resolves the open window, and an un-overridden open outside it
        is refused; an explicit override is the professor's way past the
        window, and it carries its own validation.

        The session code derives from the assigned row id, so the row is
        written in two flushes: insert with a random placeholder, then stamp
        the code and expiry.
        """
        moment: datetime = now or _utcnow()
        offering: CourseOffering = await self._get_offering_or_404(payload.offering_id)
        await self._require_assignment(
            offering_id=offering.id, professor_id=professor_id
        )
        await self._require_no_active_session(offering_id=offering.id, now=moment)

        # One read of the offering's active meetings, shared by the
        # weekly-hours gate, the type gate and the session plan.
        components: Sequence[OfferingComponent] = await active_components(
            self._session, offering.id
        )
        await self._require_schedule_requirement(offering, components)

        # D95: the offering declares what it meets. A session of a type it
        # does not configure would inherit the lecture's room and the course
        # template's duration, so it is refused — before the lab-coordinates
        # check, which is about a different mistake.
        self._require_configured_type(
            components=components, session_type=payload.session_type
        )

        course: Course | None = await self._session.get(Course, offering.course_id)
        plan: SessionPlan = await resolve_session_plan(
            self._session,
            offering=offering,
            course=course,
            components=components,
            session_type=payload.session_type,
            now=moment,
            settings=self._settings,
        )

        duration: int = payload.duration_minutes or plan.duration_minutes
        windows: _SessionWindows = _SessionWindows(
            present=payload.present_window_minutes or plan.present_window_minutes,
            late=payload.late_window_minutes or plan.late_window_minutes,
        )
        self._check_windows(windows, duration)

        radius: int = payload.classroom_radius_meters or plan.radius_meters

        # The classroom falls back payload -> matching active component ->
        # offering, which the plan has already resolved.
        classroom_name: str | None = payload.classroom_name or plan.classroom_name
        classroom_lat: float | None = _or_fallback(
            payload.classroom_lat, plan.classroom_lat
        )
        classroom_lng: float | None = _or_fallback(
            payload.classroom_lng, plan.classroom_lng
        )

        # D77: laboratory sessions always enforce the geofence, so a lab open
        # that resolves to no coordinates is rejected.
        if payload.session_type == SessionType.LAB and (
            classroom_lat is None or classroom_lng is None
        ):
            raise LabCoordinatesRequiredException()

        # D94: the class has to be running. An override is the professor's
        # explicit way past the window, so the check applies only when the
        # payload carries none.
        if payload.session_date is None and payload.start_time is None:
            self._require_within_start_window(plan=plan, now=moment)

        scheduled_start, scheduled_end, overridden = self._apply_override(
            plan=plan,
            session_date=payload.session_date,
            start_time=payload.start_time,
            now=moment,
            duration_minutes=duration,
        )

        row: Session = await self._insert_session(
            offering=offering,
            professor_id=professor_id,
            payload=payload,
            windows=windows,
            duration=duration,
            radius=radius,
            classroom_name=classroom_name,
            classroom_lat=classroom_lat,
            classroom_lng=classroom_lng,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            schedule_overridden=overridden,
            original_scheduled_start=self._original_start(
                plan=plan, overridden=overridden
            ),
            now=moment,
            created_by=actor_id,
        )
        await self._stamp_session(row, duration, moment)

        # After the stamp, not before: `session_code` is still the random
        # placeholder until `_stamp_session` derives it from the assigned id.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.OPEN,
            entity_type=AuditEntity.SESSION,
            entity_id=row.id,
            new_value=self._session_snapshot(row),
        )

        # Canonical QR serialization: build_qr_payload owns the versioned
        # compact-key JSON contract ({v,code,offering,radius,pw,lw}); QRPayload
        # validates the same JSON so the contract is exercised on every open.
        qr_json: str = build_qr_payload(
            row.id,
            row.session_code,
            offering.id,
            radius,
            windows.present,
            windows.late,
        )

        return SessionRead(
            id=row.id,
            session_code=row.session_code,
            offering_id=offering.id,
            session_type=_session_type_of(row),
            qr_payload=QRPayload.model_validate_json(qr_json),
            expires_at=row.expires_at,
            scheduled_start_time=row.scheduled_start_time,
            scheduled_end_time=row.scheduled_end_time,
            schedule_overridden=row.schedule_overridden,
            plan_source=plan.source,
            actual_start_time=row.actual_start_time,
            original_scheduled_start_time=row.original_scheduled_start_time,
            override_reason=row.override_reason,
            created_at=row.created_at or moment,
        )

    @staticmethod
    def _require_configured_type(
        *,
        components: Sequence[OfferingComponent],
        session_type: SessionType,
    ) -> None:
        """Refuse a session of a type the offering does not meet (D95).

        The offering's active meetings are what it meets (D77), and the
        list is resolved by the shared helper so the course read, the
        professor's course list, the plan and the open all say the same
        thing. An offering with no active meeting is a lecture offering.
        """
        configured = openable_session_types(
            component.session_type for component in components
        )

        if session_type not in configured:
            raise SessionTypeNotConfiguredException(
                session_type.value, [value.value for value in configured]
            )

    @staticmethod
    def _original_start(*, plan: SessionPlan, overridden: bool) -> datetime | None:
        """The start of the class an overridden session belongs to (D94).

        When today is one of the meeting's days, that class is today's
        occurrence — the one the open window was resolved against, and the
        one the professor meant to run. When today is not one of them there
        is no such class, and the plan's next occurrence is the nearest one.

        Null for a session that follows the plan: there,
        `scheduled_start_time` already is that start.
        """
        if not overridden:
            return None

        return plan.start_window.scheduled_start or plan.scheduled_start

    def _require_within_start_window(self, *, plan: SessionPlan, now: datetime) -> None:
        """Refuse an open that falls outside the class's scheduled time (D94).

        The window is today's occurrence of the meeting plus the early-open
        and late-open grace, resolved by the plan — so this check and the
        plan the professor was shown can never disagree.

        The message names the scheduled time and the current one, because
        the professor's next two options are "wait" and "start at a
        different time".
        """
        window = plan.start_window

        if window.permitted:
            return

        zone = resolve_timezone(
            self._settings.institution_timezone, label="institution timezone"
        )
        current: str = now.astimezone(zone).strftime("%Y-%m-%d %H:%M")
        scheduled: str | None = None

        if window.scheduled_start is not None and window.scheduled_end is not None:
            scheduled = (
                f"{window.scheduled_start.astimezone(zone).strftime('%Y-%m-%d %H:%M')}"
                f"–{window.scheduled_end.astimezone(zone).strftime('%H:%M')}"
            )

        raise SessionOutsideScheduledTimeException(
            reason=window.reason or "after_window",
            scheduled=scheduled,
            current=current,
        )

    def _apply_override(
        self,
        *,
        plan: SessionPlan,
        session_date: date | None,
        start_time: time | None,
        now: datetime,
        duration_minutes: int,
    ) -> tuple[datetime, datetime, bool]:
        """The session's scheduled window, and whether it is an override.

        Without an override the session runs the offering's plan: the next
        occurrence of its meeting, stored on the session so the row keeps the
        class's own start and end rather than the moment of the click.

        With one, the session is an exception. The plan's day or its time is
        replaced, the meeting keeps its length, and the row records that it
        was overridden so nothing downstream mistakes it for the plan.

        The offering's recurring schedule is never touched: an override lives
        on the session alone.
        """
        zone = resolve_timezone(
            self._settings.institution_timezone, label="institution timezone"
        )

        if session_date is None and start_time is None:
            if plan.scheduled_start is not None and plan.scheduled_end is not None:
                return plan.scheduled_start, plan.scheduled_end, False

            # No configured meeting: the session starts now and runs for the
            # resolved duration.
            return now, now + timedelta(minutes=duration_minutes), False

        local_now: datetime = now.astimezone(zone)

        if session_date is not None and session_date < local_now.date():
            raise SessionDateInPastException(session_date.isoformat())

        day: date = session_date or plan.session_date or local_now.date()
        wall: time = start_time or plan.start_time or local_now.time()

        scheduled_start: datetime = datetime.combine(
            day, wall, tzinfo=zone
        ).astimezone(timezone.utc)

        if scheduled_start < now - timedelta(minutes=OVERRIDE_PAST_GRACE_MINUTES):
            raise ScheduledStartInPastException(
                scheduled_start.astimezone(zone).strftime("%Y-%m-%d %H:%M")
            )

        scheduled_end: datetime = scheduled_start + timedelta(
            minutes=duration_minutes
        )

        if scheduled_end <= scheduled_start:
            raise InvalidSessionTimeException()

        return scheduled_start, scheduled_end, True

    async def _require_no_active_session(
        self, *, offering_id: int, now: datetime
    ) -> None:
        active_id: int | None = await self._session.scalar(
            select(Session.id)
            .where(
                Session.offering_id == offering_id,
                Session.expires_at > now,
            )
            .limit(1)
        )

        if active_id is not None:
            raise SessionAlreadyActiveException(offering_id)

    async def _require_schedule_requirement(
        self, offering: CourseOffering, components: Sequence[OfferingComponent]
    ) -> None:
        """Refuse to open sessions on a mis-scheduled offering (D82).

        The merged active-component total must equal the course units
        requirement in whole minutes — the same rule as `_check_weekly_hours`,
        recomputed here so the session feature never imports course-service
        internals. Rows with no configured meetings are exempt (nothing to
        judge: legacy and factory rows keep working). Close/status paths
        never call this.

        `components` are the offering's active meeting rows, read once by
        the caller and shared with the session plan (D93).
        """
        if not components:
            return

        course: Course | None = await self._session.get(Course, offering.course_id)

        if course is None:
            return

        total_minutes = sum(
            meeting_minutes(
                row.schedule_days, row.schedule_start_time, row.schedule_end_time
            )
            for row in components
        )
        limit_minutes = int(course.units) * 60

        if int(round(total_minutes)) != limit_minutes:
            raise OfferingScheduleMismatchException(
                round(total_minutes / 60, 2),
                round(limit_minutes / 60, 2),
                course.course_code,
                int(course.units),
            )

    @staticmethod
    def _check_windows(windows: _SessionWindows, duration: int) -> None:
        if windows.present + windows.late > duration:
            raise WindowsExceedDurationException(
                windows.present, windows.late, duration
            )

    async def _insert_session(
        self,
        *,
        offering: CourseOffering,
        professor_id: int,
        payload: SessionCreate,
        windows: _SessionWindows,
        duration: int,
        radius: int,
        classroom_name: str | None,
        classroom_lat: float | None,
        classroom_lng: float | None,
        scheduled_start: datetime,
        scheduled_end: datetime,
        schedule_overridden: bool,
        original_scheduled_start: datetime | None,
        now: datetime,
        created_by: int | None,
    ) -> Session:
        row = Session(
            offering_id=offering.id,
            professor_id=professor_id,
            session_type=payload.session_type.value,
            session_code=secrets.token_hex(16),
            duration_minutes=duration,
            present_window_minutes=windows.present,
            late_window_minutes=windows.late,
            scheduled_start_time=scheduled_start,
            scheduled_end_time=scheduled_end,
            schedule_overridden=schedule_overridden,
            # D94: when the session was really opened, and — for an override —
            # the start it would have carried without one.
            actual_start_time=now,
            original_scheduled_start_time=original_scheduled_start,
            override_reason=payload.override_reason,
            created_by=created_by,
            expires_at=None,
            classroom_radius_meters=radius,
            classroom_name=classroom_name,
            classroom_lat=classroom_lat,
            classroom_lng=classroom_lng,
        )
        self._session.add(row)
        await self._session.flush()

        return row

    async def _stamp_session(
        self, row: Session, duration: int, now: datetime
    ) -> None:
        """Second flush: derive the code from the assigned id and stamp expiry.

        D49/D12: `expires_at = min(created_at + duration, scheduled_end_time)`.
        The class-end cap only binds while the class is still ahead — a
        professor opening a 09:00-10:30 class at 11:00 would otherwise get a
        session that was born expired, and the "now + duration" reading of the
        cap would leave the scan window with nowhere to run.
        """
        base: datetime = row.created_at or now
        candidate: datetime = base + timedelta(minutes=duration)
        row.expires_at = (
            min(candidate, row.scheduled_end_time)
            if row.scheduled_end_time > base
            else candidate
        )
        row.session_code = generate_session_code(row.id, self._settings)
        await self._session.flush()

    async def get_active_session(
        self, *, session_id: int, professor_id: int
    ) -> SessionActiveResponse:
        """Live session detail for the projector view.

        ``enrolled_count``/``remaining`` feed the stat tiles (remaining is
        enrolled minus every scanned row), ``pending_sync_count`` feeds the
        offline-sync banner, and ``students`` lists every enrolled student
        with their scan status (unscanned reads as absent).
        """
        row: Session = await self._get_scoped_or_404(session_id, professor_id)
        now: datetime = _utcnow()
        students: Sequence[Student] = await self._enrolled_students(row.offering_id)
        records: Sequence[Attendance] = await self._attendance_rows(session_id)
        counts, scanned = _summarize(records)
        enrolled_count: int = len(students)

        return SessionActiveResponse(
            id=row.id,
            offering=row.offering_id,
            session_type=_session_type_of(row),
            session_code=row.session_code,
            scan_window_remaining=self._scan_window_remaining(row, now),
            scheduled_end_time=row.scheduled_end_time,
            status=_session_status(row.expires_at, now),
            enrolled_count=enrolled_count,
            remaining=max(0, enrolled_count - scanned),
            pending_sync_count=await self._pending_sync_count(session_id),
            students=self._active_student_items(students, records),
            counts=counts,
        )

    @staticmethod
    def _scan_window_remaining(row: Session, now: datetime) -> int:
        """Seconds left before the session expires.

        Deliberately seconds: the frontend renders this as a countdown clock,
        and every other duration on the session is stored in whole minutes, so
        converting here would make the projector tile tick in 60s steps. The
        name carries no unit, which is why the schema field documents it.
        """

        if row.expires_at is None:
            return 0

        return max(0, int((row.expires_at - now).total_seconds()))

    @staticmethod
    def _active_student_items(
        students: Sequence[Student], records: Sequence[Attendance]
    ) -> list[ActiveStudentItem]:
        """One tile per enrolled student; unscanned reads as absent."""
        scanned_status: dict[int, ValidationStatus] = {
            r.student_id: ValidationStatus(r.validation_status) for r in records
        }
        scanned_at: dict[int, datetime] = {r.student_id: r.timestamp for r in records}
        excuses: dict[int, str | None] = {
            r.student_id: r.excuse_reason for r in records
        }

        return [
            ActiveStudentItem(
                student_number=student.student_id,
                name=f"{student.first_name} {student.last_name}",
                section=student.section,
                status=scanned_status.get(student.id, ValidationStatus.ABSENT),
                scanned_at=scanned_at.get(student.id),
                excuse_reason=excuses.get(student.id),
            )
            for student in students
        ]

    async def close_session(
        self, *, session_id: int, professor_id: int, actor_id: int | None = None
    ) -> SessionCloseResponse:
        """Manually close session scanning; already-closed closes are no-ops."""
        row: Session = await self._get_scoped_or_404(session_id, professor_id)
        now: datetime = _utcnow()

        if row.expires_at is None or row.expires_at > now:
            old_value: dict[str, Any] = self._session_snapshot(row)
            row.expires_at = now
            await self._session.flush()

            # Inside the guard on purpose: closing an already-closed session
            # changes nothing, so it must not appear in the trail as though it
            # did.
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.CLOSE,
                entity_type=AuditEntity.SESSION,
                entity_id=row.id,
                old_value=old_value,
                new_value=self._session_snapshot(row),
            )

        counts, _ = _summarize(await self._attendance_rows(session_id))

        return SessionCloseResponse(id=row.id, final_counts=counts)

    @staticmethod
    def _session_snapshot(row: Session) -> dict[str, Any]:
        """The audited columns of a session.

        `session_code` is included: it is the value students type in, so it is
        part of what an administrator reviewing a session needs to see.
        `schedule_overridden` is included because a rescheduled session is
        not the offering's plan, and the trail is where that difference has
        to be visible (D93).

        The open-window columns come with it (D94): `actual_start_time` is
        when the session really opened, and `original_scheduled_start_time`
        is the start of the class it belongs to — so the trail shows how far
        the class moved.
        """
        return {
            "offering_id": row.offering_id,
            "professor_id": row.professor_id,
            "session_type": row.session_type,
            "session_code": row.session_code,
            "scheduled_start_time": row.scheduled_start_time.isoformat(),
            "scheduled_end_time": row.scheduled_end_time.isoformat(),
            "schedule_overridden": row.schedule_overridden,
            "actual_start_time": (
                row.actual_start_time.isoformat() if row.actual_start_time else None
            ),
            "original_scheduled_start_time": (
                row.original_scheduled_start_time.isoformat()
                if row.original_scheduled_start_time
                else None
            ),
            "override_reason": row.override_reason,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    async def verify_code(self, *, code: str) -> VerifyCodeResponse:
        """Resolve a student-typed/scanned session code to its session config.

        404 when the code matches no session, 410 when the session's window
        has closed (a missing expiry reads as closed, mirroring
        ``_session_status``).

        NOTE: lookup is by the stored ``session_code`` column, not by
        recomputing ``verify_session_code(code, session_id)`` — the request
        carries the code alone with no session id to verify against.
        ``verify_session_code`` remains the offline/typed-code helper for
        callers that already hold both values.
        """
        row: Session | None = (
            await self._session.scalars(
                select(Session).where(Session.session_code == code.strip()).limit(1)
            )
        ).one_or_none()

        if row is None:
            raise SessionNotFoundException(code)

        now: datetime = _utcnow()

        if row.expires_at is None or row.expires_at <= now:
            raise SessionExpiredException(row.id)

        offering: CourseOffering = await self._get_offering_or_404(row.offering_id)
        course: Course | None = await self._session.get(Course, offering.course_id)
        program: Program | None = await self._session.get(Program, offering.program_id)
        year_level: YearLevel | None = await self._session.get(
            YearLevel, offering.year_level_id
        )

        if course is None or program is None or year_level is None:
            # Unreachable against a real database (RESTRICT FKs); a broken
            # graph reads as unresolvable rather than 500ing on attribute
            # access.
            raise SessionNotFoundException(row.id)

        return VerifyCodeResponse(
            session_id=row.id,
            offering_id=row.offering_id,
            session_type=_session_type_of(row),
            course_code=course.course_code,
            course_name=course.course_name,
            program_code=program.code,
            year_level_label=year_level.label,
            expires_at=row.expires_at,
            scheduled_end_time=row.scheduled_end_time,
            geofence=VerifyGeofence(
                radius=row.classroom_radius_meters,
                lat=row.classroom_lat,
                lng=row.classroom_lng,
            ),
            present_window_minutes=row.present_window_minutes,
            late_window_minutes=row.late_window_minutes,
        )

    async def list_professor_sessions(
        self,
        *,
        professor_id: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offering_id: int | None = None,
        session_type: SessionType | str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[SessionListItem]:
        page, size = _normalize_page(page, size)
        now: datetime = _utcnow()
        stmt: Select[tuple[Session]] = self._sessions_stmt(
            professor_id,
            offering_id=offering_id,
            session_type=session_type,
            date_from=date_from,
            date_to=date_to,
        )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )
        rows: Sequence[Session] = (
            await self._session.scalars(
                stmt.order_by(Session.created_at.desc(), Session.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        items: list[SessionListItem] = []

        for row in rows:
            items.append(await self._session_list_item(row, now))

        return PaginatedResponse[SessionListItem](
            items=items, total=total, page=page, size=size
        )

    async def today_offering_tiles(
        self, *, professor_id: int, now: datetime | None = None
    ) -> list[SessionOfferingTile]:
        """Today's sessions for a professor as (offering, scanned, enrolled).

        Batched on purpose. `list_professor_sessions` builds each tile with two
        queries of its own, which is fine for a paginated list a human reads and
        wrong for a dashboard that wants every one of today's sessions in a
        single round trip — three queries here regardless of how many sessions
        are on.

        "Today" is UTC and anchored on `Session.created_at`, matching the date
        filter every other session query uses. A session that opened yesterday
        and is still live is therefore not counted, which is the same boundary
        `GET /professor/sessions?date_from=...` draws.
        """
        moment: datetime = now or _utcnow()
        start: datetime = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end: datetime = start + timedelta(days=1)

        rows: Sequence[Session] = (
            await self._session.scalars(
                self._sessions_stmt(
                    professor_id,
                    offering_id=None,
                    date_from=start,
                    date_to=end,
                ).order_by(Session.created_at.asc(), Session.id.asc())
            )
        ).all()

        if not rows:
            return []

        session_ids: list[int] = [row.id for row in rows]
        scanned_by_session: dict[int, int] = {
            int(session_id): int(total)
            for session_id, total in (
                await self._session.execute(
                    select(Attendance.session_id, func.count(Attendance.id))
                    .where(Attendance.session_id.in_(session_ids))
                    .group_by(Attendance.session_id)
                )
            ).all()
        }
        enrolled_by_offering: dict[int, int] = {
            int(offering_id): int(total)
            for offering_id, total in (
                await self._session.execute(
                    select(Enrollment.offering_id, func.count(Enrollment.id))
                    .join(Student, Student.id == Enrollment.student_id)
                    .where(
                        Enrollment.offering_id.in_({row.offering_id for row in rows}),
                        Student.is_active.is_(True),
                    )
                    .group_by(Enrollment.offering_id)
                )
            ).all()
        }

        return [
            SessionOfferingTile(
                session_id=row.id,
                offering_id=row.offering_id,
                scanned=scanned_by_session.get(row.id, 0),
                enrolled=enrolled_by_offering.get(row.offering_id, 0),
                status=_session_status(row.expires_at, moment),
            )
            for row in rows
        ]

    async def _session_list_item(
        self, row: Session, now: datetime
    ) -> SessionListItem:
        """One list tile: present/late/absent plus the derived session status."""
        counts, scanned = _summarize(await self._attendance_rows(row.id))
        enrolled: int = await self._enrollment_count(row.offering_id)

        return SessionListItem(
            id=row.id,
            offering_id=row.offering_id,
            session_type=_session_type_of(row),
            session_code=row.session_code,
            created_at=row.created_at,
            expires_at=row.expires_at,
            duration_minutes=row.duration_minutes,
            present_count=counts.present,
            late_count=counts.late,
            absent_count=max(0, enrolled - scanned),
            status=_session_status(row.expires_at, now),
        )

    async def get_session_history(
        self,
        *,
        professor_id: int,
        offering_id: int | None = None,
        section: str | None = None,
        session_type: SessionType | str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[SessionHistoryItem]:
        """Per-session history with present/late/absent counts and both rates.

        Rates use the enrolled total as denominator. Sorting happens in
        Python after the counts are computed so the rate sort stays exact;
        session volumes per professor are small enough for this.
        """
        page, size = _normalize_page(page, size)
        now: datetime = _utcnow()
        stmt: Select[tuple[Session]] = self._sessions_stmt(
            professor_id,
            offering_id=offering_id,
            session_type=session_type,
            date_from=date_from,
            date_to=date_to,
        )

        rows: Sequence[Session] = (
            await self._session.scalars(stmt.order_by(Session.id.asc()))
        ).all()

        items: list[SessionHistoryItem] = []

        for row in rows:
            if not await self._matches_section(row.offering_id, section):
                continue

            items.append(await self._session_history_item(row, now))

        items.sort(key=_history_key(sort_by), reverse=_desc(sort_dir))
        total: int = len(items)
        window: list[SessionHistoryItem] = items[(page - 1) * size : page * size]

        return PaginatedResponse[SessionHistoryItem](
            items=window, total=total, page=page, size=size
        )

    async def _session_history_item(
        self, row: Session, now: datetime
    ) -> SessionHistoryItem:
        """One history row: counts plus the compliance/participation rates."""
        counts, scanned = _summarize(await self._attendance_rows(row.id))
        enrolled: int = await self._enrollment_count(row.offering_id)
        compliance, participation = attendance_rates(
            present=counts.present,
            late=counts.late,
            excused=counts.excused,
            enrolled=enrolled,
        )

        return SessionHistoryItem(
            id=row.id,
            offering_id=row.offering_id,
            session_type=_session_type_of(row),
            session_code=row.session_code,
            created_at=row.created_at,
            expires_at=row.expires_at,
            duration_minutes=row.duration_minutes,
            present_count=counts.present,
            late_count=counts.late,
            absent_count=max(0, enrolled - scanned),
            status=_session_status(row.expires_at, now),
            compliance_rate=compliance,
            participation_rate=participation,
        )

    async def _matches_section(self, offering_id: int, section: str | None) -> bool:
        """No section filter, or the offering has a student in that section."""
        if section is None:
            return True

        return section in await self._offering_sections(offering_id)

    async def get_professor_attendance(
        self,
        *,
        professor_id: int,
        course_id: int | None = None,
        offering_id: int | None = None,
        section: str | None = None,
        session_id: int | None = None,
        session_type: SessionType | str | None = None,
        status: ValidationStatus | str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[ProfessorAttendanceItem]:
        """Filterable attendance table across the professor's sessions.

        ``section`` is derived from the enrolled student's section (offerings
        carry no section column). Sortable columns mirror the table headers:
        date, student, section, status, time.
        """
        page, size = _normalize_page(page, size)
        stmt: Select[tuple[Attendance]] = self._attendance_stmt(
            professor_id,
            course_id=course_id,
            offering_id=offering_id,
            section=section,
            session_id=session_id,
            session_type=session_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )
        records: Sequence[Attendance] = (
            await self._session.scalars(
                _apply_attendance_order(stmt, sort_by=sort_by, sort_dir=sort_dir)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        students: dict[int, Student] = await self._load_students(
            {r.student_id for r in records}
        )
        session_types: dict[int, SessionType] = await self._load_session_types(
            {r.session_id for r in records}
        )

        return PaginatedResponse[ProfessorAttendanceItem](
            items=self._attendance_items(records, students, session_types),
            total=total,
            page=page,
            size=size,
        )

    def _attendance_stmt(
        self,
        professor_id: int,
        *,
        course_id: int | None,
        offering_id: int | None,
        section: str | None,
        session_id: int | None,
        session_type: SessionType | str | None,
        status: ValidationStatus | str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[Attendance]]:
        """Base join for one professor's attendance rows, plus every filter.

        ``CourseOffering`` is joined only when a course filter is present so
        the unfiltered query keeps its original join set. Scope is the same union
        as ``_sessions_stmt`` - opened or assigned - and the two have to widen
        together: the ledger is read alongside a session directory built from
        ``_sessions_stmt``, so a mismatch leaves rows with nothing to join to.
        """
        stmt: Select[tuple[Attendance]] = (
            select(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(Student, Student.id == Attendance.student_id)
            .where(
                or_(
                    Session.professor_id == professor_id,
                    self._assigned_offering_clause(Session.offering_id, professor_id),
                )
            )
        )

        if course_id is not None:
            stmt = stmt.join(
                CourseOffering, CourseOffering.id == Session.offering_id
            ).where(CourseOffering.course_id == course_id)

        stmt = apply_if(stmt, offering_id, lambda v: Session.offering_id == v)
        stmt = apply_if(stmt, section, lambda v: Student.section == v)
        stmt = apply_if(stmt, session_id, lambda v: Attendance.session_id == v)
        if session_type is not None:
            value: str = (
                session_type.value
                if isinstance(session_type, SessionType)
                else str(session_type)
            )
            stmt = stmt.where(Session.session_type == value)
        stmt = apply_if(stmt, status, lambda v: Attendance.validation_status == v)
        stmt = apply_if(stmt, date_from, lambda v: Attendance.timestamp >= v)
        stmt = apply_if(stmt, date_to, lambda v: Attendance.timestamp <= v)

        return stmt

    async def _load_students(self, student_ids: set[int]) -> dict[int, Student]:
        if not student_ids:
            return {}

        rows: Sequence[Student] = (
            await self._session.scalars(
                select(Student).where(Student.id.in_(student_ids))
            )
        ).all()

        return {s.id: s for s in rows}

    async def _load_session_types(
        self, session_ids: set[int]
    ) -> dict[int, SessionType]:
        if not session_ids:
            return {}

        rows: Sequence[Session] = (
            await self._session.scalars(
                select(Session).where(Session.id.in_(session_ids))
            )
        ).all()

        return {s.id: _session_type_of(s) for s in rows}

    @staticmethod
    def _attendance_items(
        records: Sequence[Attendance],
        students: dict[int, Student],
        session_types: dict[int, SessionType] | None = None,
    ) -> list[ProfessorAttendanceItem]:
        """Project rows onto the table; records with no student are dropped."""
        items: list[ProfessorAttendanceItem] = []
        types: dict[int, SessionType] = session_types or {}

        for record in records:
            student: Student | None = students.get(record.student_id)

            if student is None:
                continue

            items.append(
                ProfessorAttendanceItem(
                    id=record.id,
                    student_number=student.student_id,
                    student_name=f"{student.first_name} {student.last_name}",
                    section=student.section,
                    session_id=record.session_id,
                    session_type=types.get(record.session_id, SessionType.LECTURE),
                    status=ValidationStatus(record.validation_status),
                    original_status=(
                        ValidationStatus(record.original_status)
                        if record.original_status is not None
                        else None
                    ),
                    scanned_at=record.timestamp,
                    scanned_via=record.scanned_via,
                    face_match_score=(
                        float(record.face_match_score)
                        if record.face_match_score is not None
                        else None
                    ),
                )
            )

        return items

    # -- internals --------------------------------------------------------

    def _sessions_stmt(
        self,
        professor_id: int,
        *,
        offering_id: int | None,
        session_type: SessionType | str | None = None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[Session]]:
        """Sessions the professor opened, or is assigned to teach.

        A union rather than a replacement. The assignment window is anchored to
        today, so scoping on assignment alone would take a professor's own past
        sessions out of reach the day that assignment's `effective_to` passes.
        """
        stmt: Select[tuple[Session]] = select(Session).where(
            or_(
                Session.professor_id == professor_id,
                self._assigned_offering_clause(Session.offering_id, professor_id),
            )
        )
        stmt = apply_if(stmt, offering_id, lambda v: Session.offering_id == v)
        if session_type is not None:
            value: str = (
                session_type.value
                if isinstance(session_type, SessionType)
                else str(session_type)
            )
            stmt = stmt.where(Session.session_type == value)
        stmt = apply_if(stmt, date_from, lambda v: Session.created_at >= v)
        stmt = apply_if(stmt, date_to, lambda v: Session.created_at <= v)

        return stmt

    async def _get_offering_or_404(self, offering_id: int) -> CourseOffering:
        offering: CourseOffering | None = await self._offerings.get(offering_id)

        if offering is None:
            raise OfferingNotFoundException(offering_id)

        return offering

    async def _get_scoped_or_404(
        self, session_id: int, professor_id: int
    ) -> Session:
        """Resolve a session the professor may act on.

        `Session.professor_id` records who opened the session and nothing more,
        so a co-teacher is not excluded from one merely because somebody else
        opened it. Ownership is checked first and the assignment is only looked
        up when it fails, which keeps the common case to a single row fetch.

        `session.professor_id` is never written here: attribution stays with
        whoever opened the session even though access does not.
        """
        row: Session | None = await self._sessions.get(session_id)

        if row is None:
            raise SessionNotFoundException(session_id)

        if row.professor_id != professor_id:
            await self._require_assignment(
                offering_id=row.offering_id, professor_id=professor_id
            )

        return row

    @staticmethod
    def _assigned_offering_clause(
        offering_id: ColumnElement[int], professor_id: int
    ) -> ColumnElement[bool]:
        """`EXISTS` an effective assignment for this offering and professor.

        A subquery rather than a join so a professor holding several assignments
        on one offering repeats no rows, and built inline so the calling
        statement stays a single query. The assignment window is anchored to
        today, so this must only ever widen a scope - never replace ownership
        with it, or a professor loses sight of their own past sessions once an
        assignment's `effective_to` passes.
        """
        today: date = date.today()

        return (
            select(CourseProfessor.offering_id)
            .where(
                CourseProfessor.offering_id == offering_id,
                CourseProfessor.professor_id == professor_id,
                CourseProfessor.effective_from <= today,
                or_(
                    CourseProfessor.effective_to.is_(None),
                    CourseProfessor.effective_to >= today,
                ),
            )
            .exists()
        )

    async def _require_assignment(self, *, offering_id: int, professor_id: int) -> None:
        """Require a current teaching assignment; 403 when outside the team.

        Unified with the excuse slice (`not_assigned`): an authenticated
        professor without an effective `course_professors` row is forbidden,
        not lost — 404 would conflate "no such session" with "not your
        course". The admin remove path (`course/service.py`) keeps its 404
        (nothing to remove), which answers a different question.
        """
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

    async def get_session_plan(
        self,
        *,
        offering_id: int,
        professor_id: int,
        session_type: SessionType,
        now: datetime | None = None,
    ) -> SessionPlanRead:
        """The resolved plan a session for this offering would inherit (D93).

        The open form renders this instead of re-deriving the schedule, so
        what the professor sees is what the server will store. Authorization
        is the same rule the open itself uses: a current teaching assignment
        on the offering.

        A type the offering does not meet is refused with the same error the
        open would raise (D95): a plan for it would be a plan the professor
        may not use, and a stale form has to learn that.
        """
        moment: datetime = now or _utcnow()
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        await self._require_assignment(
            offering_id=offering.id, professor_id=professor_id
        )

        components: Sequence[OfferingComponent] = await active_components(
            self._session, offering.id
        )
        self._require_configured_type(
            components=components, session_type=session_type
        )

        course: Course | None = await self._session.get(Course, offering.course_id)
        plan: SessionPlan = await resolve_session_plan(
            self._session,
            offering=offering,
            course=course,
            components=components,
            session_type=session_type,
            now=moment,
            settings=self._settings,
        )

        return SessionPlanRead(
            offering_id=offering.id,
            session_type=session_type,
            source=plan.source,
            session_date=plan.session_date,
            start_time=plan.start_time,
            end_time=plan.end_time,
            scheduled_start=plan.scheduled_start,
            scheduled_end=plan.scheduled_end,
            timezone=self._settings.institution_timezone,
            duration_minutes=plan.duration_minutes,
            present_window_minutes=plan.present_window_minutes,
            late_window_minutes=plan.late_window_minutes,
            classroom_name=plan.classroom_name,
            classroom_lat=plan.classroom_lat,
            classroom_lng=plan.classroom_lng,
            radius_meters=plan.radius_meters,
            override_capable=plan.has_meeting,
            # D94: whether the session may be opened right now, and why not.
            # The open form renders this instead of re-deriving the window.
            start_window=StartWindowRead(
                permitted=plan.start_window.permitted,
                reason=plan.start_window.reason,
                scheduled_date=plan.start_window.session_date,
                start_time=plan.start_window.start_time,
                end_time=plan.start_window.end_time,
                scheduled_start=plan.start_window.scheduled_start,
                scheduled_end=plan.start_window.scheduled_end,
                opens_at=plan.start_window.opens_at,
                closes_at=plan.start_window.closes_at,
                current_time=moment,
                timezone=self._settings.institution_timezone,
                early_open_minutes=plan.start_window.early_open_minutes,
                late_open_minutes=plan.start_window.late_open_minutes,
            ),
        )

    async def _enrolled_students(self, offering_id: int) -> Sequence[Student]:
        return (
            await self._session.scalars(
                select(Student)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .where(
                    Enrollment.offering_id == offering_id,
                    Student.is_active.is_(True),
                )
                .order_by(
                    Student.last_name.asc(),
                    Student.first_name.asc(),
                    Student.id.asc(),
                )
            )
        ).all()

    async def _enrollment_count(self, offering_id: int) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Enrollment)
                .join(Student, Student.id == Enrollment.student_id)
                .where(
                    Enrollment.offering_id == offering_id,
                    Student.is_active.is_(True),
                )
            )
            or 0
        )

    async def _offering_sections(self, offering_id: int) -> set[str]:
        sections: Sequence[str | None] = (
            await self._session.scalars(
                select(Student.section)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .where(
                    Enrollment.offering_id == offering_id,
                    Student.is_active.is_(True),
                )
            )
        ).all()

        return {section for section in sections if section}

    async def _attendance_rows(self, session_id: int) -> Sequence[Attendance]:
        return (
            await self._session.scalars(
                select(Attendance)
                .where(Attendance.session_id == session_id)
                .order_by(Attendance.timestamp.asc(), Attendance.id.asc())
            )
        ).all()

    async def _pending_sync_count(self, session_id: int) -> int:
        """Pending offline-sync rows queued for this session.

        ``sync_queue`` has no session FK, so the session link lives inside
        ``record_data``; the pending backlog is small enough to filter here.
        """
        rows: Sequence[SyncQueue] = (
            await self._session.scalars(
                select(SyncQueue).where(SyncQueue.status == QueueStatus.PENDING.value)
            )
        ).all()
        wanted: str = str(session_id)

        return sum(
            1
            for row in rows
            if isinstance(row.record_data, dict)
            and str(row.record_data.get("session_id")) == wanted
        )


def _desc(sort_dir: str | None) -> bool:
    return (sort_dir or "desc").lower() != "asc"


_HISTORY_KEYS: dict[str, Callable[[SessionHistoryItem], Any]] = {
    "code": lambda item: item.session_code,
    "present": lambda item: item.present_count,
    "late": lambda item: item.late_count,
    "absent": lambda item: item.absent_count,
    "rate": lambda item: item.compliance_rate,
    "date": lambda item: (item.created_at, item.id),
}


def _history_key(sort_by: str | None) -> Callable[[SessionHistoryItem], Any]:
    return _HISTORY_KEYS.get(sort_by or "date", _HISTORY_KEYS["date"])


_ATTENDANCE_SORT_COLUMNS: dict[str, tuple[Any, ...]] = {
    "date": (Session.created_at,),
    "student": (Student.last_name, Student.first_name),
    "section": (Student.section,),
    "status": (Attendance.validation_status,),
    "time": (Attendance.timestamp,),
}


def _apply_attendance_order(
    stmt: Select[tuple[Attendance]], *, sort_by: str | None, sort_dir: str | None
) -> Select[tuple[Attendance]]:
    desc: bool = _desc(sort_dir)
    columns: tuple[Any, ...] = _ATTENDANCE_SORT_COLUMNS.get(
        sort_by or "time", (Attendance.timestamp,)
    )
    ordered = [col.desc() if desc else col.asc() for col in columns]
    tie = Attendance.id.desc() if desc else Attendance.id.asc()

    return stmt.order_by(*ordered, tie)
