from __future__ import annotations

import secrets
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import generate_session_code
from features.attendance.model import Attendance
from features.course.exceptions import (
    OfferingAssignmentNotFoundException,
    OfferingNotFoundException,
    WindowsExceedDurationException,
)
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.program.model import Program, YearLevel
from features.session.exceptions import (
    SessionAlreadyActiveException,
    SessionExpiredException,
    SessionNotFoundException,
)
from features.session.model import Session
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
    SessionRead,
    VerifyCodeResponse,
    VerifyGeofence,
)
from features.student.model import Student
from features.sync.model import SyncQueue
from shared.base import BaseCRUD
from shared.enums import QueueStatus, ValidationStatus
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)
from shared.query import apply_if


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


def _rates(enrolled: int, counts: SessionCounts) -> tuple[float, float]:
    """Compliance (present/total) and participation ((p+l+e)/total) rates."""
    if enrolled <= 0:
        return 0.0, 0.0

    compliance: float = round(counts.present / enrolled, 4)
    participation: float = round(
        (counts.present + counts.late + counts.excused) / enrolled, 4
    )

    return compliance, participation


def _session_status(
    expires_at: datetime | None, now: datetime
) -> Literal["active", "closed"]:
    if expires_at is not None and expires_at > now:
        return "active"

    return "closed"


