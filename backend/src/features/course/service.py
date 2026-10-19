from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.exceptions import (
    AssignmentAlreadyEndedException,
    ComponentExistsException,
    ComponentNotFoundException,
    CourseCodeExistsException,
    CourseHasOfferingsException,
    CourseNotArchivedException,
    CourseNotFoundException,
    EnrollmentNotFoundException,
    OfferingAssignmentNotFoundException,
    ProfessorNotEligibleException,
    InvalidEffectiveFromException,
    OfferingExistsException,
    OfferingHasAssignmentsException,
    OfferingHasEnrollmentsException,
    OfferingHasSessionsException,
    OfferingNotArchivedException,
    OfferingNotFoundException,
    OfferingScheduleWindowException,
    ScheduleMismatchException,
    WeeklyHoursBelowUnitsException,
    WeeklyHoursExceedUnitsException,
    WindowsExceedDurationException,
)
from features.course.model import Course, CourseOffering, OfferingComponent
from features.course.schema import (
    AssignmentRead,
    BulkEnrollError,
    BulkEnrollResult,
    ComponentCreate,
    ComponentRead,
    ComponentUpdate,
    CourseCreate,
    CourseImportError,
    CourseImportResult,
    CourseRead,
    CourseUpdate,
    OfferingCreate,
    OfferingRead,
    OfferingUpdate,
    ProfessorAssignment,
    ProfessorReassignment,
    ProfessorReopen,
    RosterItem,
)
from features.course_professor.exceptions import (
    AssignmentHasSessionsException,
    AssignmentNotEndedException,
    AssignmentReopenConflictException,
    OverlappingAssignmentException,
)
from features.course_professor.model import CourseProfessor
from features.course_professor.service import CourseProfessorService
from features.enrollment.model import Enrollment
from features.professor.exceptions import ProfessorNotFoundException
from features.professor.model import Professor
from features.session.model import Session
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
    strip_upper,
)
from shared.enums import AuditAction, AuditEntity, SessionType
from shared.pagination import PaginatedResponse
from shared.query import apply_if
from shared.schedule import distinct_day_count, meeting_minutes, term_weeks
from features.course.constants import (
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    DURATION_MAX,
    DURATION_MIN,
    NAME_MAX_LENGTH,
    UNITS_MAX,
    UNITS_MIN,
)

BULK_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn("student_id", required_reason="missing student_id"),
    CsvColumn("first_name"),
    CsvColumn("middle_name"),
    CsvColumn("last_name"),
    CsvColumn("email"),
    CsvColumn("program_code"),
    CsvColumn("year_level"),
    CsvColumn("section"),
)

BULK_CSV_SCHEMA = CsvSchema(
    columns=BULK_CSV_COLUMNS,
    subject="student",
    subject_column="student_id",
    checks=(
        CsvGroup(
            columns=("first_name", "last_name", "email"),
            reason="missing required field for {subject} {key}",
        ),
        CsvEmailCheck("email", "invalid email for {subject} {key}"),
        CsvGroup(
            columns=("program_code", "year_level"),
            reason="missing program_code/year_level for {subject} {key}",
        ),
    ),
)


@dataclass(kw_only=True)
class _CsvRow:
    line: int
    student_id: str
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    program_code: str
    year_level: str
    section: str | None


@dataclass(frozen=True, kw_only=True)
class _RowOutcome:
    """Result of processing one bulk-enroll CSV row."""

    enrolled: bool = False
    skipped: bool = False
    error: BulkEnrollError | None = None


def _to_csv_row(raw: CsvRow) -> _CsvRow:
    values: dict[str, str] = raw.values

    return _CsvRow(
        line=raw.line,
        student_id=values["student_id"],
        first_name=values["first_name"],
        middle_name=values["middle_name"] or None,
        last_name=values["last_name"],
        email=values["email"],
        program_code=values["program_code"],
        year_level=values["year_level"],
        section=values["section"] or None,
    )


def parse_enrollment_csv(content: bytes) -> tuple[list[_CsvRow], list[BulkEnrollError]]:
    """Parse the bulk-enroll CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem is
    reported as a BulkEnrollError with its 1-based line number (header = 1).
    Cells are only stripped, not case-folded: `bulk_enroll` compares against
    the stored student and offering values itself.
    """
    rows, errors = parse_import_csv(
        content,
        BULK_CSV_SCHEMA,
        error=lambda line, reason: BulkEnrollError(line=line, reason=reason),
    )

    return [_to_csv_row(row) for row in rows], errors


COURSE_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn(
        "course_code", normalize=strip_upper, required_reason="missing course_code"
    ),
    CsvColumn("course_name"),
    CsvColumn("units", required_reason="missing units"),
    CsvColumn(
        "session_duration_hours", required_reason="missing session_duration_hours"
    ),
)

COURSE_CSV_SCHEMA = CsvSchema(
    columns=COURSE_CSV_COLUMNS,
    subject="course",
    subject_column="course_code",
    subject_fallback="on line",
    checks=(
        CsvGroup(
            columns=("course_name",),
            reason="missing required field for {subject} {key}",
        ),
    ),
)


@dataclass(kw_only=True)
class _CourseRow:
    line: int
    course_code: str
    course_name: str
    units: str
    session_duration_hours: str


def _to_course_row(raw: CsvRow) -> _CourseRow:
    values: dict[str, str] = raw.values

    return _CourseRow(
        line=raw.line,
        course_code=values["course_code"],
        course_name=values["course_name"],
        units=values["units"],
        session_duration_hours=values["session_duration_hours"],
    )


def parse_course_csv(
    content: bytes,
) -> tuple[list[_CourseRow], list[CourseImportError]]:
    """Parse the course-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem
    is reported as a CourseImportError with its 1-based line number
    (header = 1). Codes are uppercased so duplicate detection agrees with
    single-create.
    """
    rows, errors = parse_import_csv(
        content,
        COURSE_CSV_SCHEMA,
        error=lambda line, reason: CourseImportError(line=line, reason=reason),
    )

    return [_to_course_row(row) for row in rows], errors


def _validate_course_row(row: _CourseRow) -> str | None:
    """Domain validation beyond presence. Returns the reason or None."""
    if not (CODE_MIN_LENGTH <= len(row.course_code) <= CODE_MAX_LENGTH):
        return (
            f"invalid course_code for course {row.course_code}: "
            f"must be {CODE_MIN_LENGTH}-{CODE_MAX_LENGTH} characters"
        )
    name = row.course_name.strip()
    if not (1 <= len(name) <= NAME_MAX_LENGTH):
        return f"invalid course_name for course {row.course_code}"
    try:
        units = int(row.units.strip())
    except ValueError:
        return f"invalid units for course {row.course_code}"
    if not (UNITS_MIN <= units <= UNITS_MAX):
        return (
            f"invalid units for course {row.course_code}: "
            f"must be {UNITS_MIN}-{UNITS_MAX}"
        )
    try:
        duration = float(row.session_duration_hours.strip())
    except ValueError:
        return f"invalid session_duration_hours for course {row.course_code}"
    if not (DURATION_MIN <= duration <= DURATION_MAX):
        return (
            f"invalid session_duration_hours for course {row.course_code}: "
            f"must be {DURATION_MIN}-{DURATION_MAX}"
        )
    return None


