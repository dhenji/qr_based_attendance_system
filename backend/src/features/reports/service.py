from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.assignments import active_assignment_clause
from shared.cohorts import CohortKey, group_by_cohort
from shared.datetimes import end_of_day, ensure_aware
from shared.enums import ValidationStatus
from shared.exceptions import PdfExportUnavailableException
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, normalize_paging
from shared.query import apply_if
from shared.rates import attendance_rates

from features.analytics.schema import TrendGranularity
from features.attendance.model import Attendance
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.program.model import Program, YearLevel
from features.reports.schema import (
    DEFAULT_EXPORT_INCLUDE,
    AllCoursesItem,
    AllCoursesResponse,
    ReportMetric,
    ReportsComparisonItem,
    ReportsComparisonResponse,
    ReportsTrendItem,
    ReportsTrendResponse,
)
from features.session.model import Session
from features.session.service import SessionService
from features.student.model import Student


def _bucket_key(moment: datetime, granularity: TrendGranularity) -> date:
    day: date = ensure_aware(moment).date()

    match granularity:
        case "daily":
            return day
        case "weekly":
            return date.fromordinal(day.toordinal() - day.weekday())
        case _:
            return day.replace(day=1)


def _pick_rate(compliance: float, participation: float, metric: ReportMetric) -> float:
    match metric:
        case "participation":
            return participation
        case _:
            return compliance


