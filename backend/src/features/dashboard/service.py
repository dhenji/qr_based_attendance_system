"""Cross-feature stat summaries for the three dashboards.

A dashboard is by definition an aggregate over features it does not own — the
student tile needs attendance *and* schedule, the admin tile needs roster
counts *and* analytics *and* the sync backlog. That is why this is its own slice
with three routers rather than a method on `student/`, `professor/` or
`system/`: putting a four-service aggregate inside one of them would make that
feature depend on the other three and blur what it owns.

Two rules this slice follows, both deliberate:

**Compose, don't re-derive.** Every number comes from an existing service
method, so a dashboard can never disagree with the page it sits above. The
student's `compliance_rate` is literally `get_history(...).summary
.compliance_rate`; the admin's `avg_rate` is `AnalyticsService.get_overview()
.avg_compliance_rate`. Where a figure had to be computed locally it is
documented at the call site.

**"Today" means UTC.** `attendance` uses `_utcnow()` and `session`/`reports`
use `date.today()`; a dashboard mixing the two would be off by hours and
disagree with its own components. Everything below anchors to UTC. Note the
consequence: `Attendance.timestamp` and `Session.created_at` are both stored in
UTC, so for a Philippine deployment a class at 7am local is "yesterday" until
midnight UTC. That is pre-existing behaviour across the whole slice list, not
something a dashboard should quietly disagree with.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.analytics.service import AnalyticsService
from features.attendance.model import Attendance
from features.attendance.schema import RecentScanItem
from features.attendance.service import AttendanceService
from features.course_professor.model import CourseProfessor
from features.dashboard.schema import (
    AdminDashboardResponse,
    ProfessorDashboardResponse,
    ProfessorTodaySession,
    RecentActivityEntry,
    StudentDashboardResponse,
    TodayScheduleEntry,
)
from features.enrollment.model import Enrollment
from features.program.model import Program
from features.professor.model import Professor
from features.reports.service import ReportsService
from features.session.model import Session
from features.session.service import SessionService
from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from features.student.schema import ScheduleItem
from features.student.service import StudentService, _meets_on
from shared.enums import ValidationStatus

# How many rows the student feed shows. Matches the recent-scans default so the
# two dashboards agree on what "recent" means.
RECENT_ACTIVITY_LIMIT: int = 10

# How many rows the admin feed shows.
ADMIN_RECENT_SCANS_LIMIT: int = 10


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of `day` in UTC. See the module docstring on "today"."""

    start: datetime = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