def _check_weekly_hours(
    course: Course, new_total_minutes: float, old_total_minutes: float | None
) -> None:
    """Enforce `units` as the required weekly scheduled meeting hours (D79).

    Totals are compared in whole minutes: every meeting duration is
    minute-precise and multiplied by an integer day count, so rounding here
    only absorbs float dust, never a real deviation.
    `new_total_minutes` is the merged active-set total after the proposed
    write; `old_total_minutes` is the current active-set total (`None` for
    offering creation, where there is no current set). A write landing
    exactly on `units * 60` always passes. Off-requirement totals may only
    converge: the new total must move strictly closer without crossing to
    the other side (an under total cannot overshoot into over and vice
    versa). Callers: offering creation (exact only), component add, and
    component reactivation. Plain component edits skip this check by design
    (D81) — multi-step reshapes pass through mismatched totals — as do
    reads, archives, deactivations, and schedule-untouched edits.
    """

    def _as_minutes(value: float) -> int:
        return int(round(value))

    limit_minutes = int(course.units) * 60
    new_minutes = _as_minutes(new_total_minutes)
    if new_minutes == limit_minutes:
        return
    if old_total_minutes is not None:
        old_minutes = _as_minutes(old_total_minutes)
        same_side = (new_minutes - limit_minutes) * (old_minutes - limit_minutes) > 0
        closer = abs(new_minutes - limit_minutes) < abs(old_minutes - limit_minutes)
        if old_minutes != limit_minutes and same_side and closer:
            return
    scheduled_hours = round(new_minutes / 60, 2)
    limit_hours = round(limit_minutes / 60, 2)
    if new_minutes > limit_minutes:
        raise WeeklyHoursExceedUnitsException(
            scheduled_hours,
            limit_hours,
            course.course_code,
            int(course.units),
        )
    raise WeeklyHoursBelowUnitsException(
        scheduled_hours,
        limit_hours,
        course.course_code,
        int(course.units),
    )


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._courses: BaseCRUD[Course] = BaseCRUD(Course, session)
        self._offerings: BaseCRUD[CourseOffering] = BaseCRUD(CourseOffering, session)
        self._components: BaseCRUD[OfferingComponent] = BaseCRUD(
            OfferingComponent, session
        )
        self._enrollments: BaseCRUD[Enrollment] = BaseCRUD(Enrollment, session)
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)

    # -- course template CRUD (unchanged) -------------------------------

    async def create(
        self, *, payload: CourseCreate, actor_id: int | None = None
    ) -> CourseRead:
        if await self._courses.get_by(course_code=payload.course_code) is not None:
            raise CourseCodeExistsException(payload.course_code)

        course: Course = await self._courses.create(
            course_code=payload.course_code,
            course_name=payload.course_name,
            units=payload.units,
            session_duration_hours=payload.session_duration_hours,
        )

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.COURSE,
            entity_id=course.id,
            new_value=self._course_snapshot(course),
        )

        return CourseRead.model_validate(course)

    async def get(self, *, course_id: int) -> CourseRead:
        return CourseRead.model_validate(await self._get_or_404(course_id))

    async def list(
        self,
        *,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[CourseRead]:
        stmt: Select[tuple[Course]] = select(Course)

        if is_active is not None:
            stmt = stmt.where(Course.is_active == is_active)

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows = (
            await self._session.scalars(
                stmt.order_by(Course.id).offset((page - 1) * size).limit(size)
            )
        ).all()

        return PaginatedResponse[CourseRead](
            items=[CourseRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def update(
        self, *, course_id: int, payload: CourseUpdate, actor_id: int | None = None
    ) -> CourseRead:
        course: Course = await self._get_or_404(course_id)
        old_value = self._course_snapshot(course)

        if (
            "course_code" in payload.model_fields_set
            and payload.course_code is not None
            and payload.course_code != course.course_code
            and await self._courses.get_by(course_code=payload.course_code) is not None
        ):
            raise CourseCodeExistsException(payload.course_code)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(course, field, value)

        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(course)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.COURSE,
            entity_id=course.id,
            old_value=old_value,
            new_value=self._course_snapshot(course),
        )

        return CourseRead.model_validate(course)

    async def hard_delete(
        self, *, course_id: int, actor_id: int | None = None
    ) -> None:
        """Permanently delete an archived course with no offerings."""
        course: Course = await self._get_or_404(course_id)

        if course.is_active:
            raise CourseNotArchivedException(course.id)

        offering_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(CourseOffering)
                .where(CourseOffering.course_id == course_id)
            )
            or 0
        )

        if offering_count > 0:
            raise CourseHasOfferingsException(course_id)

        # Snapshot before the delete: the instance is detached once flushed.
        old_value = self._course_snapshot(course)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=AuditEntity.COURSE,
            entity_id=course.id,
            old_value=old_value,
        )

        await self._session.delete(course)
        await self._session.flush()

    async def import_roster(
        self, *, content: bytes, actor_id: int | None
    ) -> CourseImportResult:
        """Create NEW course templates from a CSV upload.

        Rows whose course_code already exists — in the database or earlier
        in the same file — are counted as duplicates, not errors. Courses
        stay standalone templates (D44): no program, schedule, or classroom
        linkage is created here; offerings attach later.
        """
        rows, errors = parse_course_csv(content)
        imported = 0
        duplicates = 0
        seen_codes: set[str] = set()

        for row in rows:
            if (
                row.course_code in seen_codes
                or await self._courses.get_by(course_code=row.course_code) is not None
            ):
                duplicates += 1
                seen_codes.add(row.course_code)
                continue

            seen_codes.add(row.course_code)
            reason = _validate_course_row(row)

            if reason is not None:
                errors.append(CourseImportError(line=row.line, reason=reason))
                continue

            self._session.add(
                Course(
                    course_code=row.course_code,
                    course_name=row.course_name.strip(),
                    units=int(row.units.strip()),
                    session_duration_hours=float(
                        row.session_duration_hours.strip()
                    ),
                )
            )
            imported += 1

        await self._session.flush()

        # One row for the upload rather than one per course, so a large
        # file cannot bury every other action in the trail.
        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.IMPORT,
            entity_type=AuditEntity.COURSE,
            entity_id=None,
            new_value={
                "imported": imported,
                "duplicates": duplicates,
                "errors": len(errors),
            },
        )

        errors.sort(key=lambda e: e.line)

        return CourseImportResult(
            imported=imported, duplicates=duplicates, errors=errors
        )

    @staticmethod
    def _course_snapshot(course: Course) -> dict[str, Any]:
        return {
            "course_code": course.course_code,
            "course_name": course.course_name,
            "units": course.units,
            "session_duration_hours": float(course.session_duration_hours),
            "is_active": course.is_active,
        }

    async def _get_or_404(self, course_id: int) -> Course:
        course: Course | None = await self._courses.get(course_id)

        if course is None:
            raise CourseNotFoundException(course_id)

        return course

    # -- offering CRUD ---------------------------------------------------

    async def create_offering(
        self, *, payload: OfferingCreate, actor_id: int | None = None
    ) -> OfferingRead:
        course: Course = await self._get_or_404(payload.course_id)
        await self._require_program(payload.program_id)
        await self._require_year_level(payload.program_id, payload.year_level_id)
        self._check_windows(
            course,
            payload.default_present_window_minutes,
            payload.default_late_window_minutes,
        )
        await self._require_no_duplicate_offering(payload)
        if payload.components:
            new_total = sum(
                meeting_minutes(
                    component.schedule_days,
                    component.schedule_start_time,
                    component.schedule_end_time,
                )
                for component in payload.components
            )
        else:
            new_total = meeting_minutes(
                payload.schedule_days,
                payload.schedule_start_time,
                payload.schedule_end_time,
            )
        _check_weekly_hours(course, new_total, None)

        offering: CourseOffering = await self._offerings.create(
            **payload.model_dump(exclude={"components"})
        )

        # D77: an offering without explicit components gets a single lecture
        # component mirroring its schedule/classroom, so every offering —
        # old or new — has at least one component to pre-fill sessions from.
        if payload.components:
            for component in payload.components:
                await self._insert_component(offering=offering, payload=component)
        else:
            await self._insert_component(
                offering=offering,
                payload=ComponentCreate(
                    session_type=SessionType.LECTURE,
                    schedule_days=payload.schedule_days,
                    schedule_start_time=payload.schedule_start_time,
                    schedule_end_time=payload.schedule_end_time,
                    classroom_name=payload.classroom_name,
                    classroom_lat=payload.classroom_lat,
                    classroom_lng=payload.classroom_lng,
                ),
            )
        await self._mirror_single_component(offering)
        await self._sync_sessions_per_week(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering.id,
            new_value=self._offering_snapshot(offering),
        )

        return await self._to_offering_read(offering)

    async def get_offering(self, *, offering_id: int) -> OfferingRead:
        return await self._to_offering_read(
            await self._get_offering_or_404(offering_id)
        )

    async def list_offerings(
        self,
        *,
        program_id: int | None,
        year_level_id: int | None,
        semester: str | None,
        course_id: int | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[OfferingRead]:
        stmt: Select[tuple[CourseOffering]] = select(CourseOffering)

        if program_id is not None:
            stmt = stmt.where(CourseOffering.program_id == program_id)

        if year_level_id is not None:
            stmt = stmt.where(CourseOffering.year_level_id == year_level_id)

        if semester is not None:
            stmt = stmt.where(CourseOffering.semester == semester)

        if course_id is not None:
            stmt = stmt.where(CourseOffering.course_id == course_id)

        if is_active is not None:
            stmt = stmt.where(CourseOffering.is_active == is_active)

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[CourseOffering] = (
            await self._session.scalars(
                stmt.order_by(CourseOffering.id).offset((page - 1) * size).limit(size)
            )
        ).all()

        return PaginatedResponse[OfferingRead](
            items=[await self._to_offering_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def update_offering(
        self,
        *,
        offering_id: int,
        payload: OfferingUpdate,
        actor_id: int | None = None,
    ) -> OfferingRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
        old_value = self._offering_snapshot(offering)

        # Validate against the merged result, before touching the ORM object.
        # A PATCH that moves only `schedule_start_time` past the stored end
        # has to be caught here: the schema validator cannot see the half it
        # was not sent, and mutating first would leave the row dirty when the
        # request is rejected.
        start = changes.get("schedule_start_time", offering.schedule_start_time)
        end = changes.get("schedule_end_time", offering.schedule_end_time)

        if start is None or end is None or end <= start:
            raise OfferingScheduleWindowException()

        # Activation gate (D82): an offering whose meetings mismatch the
        # requirement cannot go live. Only the False -> True transition is
        # checked, before the row is dirtied — deactivation, unrelated
        # PATCHes, and already-active rows are unaffected, including the
        # zero-meeting case, which mismatches every positive units value.
        if bool(changes.get("is_active", offering.is_active)) and not offering.is_active:
            await self._require_exact_for_activation(offering)

        for field, value in changes.items():
            setattr(offering, field, value)

        course: Course = await self._get_or_404(offering.course_id)
        self._check_windows(
            course,
            offering.default_present_window_minutes,
            offering.default_late_window_minutes,
        )

        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering.id,
            old_value=old_value,
            new_value=self._offering_snapshot(offering),
        )

        return await self._to_offering_read(offering)

    async def hard_delete_offering(
        self, *, offering_id: int, actor_id: int | None = None
    ) -> None:
        """Permanently delete an archived offering with no dependents.

        Guards run in FK order — enrollments, sessions, assignments — before
        the delete, so a `RESTRICT` violation can never surface as a 500.
        Components are owned by the offering and are removed with it once the
        guards above are proven empty.
        """
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        if offering.is_active:
            raise OfferingNotArchivedException(offering.id)

        enrollment_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.offering_id == offering_id)
            )
            or 0
        )

        if enrollment_count > 0:
            raise OfferingHasEnrollmentsException(offering_id)

        session_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.offering_id == offering_id)
            )
            or 0
        )

        if session_count > 0:
            raise OfferingHasSessionsException(offering_id)

        assignment_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(CourseProfessor)
                .where(CourseProfessor.offering_id == offering_id)
            )
            or 0
        )

        if assignment_count > 0:
            raise OfferingHasAssignmentsException(offering_id)

        # Snapshot before the delete: the instance is detached once flushed.
        old_value = self._offering_snapshot(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering.id,
            old_value=old_value,
        )

        # Components have no meaning without their offering — remove them with
        # it now that enrollments/sessions/assignments are proven empty.
        components: Sequence[OfferingComponent] = (
            await self._session.scalars(
                select(OfferingComponent).where(
                    OfferingComponent.offering_id == offering_id
                )
            )
        ).all()

        for component in components:
            await self._session.delete(component)

        await self._session.delete(offering)
        await self._session.flush()

    # -- professor assignments -------------------------------------------

    async def list_assignments(self, *, offering_id: int) -> Sequence[AssignmentRead]:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        rows: Sequence[CourseProfessor] = (
            await self._session.scalars(
                select(CourseProfessor)
                .where(CourseProfessor.offering_id == offering_id)
                .order_by(CourseProfessor.effective_from)
            )
        ).all()

        # One extra query rather than one per assignment: the admin table needs
        # to know which rows are protected by session history. `Session.created_at`
        # is the authorization timestamp (not `scheduled_start_time`), so the
        # same rule decides the flag and the permanent-remove guard.
        sessions_by_professor: dict[int, list[datetime]] = {}
        if rows:
            session_rows = (
                await self._session.execute(
                    select(Session.professor_id, Session.created_at).where(
                        Session.offering_id == offering_id
                    )
                )
            ).all()
            for professor_id, created_at in session_rows:
                sessions_by_professor.setdefault(professor_id, []).append(created_at)

        result: list[AssignmentRead] = []
        for row in rows:
            read = AssignmentRead.model_validate(row)
            read.semester = offering.semester
            start, end = self._assignment_window(row)
            read.has_sessions = any(
                self._session_in_assignment_window(created_at, start, end)
                for created_at in sessions_by_professor.get(row.professor_id, [])
            )
            result.append(read)
        return result

    @staticmethod
    def _assignment_window(
        row: CourseProfessor,
    ) -> tuple[datetime, datetime | None]:
        """UTC half-open window in which an assignment authorizes sessions."""
        start = datetime.combine(row.effective_from, time.min).replace(
            tzinfo=timezone.utc
        )
        end = (
            datetime.combine(
                row.effective_to + timedelta(days=1), time.min
            ).replace(tzinfo=timezone.utc)
            if row.effective_to is not None
            else None
        )
        return start, end

    @staticmethod
    def _session_in_assignment_window(
        created_at: datetime, start: datetime, end: datetime | None
    ) -> bool:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at >= start and (end is None or created_at < end)

    async def _assignment_has_sessions(self, row: CourseProfessor) -> bool:
        start, end = self._assignment_window(row)
        stmt = select(Session.id).where(
            Session.offering_id == row.offering_id,
            Session.professor_id == row.professor_id,
            Session.created_at >= start,
        )
        if end is not None:
            stmt = stmt.where(Session.created_at < end)

        return (await self._session.scalar(stmt.limit(1))) is not None

    async def assign_professor(
        self,
        *,
        offering_id: int,
        payload: ProfessorAssignment,
        assigned_by: int,
    ) -> AssignmentRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        professor: Professor | None = await self._session.get(Professor, payload.professor_id)
        if professor is None:
            raise ProfessorNotFoundException(payload.professor_id)
        if not professor.is_active:
            raise ProfessorNotEligibleException(payload.professor_id)

        overlap_service = CourseProfessorService(self._session)
        overlap: list[CourseProfessor] = await overlap_service.check_overlap(
            offering_id,
            payload.professor_id,
            payload.effective_from,
            payload.effective_to,
        )

        if overlap:
            existing: CourseProfessor = overlap[0]
            raise OverlappingAssignmentException(
                offering_id,
                payload.professor_id,
                payload.effective_from,
                payload.effective_to,
                existing.effective_from,
                existing.effective_to,
            )

        if payload.is_primary:
            await overlap_service.ensure_primary_available(
                offering_id,
                payload.effective_from,
                payload.effective_to,
            )

        record = CourseProfessor(
            offering_id=offering_id,
            professor_id=payload.professor_id,
            is_primary=payload.is_primary,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            assigned_by=assigned_by,
        )
        self._session.add(record)
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=assigned_by,
            action=AuditAction.ASSIGN,
            entity_type=AuditEntity.COURSE_PROFESSOR,
            entity_id=None,
            new_value=self._assignment_snapshot(record),
        )

        return AssignmentRead.model_validate(record)

    async def _get_assignment_row(
        self,
        *,
        offering_id: int,
        professor_id: int,
        today: date,
        effective_from: date | None = None,
    ) -> CourseProfessor:
        """Return exactly one assignment row.

        The composite primary key is (offering_id, professor_id,
        effective_from), so the start date is the only unambiguous selector.
        Without it, prefer the open-ended row (the one the admin UI exposes
        actions on), then the newest row that has not ended. Never use
        `.one_or_none()` here: historical and future rows legitimately coexist.
        """
        stmt = select(CourseProfessor).where(
            CourseProfessor.offering_id == offering_id,
            CourseProfessor.professor_id == professor_id,
        )
        if effective_from is not None:
            stmt = stmt.where(CourseProfessor.effective_from == effective_from)
        else:
            stmt = stmt.where(
                (CourseProfessor.effective_to.is_(None))
                | (CourseProfessor.effective_to >= today)
            ).order_by(CourseProfessor.effective_from.desc())

        rows: Sequence[CourseProfessor] = (
            await self._session.scalars(stmt)
        ).all()

        if not rows:
            raise OfferingAssignmentNotFoundException(offering_id, professor_id)

        if effective_from is not None:
            return rows[0]

        for row in rows:
            if row.effective_to is None:
                return row
        return rows[0]

    async def remove_professor(
        self,
        *,
        offering_id: int,
        professor_id: int,
        actor_id: int | None = None,
        effective_from: date | None = None,
    ) -> date:
        await self._get_offering_or_404(offering_id)

        today: date = date.today()
        row: CourseProfessor = await self._get_assignment_row(
            offering_id=offering_id,
            professor_id=professor_id,
            today=today,
            effective_from=effective_from,
        )

        old_value: dict[str, Any] = self._assignment_snapshot(row)

        # A future-dated assignment never took effect. Cancel it by deleting
        # the row: writing effective_to=today would invert the date range
        # (start tomorrow, end today).
        if row.effective_from > today:
            await self._session.delete(row)
            await self._session.flush()
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.UNASSIGN,
                entity_type=AuditEntity.COURSE_PROFESSOR,
                entity_id=None,
                old_value=old_value,
            )
            return today

        if row.effective_to is not None and row.effective_to < today:
            raise AssignmentAlreadyEndedException(
                offering_id, professor_id, row.effective_from
            )

        if row.effective_to != today:
            row.effective_to = today
            await self._session.flush()

            # Effective-dated rather than deleted: the row stays as the record
            # that the professor taught the offering until this date.
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.UNASSIGN,
                entity_type=AuditEntity.COURSE_PROFESSOR,
                entity_id=None,
                old_value=old_value,
                new_value=self._assignment_snapshot(row),
            )

        return today

    async def permanently_remove_professor(
        self,
        *,
        offering_id: int,
        professor_id: int,
        effective_from: date,
        actor_id: int | None = None,
    ) -> None:
        """Erase an assignment row that was ended and never opened a session.

        This is a narrow correction path, not a replacement for End: the admin
        must End the assignment first, so a live assignment cannot be erased in
        one step. The effective window is required because the composite primary
        key has no surrogate id; without it the wrong historical row could be
        deleted.
        """
        await self._get_offering_or_404(offering_id)

        today: date = date.today()
        row: CourseProfessor = await self._get_assignment_row(
            offering_id=offering_id,
            professor_id=professor_id,
            today=today,
            effective_from=effective_from,
        )

        # "Ended" means the end date has arrived: End stamps today, and any
        # later end date is still a live assignment that must be End-ed first.
        if row.effective_to is None or row.effective_to > today:
            raise AssignmentNotEndedException(
                offering_id, professor_id, row.effective_from
            )

        if await self._assignment_has_sessions(row):
            raise AssignmentHasSessionsException(
                offering_id, professor_id, row.effective_from
            )

        # Snapshot before the delete: the instance is detached once flushed.
        old_value: dict[str, Any] = self._assignment_snapshot(row)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=AuditEntity.COURSE_PROFESSOR,
            entity_id=None,
            old_value=old_value,
        )

        await self._session.delete(row)
        await self._session.flush()

    async def reassign_professor(
        self,
        *,
        offering_id: int,
        old_professor_id: int,
        payload: ProfessorReassignment,
        assigned_by: int,
    ) -> AssignmentRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        today: date = date.today()
        old_row: CourseProfessor = await self._get_assignment_row(
            offering_id=offering_id,
            professor_id=old_professor_id,
            today=today,
            effective_from=payload.old_effective_from,
        )

        # A started assignment that already ended cannot be reassigned: doing
        # so would either extend it or rewrite history.
        if (
            old_row.effective_from <= today
            and old_row.effective_to is not None
            and old_row.effective_to < today
        ):
            raise AssignmentAlreadyEndedException(
                offering_id, old_professor_id, old_row.effective_from
            )

        new_professor_id: int = payload.new_professor_id
        if new_professor_id == old_professor_id:
            raise ProfessorNotEligibleException(new_professor_id)

        new_professor: Professor | None = await self._session.get(
            Professor, new_professor_id
        )
        if new_professor is None:
            raise ProfessorNotFoundException(new_professor_id)
        if not new_professor.is_active:
            raise ProfessorNotEligibleException(new_professor_id)

        effective_from: date = payload.effective_from or today
        effective_to: date | None = payload.effective_to

        # A future assignment has not started, so the replacement may begin on
        # the same day. A started assignment must be replaced by a later date.
        if old_row.effective_from <= today:
            if effective_from <= old_row.effective_from:
                raise InvalidEffectiveFromException(offering_id, old_professor_id)
        elif effective_from < old_row.effective_from:
            raise InvalidEffectiveFromException(offering_id, old_professor_id)

        overlap_service = CourseProfessorService(self._session)
        overlap: list[CourseProfessor] = await overlap_service.check_overlap(
            offering_id,
            new_professor_id,
            effective_from,
            effective_to,
        )

        if overlap:
            existing: CourseProfessor = overlap[0]
            raise OverlappingAssignmentException(
                offering_id,
                new_professor_id,
                effective_from,
                effective_to,
                existing.effective_from,
                existing.effective_to,
            )

        old_is_primary: bool = old_row.is_primary
        is_primary: bool = (
            payload.is_primary if payload.is_primary is not None else old_is_primary
        )

        if is_primary:
            await overlap_service.ensure_primary_available(
                offering_id,
                effective_from,
                effective_to,
                exclude=old_row,
            )

        old_value: dict[str, Any] = self._assignment_snapshot(old_row)

        if old_row.effective_from > today and effective_from == old_row.effective_from:
            # Same-day replacement of a scheduled assignment: it never took
            # effect, so there is no history to keep.
            await self._session.delete(old_row)
        else:
            old_row.effective_to = effective_from - timedelta(days=1)
        await self._session.flush()

        record = CourseProfessor(
            offering_id=offering_id,
            professor_id=new_professor_id,
            is_primary=is_primary,
            effective_from=effective_from,
            effective_to=effective_to,
            assigned_by=assigned_by,
        )
        self._session.add(record)
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=assigned_by,
            action=AuditAction.REASSIGN,
            entity_type=AuditEntity.COURSE_PROFESSOR,
            entity_id=None,
            old_value=old_value,
            new_value=self._assignment_snapshot(record),
        )

        read = AssignmentRead.model_validate(record)
        read.semester = offering.semester
        return read

    async def reopen_professor(
        self,
        *,
        offering_id: int,
        professor_id: int,
        payload: ProfessorReopen,
        actor_id: int,
    ) -> AssignmentRead:
        """Undo an accidental End by clearing the exact assignment's end date.

        Reopening is only safe when no later assignment exists for the same
        professor and offering: the reopened row is open-ended, so a later
        range would overlap it. The caller must end/change that later row first.
        """
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        row: CourseProfessor = await self._get_assignment_row(
            offering_id=offering_id,
            professor_id=professor_id,
            today=date.today(),
            effective_from=payload.effective_from,
        )

        if row.effective_to is None:
            raise AssignmentNotEndedException(
                offering_id, professor_id, row.effective_from
            )

        later: CourseProfessor | None = await self._session.scalar(
            select(CourseProfessor)
            .where(
                CourseProfessor.offering_id == offering_id,
                CourseProfessor.professor_id == professor_id,
                CourseProfessor.effective_from > row.effective_from,
            )
            .order_by(CourseProfessor.effective_from)
            .limit(1)
        )
        if later is not None:
            raise AssignmentReopenConflictException(
                offering_id,
                professor_id,
                row.effective_from,
                later.effective_from,
            )

        is_primary: bool = (
            payload.is_primary if payload.is_primary is not None else row.is_primary
        )
        if is_primary:
            await CourseProfessorService(self._session).ensure_primary_available(
                offering_id,
                row.effective_from,
                None,
                exclude=row,
            )

        old_value: dict[str, Any] = self._assignment_snapshot(row)
        row.effective_to = None
        row.is_primary = is_primary
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.REOPEN,
            entity_type=AuditEntity.COURSE_PROFESSOR,
            entity_id=None,
            old_value=old_value,
            new_value=self._assignment_snapshot(row),
        )

        read = AssignmentRead.model_validate(row)
        read.semester = offering.semester
        read.has_sessions = await self._assignment_has_sessions(row)
        return read

    @staticmethod
    def _assignment_snapshot(record: CourseProfessor) -> dict[str, Any]:
        """An assignment row, which has a composite primary key.

        `course_professors` is keyed on (offering_id, professor_id,
        effective_from), so there is no single-column id for `AuditLog.entity_id`
        to hold; the identity lives here instead.
        """
        return {
            "offering_id": record.offering_id,
            "professor_id": record.professor_id,
            "is_primary": record.is_primary,
            "effective_from": (
                record.effective_from.isoformat() if record.effective_from else None
            ),
            "effective_to": (
                record.effective_to.isoformat() if record.effective_to else None
            ),
        }

    # -- bulk enroll + roster --------------------------------------------

    async def bulk_enroll(
        self, *, offering_id: int, content: bytes, actor_id: int | None = None
    ) -> BulkEnrollResult:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        program: Program | None = await self._session.get(Program, offering.program_id)

        rows, errors = parse_enrollment_csv(content)
        enrolled = 0
        skipped = 0
        seen: set[str] = set()

        for row in rows:
            outcome: _RowOutcome = await self._enroll_row(row, offering, program, seen)

            if outcome.error is not None:
                errors.append(outcome.error)
            elif outcome.enrolled:
                enrolled += 1
            else:
                skipped += 1

        await self._session.flush()

        # One row for the upload rather than one per student, so a large roster
        # cannot bury every other action in the trail. The per-student detail
        # lives on the `enrollments` rows themselves.
        if enrolled or skipped:
            await record_audit(
                self._session,
                actor_id=actor_id,
                action=AuditAction.ENROLL,
                entity_type=AuditEntity.ENROLLMENT,
                entity_id=None,
                new_value={
                    "offering_id": offering_id,
                    "enrolled": enrolled,
                    "skipped": skipped,
                    "errors": len(errors),
                },
            )

        errors.sort(key=lambda e: e.line)

        return BulkEnrollResult(enrolled=enrolled, skipped=skipped, errors=errors)

    async def _enroll_row(
        self,
        row: _CsvRow,
        offering: CourseOffering,
        program: Program | None,
        seen: set[str],
    ) -> _RowOutcome:
        """Validate and attach one CSV row to the offering.

        Mutates ``seen`` only on the two skip branches, so a later duplicate
        in the same file is skipped without a second database round trip.
        """
        resolved: Student | BulkEnrollError = await self._resolve_bulk_student(
            row, program
        )

        if isinstance(resolved, BulkEnrollError):
            return _RowOutcome(error=resolved)

        if row.student_id in seen:
            return _RowOutcome(skipped=True)

        if await self._is_enrolled(resolved.id, offering):
            seen.add(row.student_id)
            return _RowOutcome(skipped=True)

        seen.add(row.student_id)
        self._session.add(
            Enrollment(
                student_id=resolved.id,
                offering_id=offering.id,
                semester=offering.semester,
                academic_year=offering.academic_year,
            )
        )

        if row.section is not None and row.section != resolved.section:
            resolved.section = row.section

        return _RowOutcome(enrolled=True)

    async def _resolve_bulk_student(
        self, row: _CsvRow, program: Program | None
    ) -> Student | BulkEnrollError:
        """Look the row's student up and check it against the offering.

        Returns the student, or a BulkEnrollError carrying the reason the row
        cannot be enrolled. The three checks stay in this order — unknown id,
        email mismatch, program mismatch.
        """
        student: Student | None = await self._students.get_by(student_id=row.student_id)

        if student is None:
            return BulkEnrollError(
                line=row.line,
                reason=f"unknown student_id {row.student_id}",
            )

        if student.email.lower() != row.email.lower():
            return BulkEnrollError(
                line=row.line,
                reason=f"email mismatch for student {row.student_id}",
            )

        if program is not None and row.program_code.upper() != program.code.upper():
            return BulkEnrollError(
                line=row.line,
                reason=f"program_code {row.program_code} does not match offering",
            )

        return student

    async def _is_enrolled(self, student_id: int, offering: CourseOffering) -> bool:
        return (
            await self._enrollments.get_by(
                student_id=student_id,
                offering_id=offering.id,
                academic_year=offering.academic_year,
            )
            is not None
        )

    async def unenroll_student(
        self, *, offering_id: int, student_number: str, actor_id: int | None = None
    ) -> None:
        """Remove one enrollment link row.

        The link only: past attendance, excuse, and risk rows keep their
        student+session identity, and future scans are blocked by the live
        enrollment check. No `is_active` gate — cleanup on an archived
        offering must still work. Re-enrolling afterwards is a normal
        bulk-enroll row (the dedupe no longer matches).
        """
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        student: Student | None = await self._students.get_by(
            student_id=student_number
        )

        if student is None:
            raise StudentNotFoundException(student_number)

        enrollment: Enrollment | None = await self._enrollments.get_by(
            student_id=student.id,
            offering_id=offering.id,
            academic_year=offering.academic_year,
        )

        if enrollment is None:
            raise EnrollmentNotFoundException(offering_id, student_number)

        # Snapshot before the delete: the instance is detached once flushed.
        enrollment_id: int = enrollment.id
        old_value: dict[str, Any] = {
            "offering_id": offering_id,
            "student_id": student.student_id,
            "semester": enrollment.semester,
            "academic_year": enrollment.academic_year,
        }

        await self._session.delete(enrollment)
        await self._session.flush()

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UNENROLL,
            entity_type=AuditEntity.ENROLLMENT,
            entity_id=enrollment_id,
            old_value=old_value,
        )

    async def get_roster(
        self,
        *,
        offering_id: int,
        section: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[RosterItem]:
        await self._get_offering_or_404(offering_id)
        stmt: Select[tuple[Enrollment]] = self._roster_stmt(offering_id, section)

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Enrollment] = (
            await self._session.scalars(
                stmt.order_by(Student.last_name, Student.first_name, Student.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[RosterItem](
            items=await self._roster_items(rows),
            total=total,
            page=page,
            size=size,
        )

    @staticmethod
    def _roster_stmt(
        offering_id: int, section: str | None
    ) -> Select[tuple[Enrollment]]:
        stmt: Select[tuple[Enrollment]] = (
            select(Enrollment)
            .join(Student, Enrollment.student_id == Student.id)
            .where(Enrollment.offering_id == offering_id)
        )

        return apply_if(stmt, section, lambda v: Student.section == v)

    async def _roster_items(self, rows: Sequence[Enrollment]) -> list[RosterItem]:
        items: list[RosterItem] = []

        for enrollment in rows:
            student: Student | None = await self._session.get(
                Student, enrollment.student_id
            )

            if student is None:
                continue

            name: str = " ".join(
                part
                for part in (
                    student.first_name,
                    student.middle_name,
                    student.last_name,
                )
                if part
            )
            items.append(
                RosterItem(
                    student_id=student.student_id,
                    name=name,
                    section=student.section,
                    enrolled_at=enrollment.created_at,
                )
            )

        return items

    # -- internals --------------------------------------------------------

    async def _require_program(self, program_id: int) -> None:
        if await self._session.get(Program, program_id) is None:
            raise ProgramNotFoundException(program_id)

    async def _require_year_level(self, program_id: int, year_level_id: int) -> None:
        year_level: YearLevel | None = await self._session.get(YearLevel, year_level_id)

        if year_level is None or year_level.program_id != program_id:
            raise YearLevelNotFoundException(year_level_id, program_id)

    async def _term_weeks(self, offering: CourseOffering) -> int:
        """Session weeks for an offering's (year level, term) — derived (D86).

        `semester` is free text, so an unmatched or orphaned code resolves to
        the shared default rather than raising.
        """
        year_level: YearLevel | None = await self._session.get(
            YearLevel, offering.year_level_id
        )
        structure = year_level.term_structure if year_level is not None else None

        return term_weeks(structure, offering.semester)

    async def _require_no_duplicate_offering(self, payload: OfferingCreate) -> None:
        if (
            await self._offerings.get_by(
                course_id=payload.course_id,
                program_id=payload.program_id,
                semester=payload.semester,
                academic_year=payload.academic_year,
            )
            is not None
        ):
            raise OfferingExistsException(
                payload.course_id,
                payload.program_id,
                payload.semester,
                payload.academic_year,
            )

    async def _get_offering_or_404(self, offering_id: int) -> CourseOffering:
        offering: CourseOffering | None = await self._offerings.get(offering_id)

        if offering is None:
            raise OfferingNotFoundException(offering_id)

        return offering

    async def _require_exact_for_activation(self, offering: CourseOffering) -> None:
        """Block activating an offering whose meetings mismatch the requirement.

        Compared in whole minutes like every other weekly check. Only called
        on the activation transition; deactivation never reaches here.
        """
        course: Course = await self._get_or_404(offering.course_id)
        active: Sequence[OfferingComponent] = await self._active_components(
            offering.id
        )
        total_minutes = sum(
            meeting_minutes(
                row.schedule_days, row.schedule_start_time, row.schedule_end_time
            )
            for row in active
        )
        limit_minutes = int(course.units) * 60
        if int(round(total_minutes)) != limit_minutes:
            raise ScheduleMismatchException(
                round(total_minutes / 60, 2),
                round(limit_minutes / 60, 2),
                course.course_code,
                int(course.units),
            )

    async def _enrollment_count(self, offering_id: int) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.offering_id == offering_id)
            )
            or 0
        )

    async def _to_offering_read(self, offering: CourseOffering) -> OfferingRead:
        """Build the read schema by hand so `enrolled_count` is a real value.

        `model_validate` cannot see derived aggregates (§1.7), and mutating the
        model afterwards would leave a half-filled schema behind.
        """
        components: Sequence[OfferingComponent] = await self._active_components(
            offering.id
        )
        reads: list[ComponentRead] = [
            ComponentRead.model_validate(row) for row in components
        ]

        return OfferingRead(
            id=offering.id,
            course_id=offering.course_id,
            program_id=offering.program_id,
            year_level_id=offering.year_level_id,
            semester=offering.semester,
            academic_year=offering.academic_year,
            sessions_per_week=offering.sessions_per_week,
            semester_weeks=await self._term_weeks(offering),
            schedule_days=offering.schedule_days,
            schedule_start_time=offering.schedule_start_time,
            schedule_end_time=offering.schedule_end_time,
            classroom_name=offering.classroom_name,
            classroom_lat=offering.classroom_lat,
            classroom_lng=offering.classroom_lng,
            default_present_window_minutes=offering.default_present_window_minutes,
            default_late_window_minutes=offering.default_late_window_minutes,
            enrolled_count=await self._enrollment_count(offering.id),
            session_types=sorted({row.session_type for row in components}),
            components=reads,
            is_active=offering.is_active,
            created_at=offering.created_at,
            updated_at=offering.updated_at,
        )

    # -- offering components (D77) --------------------------------------

    async def list_components(self, *, offering_id: int) -> list[ComponentRead]:
        """Active scheduled components of one offering, oldest first."""
        await self._get_offering_or_404(offering_id)

        return [
            ComponentRead.model_validate(row)
            for row in await self._active_components(offering_id)
        ]

    async def create_component(
        self,
        *,
        offering_id: int,
        payload: ComponentCreate,
        actor_id: int | None = None,
    ) -> ComponentRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        # Duplicate reports 409 even when the merged total would also exceed
        # the weekly requirement, so check the unique key before it.
        if (
            await self._components.get_by(
                offering_id=offering.id,
                session_type=payload.session_type.value,
                schedule_days=payload.schedule_days,
                schedule_start_time=payload.schedule_start_time,
            )
            is not None
        ):
            raise ComponentExistsException(offering.id, payload.session_type.value)
        course: Course = await self._get_or_404(offering.course_id)
        existing = await self._active_components(offering_id)
        old_total = sum(
            meeting_minutes(
                row.schedule_days, row.schedule_start_time, row.schedule_end_time
            )
            for row in existing
        )
        new_total = old_total + meeting_minutes(
            payload.schedule_days,
            payload.schedule_start_time,
            payload.schedule_end_time,
        )
        _check_weekly_hours(course, new_total, old_total)
        row: OfferingComponent = await self._insert_component(
            offering=offering, payload=payload
        )
        await self._mirror_single_component(offering)
        await self._sync_sessions_per_week(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering.id,
            new_value=self._component_snapshot(row),
        )

        return ComponentRead.model_validate(row)

    async def update_component(
        self,
        *,
        offering_id: int,
        component_id: int,
        payload: ComponentUpdate,
        actor_id: int | None = None,
    ) -> ComponentRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        row: OfferingComponent = await self._get_component_or_404(
            offering_id, component_id
        )
        changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
        old_value = self._component_snapshot(row)

        # Validate against the merged result, before touching the ORM object —
        # same reason `update_offering` checks the merged schedule window.
        start = changes.get("schedule_start_time", row.schedule_start_time)
        end = changes.get("schedule_end_time", row.schedule_end_time)

        if start is None or end is None or end <= start:
            raise OfferingScheduleWindowException()

        merged_days = changes.get("schedule_days", row.schedule_days)
        # Reshape edits on active rows are unconstrained: a multi-step
        # schedule change (shrink one meeting, add another) necessarily passes
        # through a mismatched total no single write could land exactly on,
        # so per-write enforcement here would freeze exact rows and strand
        # legacy ones (D81). Exactness is enforced where a complete schedule
        # arrives at once (offering creation) and where the total only grows
        # (component add); the red over/short panels stay visible until the
        # reshape converges. Reactivating restores minutes like an add, so it
        # is checked even when the schedule itself is unchanged; deactivating
        # only shrinks the total and never needs the check.
        if not row.is_active and bool(changes.get("is_active", row.is_active)):
            course: Course = await self._get_or_404(offering.course_id)
            existing = await self._active_components(offering_id)
            old_total = sum(
                meeting_minutes(
                    active.schedule_days,
                    active.schedule_start_time,
                    active.schedule_end_time,
                )
                for active in existing
            )
            # The reactivated row was not in the active total.
            new_total = old_total + meeting_minutes(merged_days, start, end)
            _check_weekly_hours(course, new_total, old_total)

        for field, value in changes.items():
            setattr(row, field, value)

        await self._session.flush()
        await self._session.refresh(row)
        await self._mirror_single_component(
            await self._get_offering_or_404(offering_id)
        )
        await self._sync_sessions_per_week(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering_id,
            old_value=old_value,
            new_value=self._component_snapshot(row),
        )

        return ComponentRead.model_validate(row)

    async def archive_component(
        self, *, offering_id: int, component_id: int, actor_id: int | None = None
    ) -> None:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        row: OfferingComponent = await self._get_component_or_404(
            offering_id, component_id
        )
        old_value = self._component_snapshot(row)
        row.is_active = False
        await self._session.flush()
        await self._mirror_single_component(offering)
        await self._sync_sessions_per_week(offering)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.ARCHIVE,
            entity_type=AuditEntity.COURSE_OFFERING,
            entity_id=offering_id,
            old_value=old_value,
            new_value=self._component_snapshot(row),
        )

    async def _insert_component(
        self, *, offering: CourseOffering, payload: ComponentCreate
    ) -> OfferingComponent:
        if (
            await self._components.get_by(
                offering_id=offering.id,
                session_type=payload.session_type.value,
                schedule_days=payload.schedule_days,
                schedule_start_time=payload.schedule_start_time,
            )
            is not None
        ):
            raise ComponentExistsException(offering.id, payload.session_type.value)

        row: OfferingComponent = await self._components.create(
            offering_id=offering.id,
            session_type=payload.session_type.value,
            schedule_days=payload.schedule_days,
            schedule_start_time=payload.schedule_start_time,
            schedule_end_time=payload.schedule_end_time,
            classroom_name=payload.classroom_name,
            classroom_lat=payload.classroom_lat,
            classroom_lng=payload.classroom_lng,
        )

        return row

    async def _active_components(
        self, offering_id: int
    ) -> Sequence[OfferingComponent]:
        return (
            await self._session.scalars(
                select(OfferingComponent)
                .where(
                    OfferingComponent.offering_id == offering_id,
                    OfferingComponent.is_active.is_(True),
                )
                .order_by(OfferingComponent.id)
            )
        ).all()

    async def _sync_sessions_per_week(self, offering: CourseOffering) -> None:
        """Keep `sessions_per_week` equal to the weekly session count (D80).

        One session per meeting day: the distinct day-letter count summed over
        the active components — the same rule as `weeklySessionCount` on the
        frontend. Called after every component mutation so the column the
        risk batch reads never drifts from the meetings. Zero active meetings
        syncs to 0 (internal sync only — the API input floor of 1 still
        applies to client payloads). Flush-only, like `_mirror_single_component`.
        """
        active: Sequence[OfferingComponent] = await self._active_components(
            offering.id
        )
        offering.sessions_per_week = sum(
            distinct_day_count(row.schedule_days) for row in active
        )
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin),
        # so it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(offering)

    async def _mirror_single_component(self, offering: CourseOffering) -> None:
        """Mirror the lone active component onto the offering columns.

        The offering-level schedule/classroom is the legacy display default
        and the session pre-fill fallback. With exactly one active meeting
        it must say the same thing as that meeting, or the UI shows two
        schedules that disagree. With zero or several active meetings there
        is no single truth to mirror, so the columns are left untouched.
        Flush-only, like every other mutation here.
        """
        active: Sequence[OfferingComponent] = await self._active_components(
            offering.id
        )

        if len(active) != 1:
            return

        (only,) = active
        offering.schedule_days = only.schedule_days
        offering.schedule_start_time = only.schedule_start_time
        offering.schedule_end_time = only.schedule_end_time
        offering.classroom_name = only.classroom_name
        offering.classroom_lat = only.classroom_lat
        offering.classroom_lng = only.classroom_lng
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side
        # (TimestampMixin), so it is expired and would raise MissingGreenlet
        # if read synchronously — same hazard `update_offering` guards.
        await self._session.refresh(offering)

    async def _get_component_or_404(
        self, offering_id: int, component_id: int
    ) -> OfferingComponent:
        row: OfferingComponent | None = await self._components.get(component_id)

        if row is None or row.offering_id != offering_id:
            raise ComponentNotFoundException(component_id)

        return row

    @staticmethod
    def _component_snapshot(row: OfferingComponent) -> dict[str, Any]:
        return {
            "offering_id": row.offering_id,
            "session_type": row.session_type,
            "schedule_days": row.schedule_days,
            "schedule_start_time": row.schedule_start_time.isoformat(),
            "schedule_end_time": row.schedule_end_time.isoformat(),
            "classroom_name": row.classroom_name,
            "classroom_lat": row.classroom_lat,
            "classroom_lng": row.classroom_lng,
            "is_active": row.is_active,
        }

    @staticmethod
    def _offering_snapshot(offering: CourseOffering) -> dict[str, Any]:
        return {
            "course_id": offering.course_id,
            "program_id": offering.program_id,
            "year_level_id": offering.year_level_id,
            "semester": offering.semester,
            "academic_year": offering.academic_year,
            "sessions_per_week": offering.sessions_per_week,
            "schedule_days": offering.schedule_days,
            "schedule_start_time": offering.schedule_start_time.isoformat(),
            "schedule_end_time": offering.schedule_end_time.isoformat(),
            "classroom_name": offering.classroom_name,
            "classroom_lat": offering.classroom_lat,
            "classroom_lng": offering.classroom_lng,
            "default_present_window_minutes": offering.default_present_window_minutes,
            "default_late_window_minutes": offering.default_late_window_minutes,
            "is_active": offering.is_active,
        }

    @staticmethod
    def _check_windows(course: Course, present_minutes: int, late_minutes: int) -> None:
        duration_minutes: float = float(course.session_duration_hours) * 60

        if present_minutes + late_minutes > duration_minutes:
            raise WindowsExceedDurationException(
                present_minutes, late_minutes, duration_minutes
            )
