import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

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
from shared.pagination import PaginatedResponse

BULK_CSV_COLUMNS: tuple[str, ...] = (
    "student_id",
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "program_code",
    "year_level",
    "section",
)


@dataclass
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


def parse_enrollment_csv(content: bytes) -> tuple[list[_CsvRow], list[BulkEnrollError]]:
    """Parse the bulk-enroll CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem is
    reported as a BulkEnrollError with its 1-based line number (header = 1).
    """
    try:
        text: str = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [BulkEnrollError(line=1, reason="file is not valid UTF-8")]

    if not text.strip():
        return [], [BulkEnrollError(line=1, reason="empty file")]

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return [], [BulkEnrollError(line=1, reason="missing header row")]

    header: set[str] = {(name or "").strip() for name in reader.fieldnames}
    missing: list = sorted(set(BULK_CSV_COLUMNS) - header)

    if missing:
        return [], [
            BulkEnrollError(line=1, reason=f"missing columns: {', '.join(missing)}")
        ]

    rows: list[_CsvRow] = []
    errors: list[BulkEnrollError] = []

    for lineno, raw in enumerate(reader, start=2):
        cell = lambda key: (raw.get(key) or "").strip()  # noqa: E731

        student_id: str = cell("student_id")

        if not student_id:
            errors.append(BulkEnrollError(line=lineno, reason="missing student_id"))
            continue

        if not cell("first_name") or not cell("last_name") or not cell("email"):
            errors.append(
                BulkEnrollError(
                    line=lineno,
                    reason=f"missing required field for student {student_id}",
                )
            )
            continue

        if not cell("program_code") or not cell("year_level"):
            errors.append(
                BulkEnrollError(
                    line=lineno,
                    reason=f"missing program_code/year_level for student {student_id}",
                )
            )
            continue

        rows.append(
            _CsvRow(
                line=lineno,
                student_id=student_id,
                first_name=cell("first_name"),
                middle_name=cell("middle_name") or None,
                last_name=cell("last_name"),
                email=cell("email"),
                program_code=cell("program_code"),
                year_level=cell("year_level"),
                section=cell("section") or None,
            )
        )

    return rows, errors


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

        program: Program | None = await self._session.get(Program, payload.program_id)

        if program is None:
            raise ProgramNotFoundException(payload.program_id)

        year_level: YearLevel | None = await self._session.get(
            YearLevel, payload.year_level_id
        )

        if year_level is None or year_level.program_id != payload.program_id:
            raise YearLevelNotFoundException(payload.year_level_id, payload.program_id)

        self._check_windows(
            course,
            payload.default_present_window_minutes,
            payload.default_late_window_minutes,
        )

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

        for row in rows:
            student: Student | None = await self._students.get_by(
                student_id=row.student_id
            )

            if student is None:
                errors.append(
                    BulkEnrollError(
                        line=row.line,
                        reason=f"unknown student_id {row.student_id}",
                    )
                )
                continue

            if student.email.lower() != row.email.lower():
                errors.append(
                    BulkEnrollError(
                        line=row.line,
                        reason=f"email mismatch for student {row.student_id}",
                    )
                )
                continue

            if program is not None and row.program_code.upper() != program.code.upper():
                errors.append(
                    BulkEnrollError(
                        line=row.line,
                        reason=f"program_code {row.program_code} does not match offering",
                    )
                )
                continue

            if (
                await self._enrollments.get_by(
                    student_id=student.id,
                    offering_id=offering_id,
                    academic_year=offering.academic_year,
                )
                is not None
            ):
                skipped += 1
                continue

            self._session.add(
                Enrollment(
                    student_id=student.id,
                    offering_id=offering_id,
                    semester=offering.semester,
                    academic_year=offering.academic_year,
                )
            )

            if row.section is not None and row.section != student.section:
                student.section = row.section

            enrolled += 1

        await self._session.flush()

        errors.sort(key=lambda e: e.line)

        return BulkEnrollResult(enrolled=enrolled, skipped=skipped, errors=errors)

    async def get_roster(
        self,
        *,
        offering_id: int,
        section: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[RosterItem]:
        await self._get_offering_or_404(offering_id)

        stmt: Select[tuple[Enrollment]] = (
            select(Enrollment)
            .join(Student, Enrollment.student_id == Student.id)
            .where(Enrollment.offering_id == offering_id)
        )

        if section is not None:
            stmt = stmt.where(Student.section == section)

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

        return PaginatedResponse[RosterItem](
            items=items, total=total, page=page, size=size
        )

    # -- internals --------------------------------------------------------

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
        read = OfferingRead.model_validate(offering)
        read.enrolled_count = await self._enrollment_count(offering.id)

        return read

    @staticmethod
    def _check_windows(course: Course, present_minutes: int, late_minutes: int) -> None:
        duration_minutes: float = float(course.session_duration_hours) * 60

        if present_minutes + late_minutes > duration_minutes:
            raise WindowsExceedDurationException(
                present_minutes, late_minutes, duration_minutes
            )