class SessionService:
    """Professor-owned attendance sessions and their attendance views.

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
        self, *, professor_id: int, payload: SessionCreate
    ) -> SessionRead:
        """Open a new attendance session for an offering.

        Window/classroom fields fall back to the offering defaults and then
        to the application defaults. The session code derives from the
        assigned row id, so the row is written in two flushes: insert with a
        random placeholder, then stamp the code and expiry.
        """
        now: datetime = _utcnow()
        offering: CourseOffering = await self._get_offering_or_404(payload.offering_id)
        await self._require_assignment(
            offering_id=offering.id, professor_id=professor_id
        )
        await self._require_no_active_session(offering_id=offering.id, now=now)

        duration: int = await self._resolve_duration(payload, offering)
        windows: _SessionWindows = self._resolve_windows(payload, offering)
        self._check_windows(windows, duration)

        radius: int = (
            payload.classroom_radius_meters
            or self._settings.default_geofence_radius_meters
        )

        row: Session = await self._insert_session(
            offering=offering,
            professor_id=professor_id,
            payload=payload,
            windows=windows,
            duration=duration,
            radius=radius,
            now=now,
        )
        await self._stamp_session(row, duration, now)

        return SessionRead(
            id=row.id,
            session_code=row.session_code,
            offering_id=offering.id,
            qr_payload=QRPayload(
                code=row.session_code,
                offering=offering.id,
                radius=radius,
                pw=windows.present,
                lw=windows.late,
            ),
            expires_at=row.expires_at,
            scheduled_end_time=row.scheduled_end_time,
            created_at=row.created_at or now,
        )

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

    def _resolve_windows(
        self, payload: SessionCreate, offering: CourseOffering
    ) -> _SessionWindows:
        """Payload -> offering -> app-default fallback for the two scan windows."""
        present: int = (
            payload.present_window_minutes
            or offering.default_present_window_minutes
            or self._settings.default_present_window_minutes
        )
        late: int = (
            payload.late_window_minutes
            or offering.default_late_window_minutes
            or self._settings.default_late_window_minutes
        )

        return _SessionWindows(present=present, late=late)

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
        now: datetime,
    ) -> Session:
        row = Session(
            offering_id=offering.id,
            professor_id=professor_id,
            session_code=secrets.token_hex(16),
            duration_minutes=duration,
            present_window_minutes=windows.present,
            late_window_minutes=windows.late,
            scheduled_start_time=now,
            scheduled_end_time=now + timedelta(minutes=duration),
            expires_at=None,
            classroom_radius_meters=radius,
            classroom_name=payload.classroom_name or offering.classroom_name,
            classroom_lat=_or_fallback(payload.classroom_lat, offering.classroom_lat),
            classroom_lng=_or_fallback(payload.classroom_lng, offering.classroom_lng),
        )
        self._session.add(row)
        await self._session.flush()

        return row

    async def _stamp_session(
        self, row: Session, duration: int, now: datetime
    ) -> None:
        """Second flush: derive the code from the assigned id and stamp expiry."""
        base: datetime = row.created_at or now
        row.expires_at = min(base + timedelta(minutes=duration), row.scheduled_end_time)
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
        self, *, session_id: int, professor_id: int
    ) -> SessionCloseResponse:
        """Manually close session scanning; already-closed closes are no-ops."""
        row: Session = await self._get_scoped_or_404(session_id, professor_id)
        now: datetime = _utcnow()

        if row.expires_at is None or row.expires_at > now:
            row.expires_at = now
            await self._session.flush()

        counts, _ = _summarize(await self._attendance_rows(session_id))

        return SessionCloseResponse(id=row.id, final_counts=counts)

    async def verify_code(self, *, code: str) -> VerifyCodeResponse:
        """Resolve a student-typed/scanned session code to its session config.

        404 when the code matches no session, 410 when the session's window
        has closed (a missing expiry reads as closed, mirroring
        ``_session_status``).
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
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[SessionListItem]:
        page, size = _normalize_page(page, size)
        now: datetime = _utcnow()
        stmt: Select[tuple[Session]] = self._owned_sessions_stmt(
            professor_id,
            offering_id=offering_id,
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

    async def _session_list_item(
        self, row: Session, now: datetime
    ) -> SessionListItem:
        """One list tile: present/late/absent plus the derived session status."""
        counts, scanned = _summarize(await self._attendance_rows(row.id))
        enrolled: int = await self._enrollment_count(row.offering_id)

        return SessionListItem(
            id=row.id,
            offering_id=row.offering_id,
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
        stmt: Select[tuple[Session]] = self._owned_sessions_stmt(
            professor_id,
            offering_id=offering_id,
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
        compliance, participation = _rates(enrolled, counts)

        return SessionHistoryItem(
            id=row.id,
            offering_id=row.offering_id,
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

        return PaginatedResponse[ProfessorAttendanceItem](
            items=self._attendance_items(records, students),
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
        status: ValidationStatus | str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[Attendance]]:
        """Base join for one professor's attendance rows, plus every filter.

        ``CourseOffering`` is joined only when a course filter is present so
        the unfiltered query keeps its original join set.
        """
        stmt: Select[tuple[Attendance]] = (
            select(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(Student, Student.id == Attendance.student_id)
            .where(Session.professor_id == professor_id)
        )

        if course_id is not None:
            stmt = stmt.join(
                CourseOffering, CourseOffering.id == Session.offering_id
            ).where(CourseOffering.course_id == course_id)

        stmt = apply_if(stmt, offering_id, lambda v: Session.offering_id == v)
        stmt = apply_if(stmt, section, lambda v: Student.section == v)
        stmt = apply_if(stmt, session_id, lambda v: Attendance.session_id == v)
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

    @staticmethod
    def _attendance_items(
        records: Sequence[Attendance], students: dict[int, Student]
    ) -> list[ProfessorAttendanceItem]:
        """Project rows onto the table; records with no student are dropped."""
        items: list[ProfessorAttendanceItem] = []

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

    @staticmethod
    def _owned_sessions_stmt(
        professor_id: int,
        *,
        offering_id: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> Select[tuple[Session]]:
        """Sessions owned by one professor, narrowed by the shared filters."""
        stmt: Select[tuple[Session]] = select(Session).where(
            Session.professor_id == professor_id
        )
        stmt = apply_if(stmt, offering_id, lambda v: Session.offering_id == v)
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

    async def _assigned_offering_exists(
        self, offering_id: int, professor_id: int
    ) -> bool:
        """Whether the professor currently holds an assignment for the offering."""
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
                .limit(1)
            )
        ).one_or_none()

        return row is not None

    @staticmethod
    def _assigned_offering_clause(
        offering_id: Any, professor_id: int
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
            raise OfferingAssignmentNotFoundException(offering_id, professor_id)

    async def _resolve_duration(
        self, payload: SessionCreate, offering: CourseOffering
    ) -> int:
        if payload.duration_minutes is not None:
            return payload.duration_minutes

        course: Course | None = await self._session.get(Course, offering.course_id)

        if course is not None:
            return int(float(course.session_duration_hours) * 60)

        # Unreachable against a real database (RESTRICT FK guarantees the
        # course row); only a last resort for incomplete hand-rolled fakes.
        return 60

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
