from __future__ import annotations

import csv
import io
import time
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import DomainException
from shared.datetimes import ensure_aware
from shared.enums import RiskLevel, ValidationStatus
from shared.pagination import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.query import apply_if
from shared.rates import attendance_rates
from features.analytics.batch import run_risk_batch
from features.analytics.model import StudentRiskScore, StudentRiskScoreStaging
from features.analytics.schema import (
    AtRiskItem,
    AtRiskResponse,
    CourseComparisonItem,
    CourseComparisonResponse,
    OverviewResponse,
    PromoteStagingResponse,
    RefreshRiskResponse,
    RiskStagingItem,
    RiskStagingResponse,
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


def _full_name(
    first_name: str | None, middle_name: str | None, last_name: str | None
) -> str:
    return " ".join(part for part in (first_name, middle_name, last_name) if part)


def _normalize_paging(page: int, size: int) -> tuple[int, int]:
    return max(page, 1), min(max(size, 1), MAX_PAGE_SIZE)


def _bucket_key(moment: datetime, granularity: TrendGranularity) -> date:
    day: date = ensure_aware(moment).date()

    match granularity:
        case "daily":
            return day
        case "weekly":
            return date.fromordinal(day.toordinal() - day.weekday())
        case _:
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
    return sum(
        len(enrolled_by_offering.get(row.offering_id, set())) for row in sessions
    )


def _to_at_risk_item(
    score: StudentRiskScore,
    student: Student,
    program: Program,
    year_level: YearLevel,
    course: Course,
) -> AtRiskItem:
    """Map one stored risk row plus its joins to the contract item."""
    features: dict = score.features or {}
    return AtRiskItem(
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
        computed_at=ensure_aware(score.computed_at),
    )


def _to_staging_item(
    staged: StudentRiskScoreStaging,
    student: Student,
    program: Program,
    year_level: YearLevel,
    course: Course,
) -> RiskStagingItem:
    """Map one staged dry-run row plus its joins to the review item."""
    features: dict = staged.features or {}
    promoted_at = staged.promoted_at
    return RiskStagingItem(
        student_id=staged.student_id,
        student_name=_full_name(
            student.first_name, student.middle_name, student.last_name
        ),
        program=program.code,
        year_level=year_level.label,
        offering_id=staged.offering_id,
        course_code=course.course_code,
        course_name=course.course_name,
        absence_rate=float(features.get("absence_rate", 0.0)),
        max_streak=int(features.get("max_streak", 0)),
        trend_slope=float(features.get("trend_slope", 0.0)),
        risk_level=RiskLevel(staged.risk_level),
        computed_at=ensure_aware(staged.computed_at),
        promoted_at=ensure_aware(promoted_at) if promoted_at is not None else None,
    )


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
        compliance, participation = attendance_rates(
            present=tallies.get(ValidationStatus.PRESENT.value, 0),
            late=tallies.get(ValidationStatus.LATE.value, 0),
            excused=tallies.get(ValidationStatus.EXCUSED.value, 0),
            enrolled=enrolled,
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
            compliance, participation = attendance_rates(
                present=tallies.get(ValidationStatus.PRESENT.value, 0),
                late=tallies.get(ValidationStatus.LATE.value, 0),
                excused=tallies.get(ValidationStatus.EXCUSED.value, 0),
                enrolled=_expected_for(sessions, enrolled_by_offering),
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
            compliance, participation = attendance_rates(
                present=tallies.get(ValidationStatus.PRESENT.value, 0),
                late=tallies.get(ValidationStatus.LATE.value, 0),
                excused=tallies.get(ValidationStatus.EXCUSED.value, 0),
                enrolled=enrolled,
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
        ]] = (
            await self._session.execute(
                ordered.offset((page - 1) * size).limit(size)
            )
        ).all()  # type: ignore[assignment]
        items: list[AtRiskItem] = [
            _to_at_risk_item(score, student, program, year_level, course)
            for score, student, program, year_level, _offering, course in rows
        ]

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
        stmt = apply_if(stmt, student_id, lambda v: Enrollment.student_id == v)
        stmt = apply_if(stmt, offering_id, lambda v: Enrollment.offering_id == v)

        # `semester` scopes the query only when it rides with `offering_id` or
        # stands alone; beside `student_id` it is ignored by design.
        semester_scoped = offering_id is not None or (
            student_id is None and semester is not None
        )
        stmt = apply_if(
            stmt,
            semester if semester_scoped else None,
            lambda v: Enrollment.semester == v,
        )
        if student_id is None and offering_id is None and semester is None:
            stmt = stmt.join(
                CourseOffering, CourseOffering.id == Enrollment.offering_id
            ).where(CourseOffering.is_active.is_(True))

        rows: Sequence[tuple[int, int, str]] = (
            await self._session.execute(stmt)
        ).all()  # type: ignore[assignment]

        return list(dict.fromkeys(rows))

    async def _compute_and_upsert(
        self, targets: list[tuple[int, int, str]]
    ) -> tuple[int, int, int, int]:
        """Compute heuristic risk for the target set and persist the rows."""
        if not targets:
            return 0, 0, 0, 0

        summary = await run_risk_batch(self._session, targets)
        return (
            summary["processed"],
            summary["high"],
            summary["medium"],
            summary["low"],
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

    async def list_staged(
        self,
        *,
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        risk_level: RiskLevel | str | None = None,
        unpromoted_only: bool = False,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> RiskStagingResponse:
        """Read staged dry-run rows without touching live scores."""
        page, size = _normalize_paging(page, size)
        stmt = (
            select(
                StudentRiskScoreStaging,
                Student,
                Program,
                YearLevel,
                CourseOffering,
                Course,
            )
            .join(Student, Student.id == StudentRiskScoreStaging.student_id)
            .join(YearLevel, YearLevel.id == Student.year_level_id)
            .join(Program, Program.id == YearLevel.program_id)
            .join(
                CourseOffering,
                CourseOffering.id == StudentRiskScoreStaging.offering_id,
            )
            .join(Course, Course.id == CourseOffering.course_id)
        )
        stmt = apply_if(stmt, program_id, lambda v: CourseOffering.program_id == v)
        stmt = apply_if(
            stmt, year_level_id, lambda v: CourseOffering.year_level_id == v
        )
        stmt = apply_if(
            stmt, semester, lambda v: StudentRiskScoreStaging.semester == v
        )
        stmt = apply_if(
            stmt,
            RiskLevel(risk_level) if risk_level is not None else None,
            lambda v: StudentRiskScoreStaging.risk_level == v.value,
        )
        if unpromoted_only:
            stmt = stmt.where(StudentRiskScoreStaging.promoted_at.is_(None))
        ordered = stmt.order_by(
            StudentRiskScoreStaging.risk_probability.desc(),
            StudentRiskScoreStaging.computed_at.desc(),
            StudentRiskScoreStaging.id.desc(),
        )
        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(ordered.subquery())
            )
            or 0
        )
        rows: Sequence[tuple[
            StudentRiskScoreStaging, Student, Program, YearLevel, CourseOffering, Course
        ]] = (
            await self._session.execute(
                ordered.offset((page - 1) * size).limit(size)
            )
        ).all()  # type: ignore[assignment]
        items: list[RiskStagingItem] = [
            _to_staging_item(staged, student, program, year_level, course)
            for staged, student, program, year_level, _offering, course in rows
        ]

        return RiskStagingResponse(items=items, total=total, page=page, size=size)

    async def promote_staged(
        self,
        *,
        student_id: int | None = None,
        offering_id: int | None = None,
        semester: str | None = None,
    ) -> PromoteStagingResponse:
        """Copy unpromoted staged rows into live scores and stamp them."""
        started: float = time.perf_counter()
        if offering_id is not None and semester is None:
            raise DomainException(
                "semester is required when offering_id is set",
                code="validation_error",
                field="semester",
            )

        stmt = select(StudentRiskScoreStaging).where(
            StudentRiskScoreStaging.promoted_at.is_(None)
        )
        stmt = apply_if(stmt, student_id, lambda v: StudentRiskScoreStaging.student_id == v)
        stmt = apply_if(stmt, offering_id, lambda v: StudentRiskScoreStaging.offering_id == v)
        semester_scoped = offering_id is not None or (
            student_id is None and semester is not None
        )
        stmt = apply_if(
            stmt,
            semester if semester_scoped else None,
            lambda v: StudentRiskScoreStaging.semester == v,
        )
        staged_rows: Sequence[StudentRiskScoreStaging] = (
            await self._session.scalars(stmt)
        ).all()

        skipped_stmt = select(StudentRiskScoreStaging).where(
            StudentRiskScoreStaging.promoted_at.is_not(None)
        )
        skipped_stmt = apply_if(
            skipped_stmt, student_id, lambda v: StudentRiskScoreStaging.student_id == v
        )
        skipped_stmt = apply_if(
            skipped_stmt, offering_id, lambda v: StudentRiskScoreStaging.offering_id == v
        )
        skipped_stmt = apply_if(
            skipped_stmt,
            semester if semester_scoped else None,
            lambda v: StudentRiskScoreStaging.semester == v,
        )
        skipped: int = (
            await self._session.scalar(
                select(func.count()).select_from(skipped_stmt.subquery())
            )
            or 0
        )

        if staged_rows:
            student_ids = list({row.student_id for row in staged_rows})
            offering_ids = list({row.offering_id for row in staged_rows})
            live_rows: Sequence[StudentRiskScore] = (
                await self._session.scalars(
                    select(StudentRiskScore)
                    .where(StudentRiskScore.student_id.in_(student_ids))
                    .where(StudentRiskScore.offering_id.in_(offering_ids))
                )
            ).all()
            by_key = {
                (row.student_id, row.offering_id, row.semester, row.computed_day): row
                for row in live_rows
            }

            promoted_at = datetime.now(timezone.utc)
            for staged in staged_rows:
                key = (
                    staged.student_id,
                    staged.offering_id,
                    staged.semester,
                    staged.computed_day,
                )
                live = by_key.get(key)
                if live is None:
                    live = StudentRiskScore(
                        student_id=staged.student_id,
                        offering_id=staged.offering_id,
                        semester=staged.semester,
                        risk_probability=staged.risk_probability,
                        risk_level=staged.risk_level,
                        features=staged.features,
                        computed_at=staged.computed_at,
                        computed_day=staged.computed_day,
                    )
                    self._session.add(live)
                    by_key[key] = live
                else:
                    live.risk_probability = staged.risk_probability
                    live.risk_level = staged.risk_level
                    live.features = staged.features
                    live.computed_at = staged.computed_at
                staged.promoted_at = promoted_at
            await self._session.flush()

        return PromoteStagingResponse(
            promoted=len(staged_rows),
            skipped=skipped,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def export_course_comparison(
        self,
        *,
        format: str = "csv",
        program_id: int | None = None,
        year_level_id: int | None = None,
        semester: str | None = None,
        course_ids: Sequence[int] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> str:
        """Per-course rows rendered as CSV text for the admin export download.

        Only CSV is built here: no PDF writer is installed, so `pdf` is a
        422 rather than a silently dropped option. Generation and backup-log
        persistence stay separate — this returns text, the router streams it.
        """
        if format != "csv":
            raise DomainException(
                "PDF export is not available yet; request format csv",
                code="validation_error",
                field="format",
            )

        compared: CourseComparisonResponse = await self.get_course_comparison(
            program_id=program_id,
            year_level_id=year_level_id,
            semester=semester,
            course_ids=course_ids,
            date_from=date_from,
            date_to=date_to,
            page=DEFAULT_PAGE,
            size=MAX_PAGE_SIZE,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "course_id",
                "course_code",
                "program_id",
                "year_level_id",
                "compliance_rate",
                "participation_rate",
                "total_sessions",
            ]
        )

        for item in compared.items:
            writer.writerow(
                [
                    item.course_id,
                    item.course_code,
                    item.program_id,
                    item.year_level_id,
                    item.compliance_rate,
                    item.participation_rate,
                    item.total_sessions,
                ]
            )

        return buffer.getvalue()