class DashboardService:
    """Stat summaries for the three dashboards. Read-only throughout.

    Every method here composes other slices' public service methods and holds no
    business rules of its own; the only SQL is the two counts that no existing
    method returns (`scans_today` per student, and the active roster sizes).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        student_service: StudentService,
        attendance_service: AttendanceService,
        session_service: SessionService,
        analytics_service: AnalyticsService,
        reports_service: ReportsService,
        system_service: Any,
        program_service: Any,
    ) -> None:
        self._session = session
        self._students = student_service
        self._attendance = attendance_service
        self._sessions = session_service
        self._analytics = analytics_service
        self._reports = reports_service
        self._system = system_service
        self._programs = program_service

    # -- student ---------------------------------------------------------

    async def student_dashboard(self, *, user_id: int) -> StudentDashboardResponse:
        """The caller's own numbers. Identity comes from the token, never a param."""
        student: Student = await self._student_by_user(user_id)
        today: date = datetime.now(timezone.utc).date()

        # One call for both the compliance headline and the feed: `get_history`
        # already returns its summary alongside its page, so asking for a
        # 10-row descending slice answers two questions with one query set.
        history = await self._attendance.get_history(
            user_id=user_id,
            sort_by="date",
            sort_dir="desc",
            page=1,
            size=RECENT_ACTIVITY_LIMIT,
        )

        return StudentDashboardResponse(
            compliance_rate=history.summary.compliance_rate,
            scans_today=await self._scans_today(student.id),
            total_scans=await self._total_scans(student.id),
            today_schedule=[
                _to_today_entry(item)
                for item in (await self._students.get_schedule(user_id=user_id)).offerings
                if _meets_on(item.schedule_days, today)
            ],
            recent_activity=[
                RecentActivityEntry(
                    id=item.id,
                    session_id=item.session_id,
                    course_code=item.course_code,
                    course_name=item.course_name,
                    status=ValidationStatus(item.status).value,
                    scanned_at=item.scanned_at.isoformat(),
                )
                for item in history.items
            ],
        )

    # -- professor -------------------------------------------------------

    async def professor_dashboard(
        self, *, professor_id: int
    ) -> ProfessorDashboardResponse:
        now: datetime = datetime.now(timezone.utc)
        tiles = await self._sessions.today_offering_tiles(
            professor_id=professor_id, now=now
        )

        # `avg_rate` is the term-wide compliance figure the professor's reports
        # already compute. `total_students` is the distinct roster across their
        # offerings, which `get_all_courses` does not return directly, so it is
        # counted here over the same offering scope.
        overview = await self._reports.get_all_courses(professor_id=professor_id)

        return ProfessorDashboardResponse(
            sessions_today=len(tiles),
            # A session reads closed once `expires_at` is in the past; sessions
            # carry no status column (SessionService._session_status), and the
            # tile carries it so this needs no second query in a second scope.
            sessions_completed=sum(1 for tile in tiles if tile.status == "closed"),
            total_students=await self._professor_student_count(professor_id),
            avg_rate=overview.avg_compliance,
            today_sessions=[
                ProfessorTodaySession(
                    session_id=tile.session_id,
                    offering_id=tile.offering_id,
                    scanned=tile.scanned,
                    enrolled=tile.enrolled,
                )
                for tile in tiles
            ],
        )

    async def _professor_student_count(self, professor_id: int) -> int:
        """Distinct active students across every offering the professor teaches.

        Counted over the roster rather than over sessions so an enrolled student
        with no session yet still counts — a professor's dashboard should not
        change because a class has not met.
        """

        offering_ids: set[int] = set(
            (
                await self._session.scalars(
                    select(Session.offering_id).where(
                        Session.professor_id == professor_id
                    )
                )
            ).all()
        )
        offering_ids |= set(
            (
                await self._session.scalars(
                    select(CourseProfessor.offering_id).where(
                        CourseProfessor.professor_id == professor_id,
                        CourseProfessor.effective_to.is_(None),
                    )
                )
            ).all()
        )

        if not offering_ids:
            return 0

        return int(
            await self._session.scalar(
                select(func.count(func.distinct(Enrollment.student_id)))
                .join(Student, Student.id == Enrollment.student_id)
                .where(
                    Enrollment.offering_id.in_(offering_ids),
                    Student.is_active.is_(True),
                )
            )
            or 0
        )

    # -- admin -----------------------------------------------------------

    async def admin_dashboard(self) -> AdminDashboardResponse:
        today: date = datetime.now(timezone.utc).date()
        start, end = _utc_day_bounds(today)

        # Roster sizes, not the analytics overview's `total_students`: that one
        # counts students enrolled in a session in scope, and a dashboard that
        # disagreed with the admin list above it would be worse than useless.
        return AdminDashboardResponse(
            student_count=await self._active_count(Student),
            professor_count=await self._active_count(Professor),
            program_count=await self._active_program_count(),
            avg_rate=(await self._analytics.get_overview()).avg_compliance_rate,
            scans_today=int(
                await self._session.scalar(
                    select(func.count(Attendance.id)).where(
                        Attendance.timestamp >= start,
                        Attendance.timestamp < end,
                    )
                )
                or 0
            ),
            pending_sync=await self._system.pending_sync_total(),
            recent_scans=[
                RecentScanItem.model_validate(item)
                for item in (
                    await self._attendance.get_recent_scans(
                        limit=ADMIN_RECENT_SCANS_LIMIT
                    )
                ).items
            ],
        )

    # -- shared counts ---------------------------------------------------

    async def _student_by_user(self, user_id: int) -> Student:
        """The caller's roster row, from the token's user id.

        `get_history` raises `StudentNotFoundException` on its own if the
        account has no roster row, so this only has to produce the primary key
        for the two scan counts.
        """
        student: Student | None = (
            await self._session.scalars(
                select(Student).where(Student.user_id == user_id).limit(1)
            )
        ).one_or_none()

        if student is None:
            raise StudentNotFoundException(user_id)

        return student

    async def _active_count(self, model: Any) -> int:
        return int(
            await self._session.scalar(
                select(func.count(model.id)).where(model.is_active.is_(True))
            )
            or 0
        )

    async def _active_program_count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count(Program.id)).where(Program.is_active.is_(True))
            )
            or 0
        )

    async def _scans_today(self, student_pk: int) -> int:
        """No existing method returns this, and `Attendance.timestamp` is
        unindexed, so this is a sequential scan. Fine for a single student; a
        dashboard-wide `scans_today` in `admin_dashboard` has the same cost and
        is the reason to index the column if these endpoints get hot."""
        start, end = _utc_day_bounds(datetime.now(timezone.utc).date())
        return int(
            await self._session.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.student_id == student_pk,
                    Attendance.timestamp >= start,
                    Attendance.timestamp < end,
                )
            )
            or 0
        )

    async def _total_scans(self, student_pk: int) -> int:
        return int(
            await self._session.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.student_id == student_pk
                )
            )
            or 0
        )


def _to_today_entry(item: ScheduleItem) -> TodayScheduleEntry:
    return TodayScheduleEntry(
        offering_id=item.offering_id,
        course_code=item.course_code,
        course_name=item.course_name,
        schedule_days=item.schedule_days,
        # `ScheduleItem` types these as `time`; the dashboard contract carries
        # them as strings so the payload matches what the schedule endpoint
        # serialises rather than inventing a second time format.
        schedule_start_time=item.schedule_start_time.isoformat(),
        schedule_end_time=item.schedule_end_time.isoformat(),
        classroom_name=item.classroom_name,
        professor_name=item.professor_name,
    )