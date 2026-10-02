from __future__ import annotations

import time
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DomainException
from features.analytics.model import StudentRiskScore
from features.analytics.schema import (
    AtRiskItem,
    AtRiskResponse,
    CourseComparisonItem,
    CourseComparisonResponse,
    OverviewResponse,
    RefreshRiskResponse,
    TrendGranularity,
    TrendItem,
    TrendResponse,
)
from features.attendance.model import Attendance
from features.course.model import Course, CourseOffering
from features.enrollment.model import Enrollment
from features.program.model import Program, YearLevel
from features.session.model import Session
from features.student.model import Student
from shared.enums import RiskLevel, ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.query import apply_if


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def _rates(present: int, late: int, excused: int, enrolled: int) -> tuple[float, float]:
    """Compliance (present/total) and participation ((p+l+e)/total) rates."""
    if enrolled <= 0:
        return 0.0, 0.0

    return (
        round(present / enrolled, 4),
        round((present + late + excused) / enrolled, 4),
    )


def _full_name(
    first_name: str | None, middle_name: str | None, last_name: str | None
) -> str:
    return " ".join(part for part in (first_name, middle_name, last_name) if part)


def _normalize_paging(page: int, size: int) -> tuple[int, int]:
    return max(page, 1), min(max(size, 1), MAX_PAGE_SIZE)


def _bucket_key(moment: datetime, granularity: TrendGranularity) -> date:
    day: date = _ensure_aware(moment).date()

    if granularity == "daily":
        return day

    if granularity == "weekly":
        return date.fromordinal(day.toordinal() - day.weekday())

    return day.replace(day=1)


def _offerings_stmt(
    program_id: int | None,
    year_level_id: int | None,
    semester: str | None,
    course_ids: Sequence[int] | None = None,
) -> Select[Any]:
    stmt = select(CourseOffering)
    stmt = apply_if(stmt, program_id, lambda v: CourseOffering.program_id == v)
    stmt = apply_if(stmt, year_level_id, lambda v: CourseOffering.year_level_id == v)
    stmt = apply_if(stmt, semester, lambda v: CourseOffering.semester == v)

    if course_ids:
        stmt = stmt.where(CourseOffering.course_id.in_(course_ids))

    return stmt


async def _scoped_sessions(
    session: AsyncSession,
    offering_ids: list[int],
    date_from: datetime | None,
    date_to: datetime | None,
) -> Sequence[Session]:
    if not offering_ids:
        return []

    stmt = select(Session).where(Session.offering_id.in_(offering_ids))
    stmt = apply_if(stmt, date_from, lambda v: Session.created_at >= v)
    stmt = apply_if(stmt, date_to, lambda v: Session.created_at <= v)

    return (await session.scalars(stmt)).all()


async def _enrollments_by_offering(
    session: AsyncSession, offering_ids: list[int]
) -> dict[int, set[int]]:
    if not offering_ids:
        return {}

    rows: Sequence[tuple[int, int]] = (
        await session.execute(
            select(Enrollment.offering_id, Enrollment.student_id).where(
                Enrollment.offering_id.in_(offering_ids)
            )
        )
    ).all()  # type: ignore[assignment]
    grouped: dict[int, set[int]] = {}

    for offering_id, student_id in rows:
        grouped.setdefault(offering_id, set()).add(student_id)

    return grouped


async def _tallies_for_sessions(
    session: AsyncSession, session_ids: list[int]
) -> Counter[str]:
    if not session_ids:
        return Counter()

    rows: Sequence[tuple[str, int]] = (
        await session.execute(
            select(Attendance.validation_status, func.count())
            .where(Attendance.session_id.in_(session_ids))
            .group_by(Attendance.validation_status)
        )
    ).all()  # type: ignore[assignment]

    return Counter({status: count for status, count in rows})


def _expected_for(
    sessions: Sequence[Session], enrolled_by_offering: dict[int, set[int]]
) -> int:
    return sum(len(enrolled_by_offering.get(row.offering_id, set())) for row in sessions)