class ReportsService:
    """Professor-scoped attendance aggregates over the assignment union.

    Scope is sessions the professor opened plus offerings they are currently
    assigned to — the same union the session ledger reads, so the on-screen
    rows and these aggregates never disagree about whose sessions they show.
    Read-only; the transaction boundary stays in the request dependency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_courses(
        self,
        *,
        professor_id: int,
        granularity: TrendGranularity = "daily",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        session_type: str | None = None,
    ) -> AllCoursesResponse:
        """Bucketed totals across every offering in the professor's union."""
        offerings: Sequence[CourseOffering] = await self._scoped_offerings(
            professor_id, None, None, None
        )
        offering_ids: list[int] = [row.id for row in offerings]
        sessions: Sequence[Session] = await self._sessions_in(
            offering_ids, date_from, date_to, session_type
        )
        enrolled_by_offering = await self._enrolled_by_offering(offering_ids)
        buckets, bucket_tallies = await self._bucketed(
            sessions, granularity, date_from, date_to
        )
        items: list[AllCoursesItem] = []

        for key in sorted(set(buckets) | set(bucket_tallies)):
            bucket: list[Session] = buckets.get(key, [])
            tally: Counter[str] = bucket_tallies.get(key, Counter())
            expected: int = _expected_for(bucket, enrolled_by_offering)
            compliance, participation = attendance_rates(
                present=tally.get(ValidationStatus.PRESENT.value, 0),
                late=tally.get(ValidationStatus.LATE.value, 0),
                excused=tally.get(ValidationStatus.EXCUSED.value, 0),
                enrolled=expected,
            )
            items.append(
                AllCoursesItem(
                    date=key,
                    total_sessions=len(bucket),
                    total_students=len(
                        {
                            student
                            for row in bucket
                            for student in enrolled_by_offering.get(
                                row.offering_id, set()
                            )
                        }
                    ),
                    compliance_rate=compliance,
                    participation_rate=participation,
                )
            )

        expected_all: int = _expected_for(sessions, enrolled_by_offering)
        tallies_all: Counter[str] = await self._tallies([row.id for row in sessions])
        avg_compliance, avg_participation = attendance_rates(
            present=tallies_all.get(ValidationStatus.PRESENT.value, 0),
            late=tallies_all.get(ValidationStatus.LATE.value, 0),
            excused=tallies_all.get(ValidationStatus.EXCUSED.value, 0),
            enrolled=expected_all,
        )

        return AllCoursesResponse(
            items=items,
            avg_compliance=avg_compliance,
            avg_participation=avg_participation,
        )

    async def get_comparison(
        self,
        *,
        professor_id: int,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        session_type: str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> ReportsComparisonResponse:
        """Cohort rates over the union; one row per program × year level.

        One row per (course, program, year level) so the same subject across
        cohorts is comparable (D6/D34); semester/program/year stay filters.
        Each row carries its own program code and year-level label so the
        client never has to guess a cohort from a course id.
        """
        page, size = normalize_paging(page, size)
        offerings: Sequence[CourseOffering] = await self._scoped_offerings(
            professor_id, program_id, year_level_id, semester
        )

        if not offerings:
            return ReportsComparisonResponse(items=[], total=0, page=page, size=size)

        cohorts: dict[CohortKey, list[CourseOffering]] = group_by_cohort(offerings)
        course_map: dict[int, Course] = await self._course_map(
            sorted({key[0] for key in cohorts})
        )
        program_map: dict[int, Program] = await self._program_map(
            sorted({key[1] for key in cohorts})
        )
        year_level_map: dict[int, YearLevel] = await self._year_level_map(
            sorted({key[2] for key in cohorts})
        )
        enrolled_by_offering = await self._enrolled_by_offering(
            [row.id for row in offerings]
        )
        items: list[ReportsComparisonItem] = []

        for key in sorted(
            cohorts,
            key=lambda key: (
                course_map[key[0]].course_code if key[0] in course_map else "",
                key[1],
                key[2],
            ),
        ):
            course_id, cohort_program_id, cohort_year_level_id = key
            rows: list[CourseOffering] = cohorts[key]
            offering_ids: list[int] = [row.id for row in rows]
            sessions: Sequence[Session] = await self._sessions_in(
                offering_ids, date_from, date_to, session_type
            )
            tallies: Counter[str] = await self._tallies([row.id for row in sessions])
            compliance, participation = attendance_rates(
                present=tallies.get(ValidationStatus.PRESENT.value, 0),
                late=tallies.get(ValidationStatus.LATE.value, 0),
                excused=tallies.get(ValidationStatus.EXCUSED.value, 0),
                enrolled=_expected_for(sessions, enrolled_by_offering),
            )
            course: Course | None = course_map.get(course_id)
            program: Program | None = program_map.get(cohort_program_id)
            year_level: YearLevel | None = year_level_map.get(cohort_year_level_id)
            items.append(
                ReportsComparisonItem(
                    course_id=course_id,
                    course_code=course.course_code if course else "",
                    program_id=cohort_program_id,
                    year_level_id=cohort_year_level_id,
                    program_code=program.code if program else "",
                    year_level_label=year_level.label if year_level else "",
                    compliance_rate=compliance,
                    participation_rate=participation,
                    total_sessions=len(sessions),
                )
            )

        return ReportsComparisonResponse(
            items=items[(page - 1) * size : page * size],
            total=len(items),
            page=page,
            size=size,
        )

    async def get_trends(
        self,
        *,
        professor_id: int,
        course_ids: Sequence[int] | None = None,
        metric: ReportMetric = "compliance",
        granularity: TrendGranularity = "daily",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        session_type: str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> ReportsTrendResponse:
        """One rate series per course, bucketed by the chosen granularity."""
        page, size = normalize_paging(page, size)
        offerings: Sequence[CourseOffering] = await self._scoped_offerings(
            professor_id, None, None, None, course_ids
        )

        if not offerings:
            return ReportsTrendResponse(items=[], total=0, page=page, size=size)

        by_course: dict[int, list[CourseOffering]] = {}

        for row in sorted(offerings, key=lambda item: item.id):
            by_course.setdefault(row.course_id, []).append(row)

        course_map: dict[int, Course] = await self._course_map(sorted(by_course))
        enrolled_by_offering = await self._enrolled_by_offering(
            [row.id for row in offerings]
        )
        items: list[ReportsTrendItem] = []

        for course_id in sorted(by_course):
            rows: list[CourseOffering] = by_course[course_id]
            offering_ids: list[int] = [row.id for row in rows]
            sessions: Sequence[Session] = await self._sessions_in(
                offering_ids, date_from, date_to, session_type
            )
            buckets, bucket_tallies = await self._bucketed(
                sessions, granularity, date_from, date_to
            )
            course: Course | None = course_map.get(course_id)

            for key in sorted(set(buckets) | set(bucket_tallies)):
                bucket: list[Session] = buckets.get(key, [])
                tally: Counter[str] = bucket_tallies.get(key, Counter())
                compliance, participation = attendance_rates(
                    present=tally.get(ValidationStatus.PRESENT.value, 0),
                    late=tally.get(ValidationStatus.LATE.value, 0),
                    excused=tally.get(ValidationStatus.EXCUSED.value, 0),
                    enrolled=_expected_for(bucket, enrolled_by_offering),
                )
                items.append(
                    ReportsTrendItem(
                        date=key,
                        course_id=course_id,
                        course_code=course.course_code if course else "",
                        rate=_pick_rate(compliance, participation, metric),
                    )
                )

        ordered: list[ReportsTrendItem] = sorted(
            items, key=lambda item: (item.date, item.course_id)
        )

        return ReportsTrendResponse(
            items=ordered[(page - 1) * size : page * size],
            total=len(ordered),
            page=page,
            size=size,
        )

    async def export_attendance(
        self,
        *,
        professor_id: int,
        course_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        format: str = "csv",
        include: Sequence[str] | None = None,
        statuses: Sequence[ValidationStatus | str] | None = None,
        session_type: str | None = None,
    ) -> str:
        """Per-scan rows for the professor's union rendered as CSV text.

        Scope is sessions the professor opened or is currently assigned to —
        the same row-level union the session ledger reads, so the download
        never disagrees with the on-screen table. Only CSV is built here:
        no PDF writer is installed, so `pdf` is a 422 rather than a
        silently dropped option. Generation and file persistence stay
        separate — this returns text, the router streams it.
        """
        if format != "csv":
            raise PdfExportUnavailableException()

        wanted: set[str] = (
            set(include) if include is not None else set(DEFAULT_EXPORT_INCLUDE)
        )
        stmt = (
            select(Attendance)
            .join(Session, Session.id == Attendance.session_id)
            .join(Student, Student.id == Attendance.student_id)
            .where(
                or_(
                    Session.professor_id == professor_id,
                    SessionService._assigned_offering_clause(
                        Session.offering_id, professor_id
                    ),
                )
            )
        )

        if course_id is not None:
            stmt = stmt.join(
                CourseOffering, CourseOffering.id == Session.offering_id
            ).where(CourseOffering.course_id == course_id)

        date_from = ensure_aware(date_from) if date_from is not None else None
        date_to = end_of_day(ensure_aware(date_to)) if date_to is not None else None

        stmt = apply_if(stmt, date_from, lambda v: Attendance.timestamp >= v)
        stmt = apply_if(stmt, date_to, lambda v: Attendance.timestamp <= v)
        stmt = apply_if(stmt, session_type, lambda v: Session.session_type == v)

        if statuses:
            stmt = stmt.where(
                Attendance.validation_status.in_(
                    [
                        s.value if isinstance(s, ValidationStatus) else str(s)
                        for s in statuses
                    ]
                )
            )

        records: Sequence[Attendance] = (
            await self._session.scalars(
                stmt.order_by(Attendance.timestamp.asc(), Attendance.id.asc())
            )
        ).all()
        students: dict[int, Student] = await self._students_by_id(
            {row.student_id for row in records}
        )
        session_types: dict[int, str] = {}
        if records:
            rows: Sequence[tuple[int, str]] = (
                await self._session.execute(
                    select(Session.id, Session.session_type).where(
                        Session.id.in_({row.session_id for row in records})
                    )
                )
            ).all()  # type: ignore[assignment]
            session_types = {sid: st for sid, st in rows}

        header: list[str] = ["session_id", "session_type"]

        if "student_id" in wanted:
            header.append("student_id")

        if "name" in wanted:
            header.append("name")

        if "timestamp" in wanted:
            header.append("timestamp")

        if "gps" in wanted:
            header.extend(["gps_lat", "gps_lng"])

        if "liveness" in wanted:
            header.append("face_match_score")

        header.append("status")

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)

        for record in records:
            student: Student | None = students.get(record.student_id)

            if student is None:
                continue

            row: list[Any] = [
                record.session_id,
                session_types.get(record.session_id, ""),
            ]

            if "student_id" in wanted:
                row.append(student.student_id)

            if "name" in wanted:
                row.append(f"{student.first_name} {student.last_name}")

            if "timestamp" in wanted:
                row.append(
                    record.timestamp.isoformat() if record.timestamp is not None else ""
                )

            if "gps" in wanted:
                row.extend(
                    [
                        record.gps_lat if record.gps_lat is not None else "",
                        record.gps_lng if record.gps_lng is not None else "",
                    ]
                )

            if "liveness" in wanted:
                row.append(
                    float(record.face_match_score)
                    if record.face_match_score is not None
                    else ""
                )

            row.append(record.validation_status)
            writer.writerow(row)

        return buffer.getvalue()

    async def _students_by_id(self, student_ids: set[int]) -> dict[int, Student]:
        if not student_ids:
            return {}

        rows: Sequence[Student] = (
            await self._session.scalars(
                select(Student).where(Student.id.in_(student_ids))
            )
        ).all()

        return {row.id: row for row in rows}

    async def _scoped_offerings(
        self,
        professor_id: int,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_ids: Sequence[int] | None = None,
    ) -> Sequence[CourseOffering]:
        """Union offerings narrowed by the optional slicing filters."""
        union_ids: list[int] = await self._union_offering_ids(professor_id)

        if not union_ids:
            return []

        stmt = select(CourseOffering).where(CourseOffering.id.in_(union_ids))
        stmt = apply_if(stmt, program_id, lambda v: CourseOffering.program_id == v)
        stmt = apply_if(
            stmt, year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, semester, lambda v: CourseOffering.semester == v)

        if course_ids:
            stmt = stmt.where(CourseOffering.course_id.in_(course_ids))

        return (
            await self._session.scalars(stmt.order_by(CourseOffering.id.asc()))
        ).all()

    async def _union_offering_ids(self, professor_id: int) -> list[int]:
        """Offerings the professor opened a session in or is assigned to.

        The assignment window mirrors the session ledger and the professor
        cards: effective today with an open end. Ownership is never replaced
        by it, or past sessions vanish once an assignment lapses.
        """
        today: date = date.today()
        opened = select(Session.offering_id).where(Session.professor_id == professor_id)
        assigned = select(CourseProfessor.offering_id).where(
            CourseProfessor.professor_id == professor_id,
            active_assignment_clause(today),
        )
        rows: Sequence[int] = (
            await self._session.scalars(opened.union(assigned))
        ).all()

        return sorted(set(rows))

    async def _sessions_in(
        self,
        offering_ids: list[int],
        date_from: datetime | None,
        date_to: datetime | None,
        session_type: str | None = None,
    ) -> Sequence[Session]:
        if not offering_ids:
            return []

        date_from = ensure_aware(date_from) if date_from is not None else None
        date_to = end_of_day(ensure_aware(date_to)) if date_to is not None else None

        stmt = select(Session).where(Session.offering_id.in_(offering_ids))
        stmt = apply_if(stmt, date_from, lambda v: Session.created_at >= v)
        stmt = apply_if(stmt, date_to, lambda v: Session.created_at <= v)
        stmt = apply_if(stmt, session_type, lambda v: Session.session_type == v)

        return (await self._session.scalars(stmt)).all()

    async def _enrolled_by_offering(
        self, offering_ids: list[int]
    ) -> dict[int, set[int]]:
        if not offering_ids:
            return {}

        rows: Sequence[tuple[int, int]] = (
            await self._session.execute(
                select(Enrollment.offering_id, Enrollment.student_id).where(
                    Enrollment.offering_id.in_(offering_ids)
                )
            )
        ).all()  # type: ignore[assignment]
        grouped: dict[int, set[int]] = {}

        for offering_id, student_id in rows:
            grouped.setdefault(offering_id, set()).add(student_id)

        return grouped

    async def _tallies(self, session_ids: list[int]) -> Counter[str]:
        if not session_ids:
            return Counter()

        rows: Sequence[tuple[str, int]] = (
            await self._session.execute(
                select(Attendance.validation_status, func.count())
                .where(Attendance.session_id.in_(session_ids))
                .group_by(Attendance.validation_status)
            )
        ).all()  # type: ignore[assignment]

        return Counter({status: count for status, count in rows})

    async def _bucketed(
        self,
        sessions: Sequence[Session],
        granularity: TrendGranularity,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[dict[date, list[Session]], dict[date, Counter[str]]]:
        """Sessions and their attendance tallies grouped by period start."""
        date_from = ensure_aware(date_from) if date_from is not None else None
        date_to = end_of_day(ensure_aware(date_to)) if date_to is not None else None

        buckets: dict[date, list[Session]] = {}

        for row in sessions:
            if row.created_at is None:
                continue

            buckets.setdefault(_bucket_key(row.created_at, granularity), []).append(row)

        session_ids: list[int] = [row.id for row in sessions]
        tallies: dict[date, Counter[str]] = {}

        if session_ids:
            stmt = select(Attendance.timestamp, Attendance.validation_status).where(
                Attendance.session_id.in_(session_ids)
            )
            stmt = apply_if(stmt, date_from, lambda v: Attendance.timestamp >= v)
            stmt = apply_if(stmt, date_to, lambda v: Attendance.timestamp <= v)
            rows: Sequence[tuple[Any, str]] = (await self._session.execute(stmt)).all()  # type: ignore[assignment]

            for stamped_at, status in rows:
                if stamped_at is None:
                    continue

                key: date = _bucket_key(stamped_at, granularity)
                tallies.setdefault(key, Counter())[status] += 1

        return buckets, tallies

    async def _course_map(self, course_ids: list[int]) -> dict[int, Course]:
        if not course_ids:
            return {}

        rows: Sequence[Course] = (
            await self._session.scalars(select(Course).where(Course.id.in_(course_ids)))
        ).all()

        return {row.id: row for row in rows}

    async def _program_map(self, program_ids: list[int]) -> dict[int, Program]:
        if not program_ids:
            return {}

        rows: Sequence[Program] = (
            await self._session.scalars(
                select(Program).where(Program.id.in_(program_ids))
            )
        ).all()

        return {row.id: row for row in rows}

    async def _year_level_map(self, year_level_ids: list[int]) -> dict[int, YearLevel]:
        if not year_level_ids:
            return {}

        rows: Sequence[YearLevel] = (
            await self._session.scalars(
                select(YearLevel).where(YearLevel.id.in_(year_level_ids))
            )
        ).all()

        return {row.id: row for row in rows}


def _expected_for(
    sessions: Sequence[Session], enrolled_by_offering: dict[int, set[int]]
) -> int:
    return sum(
        len(enrolled_by_offering.get(row.offering_id, set())) for row in sessions
    )
