from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password, verify_password
from features.attendance.model import Attendance
from features.course.model import Course, CourseOffering
from features.course_professor.model import CourseProfessor
from features.enrollment.model import Enrollment
from features.excuse.model import ExcuseRequest
from features.professor.model import Professor
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.exceptions import (
    CurrentPasswordInvalidException,
    FaceEmbeddingNotFoundException,
    StudentEmailExistsException,
    StudentHasRecordsException,
    StudentIdExistsException,
    StudentNotArchivedException,
    StudentNotFoundException,
    YearLevelMismatchException,
)
from features.student.model import Student
from features.student.schema import (
    ChangePasswordRequest,
    FaceEmbeddingResponse,
    ScheduleItem,
    ScheduleResponse,
    StudentCreate,
    StudentDetail,
    StudentImportError,
    StudentImportResult,
    StudentRead,
    StudentUpdate,
)
from shared.base import BaseCRUD
from shared.cache import get_face_embedding_cached
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
    strip_lower,
    strip_upper,
)
from shared.pagination import PaginatedResponse

ROSTER_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn(
        "student_id", normalize=strip_upper, required_reason="missing student_id"
    ),
    CsvColumn("first_name"),
    CsvColumn("middle_name"),
    CsvColumn("last_name"),
    CsvColumn("email", normalize=strip_lower),
    CsvColumn("program_code", normalize=strip_upper),
    CsvColumn("section"),
    CsvColumn("year_level"),
)