class AnalyticsService:
    """Admin analytics over sessions, attendance records, and risk scores.

    Read-only except for ``refresh_risk``, which resolves its scope and
    delegates the compute plus UPSERT to a helper the risk batch job owns.
    Only ``flush()`` is used here; commit/rollback stays in the request
    dependency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overview(
        self,
        *,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> OverviewResponse:
        """Totals plus average rates over the offering filter set."""
        offerings: Sequence[CourseOffering] = (
            await self._session.scalars(
                _offerings_stmt(program_id, year_level_id, semester)
            )
        ).all()
        offering_ids: list[int] = [row.id for row in offerings]
        sessions: Sequence[Session] = await _scoped_sessions(
            self._session, offering_ids, date_from, date_to
        )
        enrolled_by_offering = await _enrollments_by_offering(
            self._session, offering_ids
        )
        tallies = await _tallies_for_sessions(
            self._session, [row.id for row in sessions]
        )
        enrolled: int = _expected_for(sessions, enrolled_by_offering)
        compliance, participation = _rates(
            tallies.get(ValidationStatus.PRESENT.value, 0),
            tallies.get(ValidationStatus.LATE.value, 0),
            tallies.get(ValidationStatus.EXCUSED.value, 0),
            enrolled,
        )

        return OverviewResponse(
            total_students=len(
                {
                    student
                    for members in enrolled_by_offering.values()
                    for student in members
                }
            ),
            total_courses=len({row.course_id for row in offerings}),
            avg_compliance_rate=compliance,
            avg_participation_rate=participation,
            total_sessions=len(sessions),
        )

    async def get_course_comparison(
        self,
        *,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        course_ids: Sequence[int] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> CourseComparisonResponse:
        """Per-course rates over the filter set; one row per course."""
        page, size = _normalize_paging(page, size)
        offerings: Sequence[CourseOffering] = (
            await self._session.scalars(
                _offerings_stmt(program_id, year_level_id, semester, course_ids)
            )
        ).all()

        if not offerings:
            return CourseComparisonResponse(items=[], total=0, page=page, size=size)

        by_course: dict[int, list[CourseOffering]] = {}

        for row in sorted(offerings, key=lambda item: item.id):
            by_course.setdefault(row.course_id, []).append(row)

        course_ids_sorted: list[int] = sorted(by_course)
        course_map: dict[int, Course] = {
            row.id: row
            for row in (
                await self._session.scalars(
                    select(Course).where(Course.id.in_(course_ids_sorted))
                )
            ).all()
        }
        items: list[CourseComparisonItem] = []

        for course_id in course_ids_sorted:
            rows: list[CourseOffering] = by_course[course_id]
            offering_ids: list[int] = [row.id for row in rows]
            sessions: Sequence[Session] = await _scoped_sessions(
                self._session, offering_ids, date_from, date_to
            )
            enrolled_by_offering = await _enrollments_by_offering(
                self._session, offering_ids
            )
            tallies = await _tallies_for_sessions(
                self._session, [row.id for row in sessions]
            )
            compliance, participation = _rates(
                tallies.get(ValidationStatus.PRESENT.value, 0),
                tallies.get(ValidationStatus.LATE.value, 0),
                tallies.get(ValidationStatus.EXCUSED.value, 0),
                _expected_for(sessions, enrolled_by_offering),
            )
            course: Course | None = course_map.get(course_id)

            items.append(
                CourseComparisonItem(
                    course_id=course_id,
                    course_code=course.course_code if course else "",
                    program_id=rows[0].program_id,
                    year_level_id=rows[0].year_level_id,
                    compliance_rate=compliance,
                    participation_rate=participation,
                    total_sessions=len(sessions),
                )
            )

        total: int = len(items)

        return CourseComparisonResponse(
            items=items[(page - 1) * size : page * size],
            total=total,
            page=page,
            size=size,
        )

    async def get_trends(
        self,
        *,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        course_ids: Sequence[int] | None = None,
        granularity: TrendGranularity = "daily",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> TrendResponse:
        """Bucketed rates; buckets are period-start dates in ascending order."""
        page, size = _normalize_paging(page, size)
        offerings: Sequence[CourseOffering] = (
            await self._session.scalars(
                _offerings_stmt(program_id, year_level_id, semester, course_ids)
            )
        ).all()
        offering_ids: list[int] = [row.id for row in offerings]

        if not offering_ids:
            return TrendResponse(items=[], total=0, page=page, size=size)

        sessions: Sequence[Session] = await _scoped_sessions(
            self._session, offering_ids, date_from, date_to
        )
        enrolled_by_offering = await _enrollments_by_offering(
            self._session, offering_ids
        )
        session_ids: list[int] = [row.id for row in sessions]
        session_by_id: dict[int, Session] = {row.id: row for row in sessions}
        bucket_sessions: dict[date, list[Session]] = {}

        for row in sessions:
            if row.created_at is None:
                continue

            bucket_sessions.setdefault(
                _bucket_key(row.created_at, granularity), []
            ).append(row)

        bucket_tallies: dict[date, Counter[str]] = {}

        if session_ids:
            rows: Sequence[tuple[datetime, str]] = (
                await self._session.execute(
                    select(Attendance.timestamp, Attendance.validation_status).where(
                        Attendance.session_id.in_(session_ids)
                    )
                )
            ).all()  # type: ignore[assignment]

            for stamped_at, status in rows:
                if stamped_at is None:
                    continue

                key: date = _bucket_key(stamped_at, granularity)
                bucket_tallies.setdefault(key, Counter())[status] += 1

        items: list[TrendItem] = []

        for key in sorted(set(bucket_sessions) | set(bucket_tallies)):
            bucket: list[Session] = bucket_sessions.get(key, [])
            tallies: Counter[str] = bucket_tallies.get(key, Counter())
            enrolled: int = _expected_for(bucket, enrolled_by_offering)
            compliance, participation = _rates(
                tallies.get(ValidationStatus.PRESENT.value, 0),
                tallies.get(ValidationStatus.LATE.value, 0),
                tallies.get(ValidationStatus.EXCUSED.value, 0),
                enrolled,
            )
            session_count: int = len(
                {row.id for row in bucket}
                | {
                    row_id
                    for row_id, row in session_by_id.items()
                    if _bucket_key(row.created_at, granularity) == key
                    if row.created_at is not None
                }
            )

            items.append(
                TrendItem(
                    date=key,
                    compliance_rate=compliance,
                    participation_rate=participation,
                    total_sessions=session_count,
                )
            )

        total: int = len(items)

        return TrendResponse(
            items=items[(page - 1) * size : page * size],
            total=total,
            page=page,
            size=size,
        )

    async def get_at_risk(
        self,
        *,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        risk_level: RiskLevel | str | None = None,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> AtRiskResponse:
        """Read stored risk rows; feature values come from the JSONB snapshot."""
        page, size = _normalize_paging(page, size)
        stmt = (
            select(
                StudentRiskScore, Student, Program, YearLevel, CourseOffering, Course
            )
            .join(Student, Student.id == StudentRiskScore.student_id)
            .join(YearLevel, YearLevel.id == Student.year_level_id)
            .join(Program, Program.id == YearLevel.program_id)
            .join(CourseOffering, CourseOffering.id == StudentRiskScore.offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
        )
        stmt = apply_if(stmt, program_id, lambda v: CourseOffering.program_id == v)
        stmt = apply_if(
            stmt, year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(stmt, semester, lambda v: StudentRiskScore.semester == v)
        stmt = apply_if(
            stmt,
            RiskLevel(risk_level) if risk_level is not None else None,
            lambda v: StudentRiskScore.risk_level == v.value,
        )
        ordered = stmt.order_by(
            StudentRiskScore.risk_probability.desc(),
            StudentRiskScore.computed_at.desc(),
            StudentRiskScore.id.desc(),
        )
        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(ordered.subquery())
            )
            or 0
        )
        rows: Sequence[tuple[
            StudentRiskScore, Student, Program, YearLevel, CourseOffering, Course
        ]] = (await self._session.execute(ordered.offset((page - 1) * size).limit(size))).all()  # type: ignore[assignment]
        items: list[AtRiskItem] = []

        for score, student, program, year_level, _offering, course in rows:
            features: dict = score.features or {}

            items.append(
                AtRiskItem(
                    student_id=score.student_id,
                    student_name=_full_name(
                        student.first_name, student.middle_name, student.last_name
                    ),
                    program=program.code,
                    year_level=year_level.label,
                    offering_id=score.offering_id,
                    course_code=course.course_code,
                    course_name=course.course_name,
                    absence_rate=float(features.get("absence_rate", 0.0)),
                    max_streak=int(features.get("max_streak", 0)),
                    trend_slope=float(features.get("trend_slope", 0.0)),
                    risk_level=RiskLevel(score.risk_level),
                    computed_at=_ensure_aware(score.computed_at),
                )
            )

        return AtRiskResponse(items=items, total=total, page=page, size=size)

    async def _resolve_refresh_targets(
        self,
        student_id: int | None,
        offering_id: int | None,
        semester: str | None,
    ) -> list[tuple[int, int, str]]:
        """Enrollment tuples a refresh covers; full batch is active only."""
        if offering_id is not None and semester is None:
            raise DomainException(
                "semester is required when offering_id is set",
                code="validation_error",
                field="semester",
            )

        stmt = select(
            Enrollment.student_id, Enrollment.offering_id, Enrollment.semester
        )

        if student_id is not None:
            stmt = stmt.where(Enrollment.student_id == student_id)

        if offering_id is not None:
            stmt = stmt.where(Enrollment.offering_id == offering_id)

        if semester is not None and offering_id is not None:
            stmt = stmt.where(Enrollment.semester == semester)
        elif semester is not None and student_id is None and offering_id is None:
            stmt = stmt.where(Enrollment.semester == semester)
        elif student_id is None and offering_id is None and semester is None:
            stmt = stmt.join(
                CourseOffering, CourseOffering.id == Enrollment.offering_id
            ).where(CourseOffering.is_active.is_(True))

        rows: Sequence[tuple[int, int, str]] = (await self._session.execute(stmt)).all()  # type: ignore[assignment]

        return list(dict.fromkeys(rows))

    async def _compute_and_upsert(
        self, targets: list[tuple[int, int, str]]
    ) -> tuple[int, int, int, int]:
        """Count stored levels for the target set without writing rows.

        The heuristic compute plus UPSERT replaces this body without changing
        the caller: same targets in, same (processed, high, medium, low) out,
        with writes added.
        """
        if not targets:
            return 0, 0, 0, 0

        student_ids: list[int] = list({student_id for student_id, _, _ in targets})
        offering_ids: list[int] = list({offering_id for _, offering_id, _ in targets})
        levels: Sequence[str] = (
            await self._session.scalars(
                select(StudentRiskScore.risk_level)
                .where(StudentRiskScore.student_id.in_(student_ids))
                .where(StudentRiskScore.offering_id.in_(offering_ids))
            )
        ).all()
        counts: Counter[str] = Counter(levels)

        return (
            len(targets),
            counts.get(RiskLevel.HIGH.value, 0),
            counts.get(RiskLevel.MEDIUM.value, 0),
            counts.get(RiskLevel.LOW.value, 0),
        )

    async def refresh_risk(
        self,
        *,
        student_id: int | None = None,
        offering_id: int | None = None,
        semester: str | None = None,
    ) -> RefreshRiskResponse:
        """Synchronous scoped recalculation; no filter runs the full batch."""
        started: float = time.perf_counter()
        targets: list[tuple[int, int, str]] = await self._resolve_refresh_targets(
            student_id, offering_id, semester
        )
        processed, high, medium, low = await self._compute_and_upsert(targets)
        await self._session.flush()

        return RefreshRiskResponse(
            processed=processed,
            high=high,
            medium=medium,
            low=low,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
