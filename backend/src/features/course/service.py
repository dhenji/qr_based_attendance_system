from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.exceptions import (
    CourseCodeExistsException,
    CourseNotFoundException,
    OfferingAssignmentNotFoundException,
    OfferingExistsException,
    OfferingNotFoundException,
    WindowsExceedDurationException,
)
from features.course.model import Course, CourseOffering
from features.course.schema import (
    AssignmentRead,
    BulkEnrollError,
    BulkEnrollResult,
    CourseCreate,
    CourseRead,
    CourseUpdate,
    OfferingCreate,
    OfferingRead,
    OfferingUpdate,
    ProfessorAssignment,
    RosterItem,
)
from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor
from features.course_professor.service import CourseProfessorService
from features.enrollment.model import Enrollment
from features.professor.exceptions import ProfessorNotFoundException
from features.professor.model import Professor
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.model import Student
from shared.base import BaseCRUD
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
)
from shared.pagination import PaginatedResponse
from shared.query import apply_if

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


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._courses: BaseCRUD[Course] = BaseCRUD(Course, session)
        self._offerings: BaseCRUD[CourseOffering] = BaseCRUD(CourseOffering, session)
        self._enrollments: BaseCRUD[Enrollment] = BaseCRUD(Enrollment, session)
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)

    # -- course template CRUD (unchanged) -------------------------------

    async def create(self, *, payload: CourseCreate) -> CourseRead:
        if await self._courses.get_by(course_code=payload.course_code) is not None:
            raise CourseCodeExistsException(payload.course_code)

        course: Course = await self._courses.create(
            course_code=payload.course_code,
            course_name=payload.course_name,
            units=payload.units,
            session_duration_hours=payload.session_duration_hours,
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

    async def update(self, *, course_id: int, payload: CourseUpdate) -> CourseRead:
        course: Course = await self._get_or_404(course_id)

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

        return CourseRead.model_validate(course)

    async def archive(self, *, course_id: int) -> None:
        course: Course = await self._get_or_404(course_id)
        course.is_active = False
        await self._session.flush()

    async def _get_or_404(self, course_id: int) -> Course:
        course: Course | None = await self._courses.get(course_id)

        if course is None:
            raise CourseNotFoundException(course_id)

        return course

    # -- offering CRUD ---------------------------------------------------

    async def create_offering(self, *, payload: OfferingCreate) -> OfferingRead:
        course: Course = await self._get_or_404(payload.course_id)
        await self._require_program(payload.program_id)
        await self._require_year_level(payload.program_id, payload.year_level_id)
        self._check_windows(
            course,
            payload.default_present_window_minutes,
            payload.default_late_window_minutes,
        )
        await self._require_no_duplicate_offering(payload)

        offering: CourseOffering = await self._offerings.create(**payload.model_dump())

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
        self, *, offering_id: int, payload: OfferingUpdate
    ) -> OfferingRead:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(offering, field, value)

        start = offering.schedule_start_time
        end = offering.schedule_end_time

        if end <= start:
            raise ValueError("schedule_end_time must be after schedule_start_time")

        course: Course = await self._get_or_404(offering.course_id)
        self._check_windows(
            course,
            offering.default_present_window_minutes,
            offering.default_late_window_minutes,
        )

        await self._session.flush()

        return await self._to_offering_read(offering)

    async def archive_offering(self, *, offering_id: int) -> None:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        offering.is_active = False
        await self._session.flush()

    # -- professor assignments -------------------------------------------

    async def list_assignments(self, *, offering_id: int) -> Sequence[AssignmentRead]:
        await self._get_offering_or_404(offering_id)

        rows: Sequence[CourseProfessor] = (
            await self._session.scalars(
                select(CourseProfessor)
                .where(CourseProfessor.offering_id == offering_id)
                .order_by(CourseProfessor.effective_from)
            )
        ).all()

        return [AssignmentRead.model_validate(row) for row in rows]

    async def assign_professor(
        self,
        *,
        offering_id: int,
        payload: ProfessorAssignment,
        assigned_by: int,
    ) -> AssignmentRead:
        await self._get_offering_or_404(offering_id)

        if await self._session.get(Professor, payload.professor_id) is None:
            raise ProfessorNotFoundException(payload.professor_id)

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

        record = CourseProfessor(
            offering_id=offering_id,
            professor_id=payload.professor_id,
            is_primary=payload.is_primary,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            semester=payload.semester,
            assigned_by=assigned_by,
        )
        self._session.add(record)
        await self._session.flush()

        return AssignmentRead.model_validate(record)

    async def remove_professor(self, *, offering_id: int, professor_id: int) -> date:
        await self._get_offering_or_404(offering_id)

        today: date = date.today()
        row: CourseProfessor | None = (
            await self._session.scalars(
                select(CourseProfessor)
                .where(
                    CourseProfessor.offering_id == offering_id,
                    CourseProfessor.professor_id == professor_id,
                    (
                        (CourseProfessor.effective_to.is_(None))
                        | (CourseProfessor.effective_to >= today)
                    ),
                )
                .order_by(CourseProfessor.effective_from.desc())
            )
        ).one_or_none()

        if row is None:
            raise OfferingAssignmentNotFoundException(offering_id, professor_id)

        row.effective_to = today
        await self._session.flush()

        return today

    # -- bulk enroll + roster --------------------------------------------

    async def bulk_enroll(
        self, *, offering_id: int, content: bytes
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
        return OfferingRead(
            id=offering.id,
            course_id=offering.course_id,
            program_id=offering.program_id,
            year_level_id=offering.year_level_id,
            semester=offering.semester,
            academic_year=offering.academic_year,
            sessions_per_week=offering.sessions_per_week,
            semester_weeks=offering.semester_weeks,
            schedule_days=offering.schedule_days,
            schedule_start_time=offering.schedule_start_time,
            schedule_end_time=offering.schedule_end_time,
            classroom_name=offering.classroom_name,
            classroom_lat=offering.classroom_lat,
            classroom_lng=offering.classroom_lng,
            default_present_window_minutes=offering.default_present_window_minutes,
            default_late_window_minutes=offering.default_late_window_minutes,
            enrolled_count=await self._enrollment_count(offering.id),
            is_active=offering.is_active,
            created_at=offering.created_at,
            updated_at=offering.updated_at,
        )

    @staticmethod
    def _check_windows(course: Course, present_minutes: int, late_minutes: int) -> None:
        duration_minutes: float = float(course.session_duration_hours) * 60

        if present_minutes + late_minutes > duration_minutes:
            raise WindowsExceedDurationException(
                present_minutes, late_minutes, duration_minutes
            )