ROSTER_CSV_SCHEMA = CsvSchema(
    columns=ROSTER_CSV_COLUMNS,
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


@dataclass
class _RosterRow:
    line: int
    student_id: str
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    program_code: str
    section: str | None
    year_level: str


def _to_roster_row(raw: CsvRow) -> _RosterRow:
    values: dict[str, str] = raw.values

    return _RosterRow(
        line=raw.line,
        student_id=values["student_id"],
        first_name=values["first_name"],
        middle_name=values["middle_name"] or None,
        last_name=values["last_name"],
        email=values["email"],
        program_code=values["program_code"],
        section=values["section"] or None,
        year_level=values["year_level"],
    )


def parse_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[StudentImportError]]:
    """Parse the roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem is
    reported as a StudentImportError with its 1-based line number (header = 1).
    Values are normalized the same way as StudentCreate (student_id upper,
    email lower) so duplicate detection agrees with single-create.
    """
    rows, errors = parse_import_csv(
        content,
        ROSTER_CSV_SCHEMA,
        error=lambda line, reason: StudentImportError(line=line, reason=reason),
    )

    return [_to_roster_row(row) for row in rows], errors


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)
        self._programs: BaseCRUD[Program] = BaseCRUD(Program, session)
        self._years: BaseCRUD[YearLevel] = BaseCRUD(YearLevel, session)

    async def create(self, *, payload: StudentCreate) -> StudentRead:
        if await self._students.get_by(student_id=payload.student_id) is not None:
            raise StudentIdExistsException(payload.student_id)

        if await self._students.get_by(email=payload.email) is not None:
            raise StudentEmailExistsException(payload.email)

        year_level, _ = await self._resolve_cohort(
            payload.year_level_id, payload.program_id
        )

        student: Student = await self._students.create(
            student_id=payload.student_id,
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            email=payload.email,
            year_level_id=year_level.id,
            section=payload.section,
        )

        return await self._to_read(student)

    async def get(self, *, student_id: int) -> StudentDetail:
        return await self._to_detail(await self._get_or_404(student_id))

    async def get_profile(self, *, user_id: int) -> StudentDetail:
        """Get the student profile for the authenticated user.

        Resolves the student by user_id (from the auth token) and returns
        the full detail including face enrollment metadata and scan count.
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        return await self._to_detail(student)

    async def get_face_embedding(
        self, *, user_id: int, current_version: int = 0
    ) -> FaceEmbeddingResponse | None:
        """Return the student's embedding if the client copy is stale.

        Return `None` when the client is current (router maps to 204).
        Raises 404 when the identity is missing or has no blob stored.
        """

        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        blob: bytes | None = await get_face_embedding_cached(self._session, student.id)

        if blob is None:
            raise FaceEmbeddingNotFoundException(user_id)

        server_version: int = student.face_embedding_version or 0

        if current_version >= server_version:
            return None

        return FaceEmbeddingResponse(
            version=server_version, embedding=base64.b64encode(blob).decode("ascii")
        )

    async def get_schedule(self, *, user_id: int) -> ScheduleResponse:
        """Enrolled offerings with schedule, classroom, and professor name.

        Active offerings only (`CourseOffering.is_active`), stable
        `offering_id ASC` order (presentation sorting stays frontend-side).
        Professor names resolve to the current primary assignment, else the
        latest current assignment, else None. Read-only: no rows written.
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None:
            raise StudentNotFoundException(user_id)

        rows = (
            await self._session.execute(
                select(
                    CourseOffering.id,
                    CourseOffering.course_id,
                    Course.course_code,
                    Course.course_name,
                    Program.code,
                    YearLevel.label,
                    CourseOffering.semester,
                    CourseOffering.schedule_days,
                    CourseOffering.schedule_start_time,
                    CourseOffering.schedule_end_time,
                    CourseOffering.classroom_name,
                )
                .select_from(Enrollment)
                .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
                .join(Course, Course.id == CourseOffering.course_id)
                .join(Program, Program.id == CourseOffering.program_id)
                .join(YearLevel, YearLevel.id == CourseOffering.year_level_id)
                .where(
                    Enrollment.student_id == student.id,
                    CourseOffering.is_active.is_(True),
                )
                .order_by(CourseOffering.id.asc())
            )
        ).all()

        names: dict[int, str] = await self._schedule_professor_names(
            [row[0] for row in rows]
        )

        return ScheduleResponse(
            offerings=[
                ScheduleItem(
                    offering_id=offering_id,
                    course_id=course_id,
                    course_code=course_code,
                    course_name=course_name,
                    program_code=program_code,
                    year_level_label=year_level_label,
                    semester=semester,
                    schedule_days=schedule_days,
                    schedule_start_time=schedule_start_time,
                    schedule_end_time=schedule_end_time,
                    classroom_name=classroom_name,
                    professor_name=names.get(offering_id),
                )
                for (
                    offering_id,
                    course_id,
                    course_code,
                    course_name,
                    program_code,
                    year_level_label,
                    semester,
                    schedule_days,
                    schedule_start_time,
                    schedule_end_time,
                    classroom_name,
                ) in rows
            ]
        )

    async def _schedule_professor_names(
        self, offering_ids: list[int]
    ) -> dict[int, str]:
        """Current professor display name per offering (batched, one query).

        Keeps only assignments whose effective window covers today, then
        picks primary first, latest `effective_from` on ties — mirroring
        `ProfessorService._assigned_offerings`.
        """
        if not offering_ids:
            return {}

        today: date = date.today()
        prof_rows = (
            await self._session.execute(
                select(
                    CourseProfessor.offering_id,
                    Professor.first_name,
                    Professor.last_name,
                    CourseProfessor.is_primary,
                    CourseProfessor.effective_from,
                )
                .join(Professor, Professor.id == CourseProfessor.professor_id)
                .where(
                    CourseProfessor.offering_id.in_(offering_ids),
                    CourseProfessor.effective_from <= today,
                    or_(
                        CourseProfessor.effective_to.is_(None),
                        CourseProfessor.effective_to >= today,
                    ),
                )
            )
        ).all()

        ranked: dict[int, tuple[tuple[bool, Any], str]] = {}

        for offering_id, first_name, last_name, is_primary, effective_from in prof_rows:
            key: tuple[bool, Any] = (bool(is_primary), effective_from)
            current = ranked.get(offering_id)

            if current is None or key > current[0]:
                ranked[offering_id] = (key, f"{first_name} {last_name}")

        return {offering_id: name for offering_id, (_, name) in ranked.items()}

    async def list(
        self,
        *,
        search: str | None,
        program_id: int | None,
        year_level_id: int | None,
        section: str | None,
        is_active: bool | None,
        sort_by: str | None,
        sort_dir: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[StudentRead]:
        stmt: Select[tuple[Student]] = select(Student)

        if year_level_id is not None:
            stmt = stmt.where(Student.year_level_id == year_level_id)

        if program_id is not None:
            stmt = stmt.where(
                Student.year_level_id.in_(
                    select(YearLevel.id).where(YearLevel.program_id == program_id)
                )
            )

        if section is not None:
            stmt = stmt.where(Student.section == section)

        if is_active is not None:
            stmt = stmt.where(Student.is_active == is_active)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Student.student_id.ilike(term),
                    Student.first_name.ilike(term),
                    Student.middle_name.ilike(term),
                    Student.last_name.ilike(term),
                    Student.email.ilike(term),
                )
            )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Student] = (
            await self._session.scalars(
                self._apply_order(stmt, sort_by=sort_by, sort_dir=sort_dir)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[StudentRead](
            items=[await self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def update(self, *, student_id: int, payload: StudentUpdate) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        values: dict[str, Any] = payload.model_dump(exclude_unset=True)

        # Extract cohort fields for joint validation
        program_id: int | None = values.pop("program_id", None)
        year_level_id: int | None = values.pop("year_level_id", None)

        for field, value in values.items():
            if handler := self._FIELD_HANDLERS.get(field):
                await handler(self, student, value, student_id)
            else:
                setattr(student, field, value)

        if program_id is not None or year_level_id is not None:
            await self._resolve_and_set_cohort(student, program_id, year_level_id)

        await self._session.flush()

        return await self._to_read(student)

    async def _handle_email(
        self, student: Student, value: str, student_id: int
    ) -> None:
        if value != student.email:
            existing: Student | None = await self._students.get_by(email=value)
            if existing is not None and existing.id != student.id:
                raise StudentEmailExistsException(value)
        student.email = value

    async def _handle_is_active(
        self, student: Student, value: bool, student_id: int
    ) -> None:
        if value is False:
            await self.archive(student_id=student.id)
        else:
            student.is_active = True

    async def _resolve_and_set_cohort(
        self, student: Student, program_id: int | None, year_level_id: int | None
    ) -> None:
        target_program: int = (
            program_id
            if program_id is not None
            else (await self._year_level(student.year_level_id)).program_id
        )
        target_year: int = (
            year_level_id if year_level_id is not None else student.year_level_id
        )
        year_level, _ = await self._resolve_cohort(target_year, target_program)
        student.year_level_id = year_level.id

    _FIELD_HANDLERS: dict[str, Callable] = {
        "email": _handle_email,
        "is_active": _handle_is_active,
    }

    async def archive(self, *, student_id: int) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        student.is_active = False
        # Face revocation: an archived identity must not stay matchable.
        student.face_embedding = None
        student.face_enrolled_at = None
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._session.flush()

        return await self._to_read(student)

    async def reactivate(self, *, student_id: int) -> StudentRead:
        student: Student = await self._get_or_404(student_id)
        student.is_active = True
        await self._session.flush()

        return await self._to_read(student)

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> None:
        """Change the student's password.

        Validates the current password against the linked User record,
        then updates the hash and clears must_change_password.
        """
        student: Student | None = await self._students.get_by(user_id=user_id)

        if student is None or student.user is None:
            raise StudentNotFoundException(user_id)

        if not verify_password(current_password, student.user.password_hash):
            raise CurrentPasswordInvalidException()

        student.user.password_hash = hash_password(new_password)
        student.user.must_change_password = False

        await self._session.flush()

    async def import_roster(self, *, content: bytes) -> StudentImportResult:
        """Create NEW roster students from a CSV upload.

        Unlike offering bulk-enroll (which attaches existing students),
        every valid row inserts a student. Rows whose student_id or email
        already exists — in the database or earlier in the same file — are
        counted as duplicates, not errors.
        """
        rows, parse_errors = parse_roster_csv(content)
        imported = 0
        duplicates = 0
        seen_ids: set[str] = set()
        seen_emails: set[str] = set()
        errors: list[StudentImportError] = list(parse_errors)

        for row in rows:
            is_duplicate, error = await self._validate_import_row(
                row, seen_ids, seen_emails
            )
            if is_duplicate:
                duplicates += 1
                seen_ids.add(row.student_id)
                seen_emails.add(row.email)
                continue
            if error:
                errors.append(error)
                continue

            seen_ids.add(row.student_id)
            seen_emails.add(row.email)

            program = await self._programs.get_by(code=row.program_code)

            if program is None:
                errors.append(
                    StudentImportError(
                        line=row.line,
                        reason=f"unknown program_code {row.program_code}",
                    )
                )
                continue

            year_level = await self._resolve_import_year_level(
                program.id, row.year_level
            )

            if year_level is None:
                errors.append(
                    StudentImportError(
                        line=row.line,
                        reason=(
                            f"unknown year_level {row.year_level} "
                            f"for program {row.program_code}"
                        ),
                    )
                )
                continue

            self._session.add(
                Student(
                    student_id=row.student_id,
                    first_name=row.first_name,
                    middle_name=row.middle_name,
                    last_name=row.last_name,
                    email=row.email,
                    year_level_id=year_level.id,
                    section=row.section,
                )
            )
            imported += 1

        await self._session.flush()

        errors.sort(key=lambda e: e.line)

        return StudentImportResult(
            imported=imported, duplicates=duplicates, errors=errors
        )

    async def _validate_import_row(
        self,
        row: _RosterRow,
        seen_ids: set[str],
        seen_emails: set[str],
    ) -> tuple[bool, StudentImportError | None]:
        """Validate a single import row. Returns (is_duplicate, error)."""

        if (
            row.student_id in seen_ids
            or row.email in seen_emails
            or await self._students.get_by(student_id=row.student_id) is not None
            or await self._students.get_by(email=row.email) is not None
        ):
            return True, None

        return False, None

    async def hard_delete(self, *, student_id: int) -> None:
        """Permanently delete an archived student with no referencing rows."""
        student: Student = await self._get_or_404(student_id)

        if student.is_active:
            raise StudentNotArchivedException(student.id)

        for model in (Enrollment, Attendance, ExcuseRequest):
            count: int = (
                await self._session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.student_id == student.id)
                )
                or 0
            )

            if count:
                raise StudentHasRecordsException(student.id)

        await self._session.delete(student)
        await self._session.flush()

    async def _get_or_404(self, student_id: int) -> Student:
        student: Student | None = await self._students.get(student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        return student

    async def _year_level(self, year_level_id: int) -> YearLevel:
        year_level: YearLevel | None = await self._session.get(YearLevel, year_level_id)

        if year_level is None:
            raise YearLevelNotFoundException(year_level_id)

        return year_level

    async def _resolve_cohort(
        self, year_level_id: int, program_id: int
    ) -> tuple[YearLevel, Program]:
        year_level: YearLevel | None = await self._session.get(YearLevel, year_level_id)

        if year_level is None:
            raise YearLevelNotFoundException(year_level_id, program_id)

        program: Program | None = await self._session.get(Program, program_id)

        if program is None:
            raise ProgramNotFoundException(program_id)

        if year_level.program_id != program_id:
            raise YearLevelMismatchException(year_level_id, program_id)

        return year_level, program

    async def _resolve_import_year_level(
        self, program_id: int, raw: str
    ) -> YearLevel | None:
        """Match a CSV year_level cell to a YearLevel of the program.

        Accepts a year_number ("1") or a label ("1st Year",
        case-insensitive). Returns None when nothing matches so the caller
        can report a per-line error.
        """
        levels: Sequence[YearLevel] = await self._years.list(program_id=program_id)
        text: str = raw.strip()

        if text.isdigit():
            for level in levels:
                if level.year_number == int(text):
                    return level

            return None

        lowered: str = text.lower()

        for level in levels:
            if level.label.lower() == lowered:
                return level

        return None

    async def _scan_count(self, student_pk: int) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(Attendance.student_id == student_pk)
            )
            or 0
        )

    async def _to_read(self, student: Student) -> StudentRead:
        year_level: YearLevel = await self._year_level(student.year_level_id)
        program: Program | None = await self._session.get(
            Program, year_level.program_id
        )

        return StudentRead(
            id=student.id,
            student_id=student.student_id,
            first_name=student.first_name,
            middle_name=student.middle_name,
            last_name=student.last_name,
            email=student.email,
            program_code=program.code if program is not None else "",
            year_level_label=year_level.label,
            section=student.section,
            is_active=student.is_active,
            face_enrolled=student.face_embedding is not None,
            created_at=student.created_at,
            scan_count=await self._scan_count(student.id),
        )

    async def _to_detail(self, student: Student) -> StudentDetail:
        read: StudentRead = await self._to_read(student)

        return StudentDetail(
            **read.model_dump(),
            face_enrolled_at=student.face_enrolled_at,
            face_embedding_version=student.face_embedding_version or 0,
        )

    @staticmethod
    def _apply_order(
        stmt: Select[tuple[Student]], *, sort_by: str | None, sort_dir: str | None
    ) -> Select[tuple[Student]]:
        direction: str = (sort_dir or "asc").lower()
        desc: bool = direction == "desc"

        def _order(*columns: Any) -> Any:
            ordered = [col.desc() if desc else col.asc() for col in columns]
            return stmt.order_by(*ordered, Student.id.asc())

        if sort_by == "last_name":
            return _order(Student.last_name, Student.first_name)

        if sort_by == "student_id":
            return _order(Student.student_id)

        if sort_by == "created_at":
            return _order(Student.created_at)

        return stmt.order_by(Student.id)
