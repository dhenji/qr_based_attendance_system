from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.attendance.model import Attendance
from features.enrollment.model import Enrollment
from features.excuse.model import ExcuseRequest
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.exceptions import (
    StudentEmailExistsException,
    StudentHasRecordsException,
    StudentIdExistsException,
    StudentNotArchivedException,
    StudentNotFoundException,
    YearLevelMismatchException,
)
from features.student.model import Student
from features.student.schema import (
    StudentCreate,
    StudentDetail,
    StudentImportError,
    StudentImportResult,
    StudentRead,
    StudentUpdate,
)
from shared.base import BaseCRUD
from shared.csv_import import is_valid_email, parse_csv
from shared.pagination import PaginatedResponse

ROSTER_CSV_COLUMNS: tuple[str, ...] = (
    "student_id",
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "program_code",
    "section",
    "year_level",
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


def parse_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[StudentImportError]]:
    """Parse the roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem is
    reported as a StudentImportError with its 1-based line number (header = 1).
    Values are normalized the same way as StudentCreate (student_id upper,
    email lower) so duplicate detection agrees with single-create.
    """
    raw_rows, structural_errors = parse_csv(content, ROSTER_CSV_COLUMNS)

    errors: list[StudentImportError] = [
        StudentImportError(line=e.line, reason=e.reason)
        for e in structural_errors
    ]

    if structural_errors:
        return [], errors

    rows: list[_RosterRow] = []

    for raw in raw_rows:
        lineno = raw.line
        cell = raw.values.get

        student_id: str = (cell("student_id") or "").strip().upper()

        if not student_id:
            errors.append(
                StudentImportError(line=lineno, reason="missing student_id")
            )
            continue

        first_name = (cell("first_name") or "").strip()
        last_name = (cell("last_name") or "").strip()
        email = (cell("email") or "").strip().lower()

        if not first_name or not last_name or not email:
            errors.append(
                StudentImportError(
                    line=lineno,
                    reason=f"missing required field for student {student_id}",
                )
            )
            continue

        if not is_valid_email(email):
            errors.append(
                StudentImportError(
                    line=lineno,
                    reason=f"invalid email for student {student_id}",
                )
            )
            continue

        program_code = (cell("program_code") or "").strip().upper()
        year_level = (cell("year_level") or "").strip()

        if not program_code or not year_level:
            errors.append(
                StudentImportError(
                    line=lineno,
                    reason=f"missing program_code/year_level for student {student_id}",
                )
            )
            continue

        rows.append(
            _RosterRow(
                line=lineno,
                student_id=student_id,
                first_name=first_name,
                middle_name=(cell("middle_name") or "").strip() or None,
                last_name=last_name,
                email=email,
                program_code=program_code,
                section=(cell("section") or "").strip() or None,
                year_level=year_level,
            )
        )

    return rows, errors


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

        is_active: bool | None = values.pop("is_active", None)
        program_id: int | None = values.pop("program_id", None)
        year_level_id: int | None = values.pop("year_level_id", None)

        if "email" in values and values["email"] != student.email:
            existing: Student | None = await self._students.get_by(email=values["email"])

            if existing is not None and existing.id != student.id:
                raise StudentEmailExistsException(values["email"])

        for field, value in values.items():
            setattr(student, field, value)

        if program_id is not None or year_level_id is not None:
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

        if is_active is False:
            return await self.archive(student_id=student.id)

        if is_active is True:
            student.is_active = True

        await self._session.flush()

        return await self._to_read(student)

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

    async def import_roster(self, *, content: bytes) -> StudentImportResult:
        """Create NEW roster students from a CSV upload.

        Unlike offering bulk-enroll (which attaches existing students),
        every valid row inserts a student. Rows whose student_id or email
        already exists — in the database or earlier in the same file — are
        counted as duplicates, not errors.
        """
        rows, errors = parse_roster_csv(content)
        imported = 0
        duplicates = 0
        seen_ids: set[str] = set()
        seen_emails: set[str] = set()

        for row in rows:
            if (
                row.student_id in seen_ids
                or row.email in seen_emails
                or await self._students.get_by(student_id=row.student_id)
                is not None
                or await self._students.get_by(email=row.email) is not None
            ):
                duplicates += 1
                seen_ids.add(row.student_id)
                seen_emails.add(row.email)
                continue

            seen_ids.add(row.student_id)
            seen_emails.add(row.email)

            program: Program | None = await self._programs.get_by(
                code=row.program_code
            )

            if program is None:
                errors.append(
                    StudentImportError(
                        line=row.line,
                        reason=f"unknown program_code {row.program_code}",
                    )
                )
                continue

            year_level: YearLevel | None = await self._resolve_import_year_level(
                program.id, row.year_level
            )

            if year_level is None:
                errors.append(
                    StudentImportError(
                        line=row.line,
                        reason=f"unknown year_level {row.year_level} for program {row.program_code}",
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
        year_level: YearLevel | None = await self._session.get(
            YearLevel, year_level_id
        )

        if year_level is None:
            raise YearLevelNotFoundException(year_level_id)

        return year_level

    async def _resolve_cohort(
        self, year_level_id: int, program_id: int
    ) -> tuple[YearLevel, Program]:
        year_level: YearLevel | None = await self._session.get(
            YearLevel, year_level_id
        )

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
        program: Program | None = await self._session.get(Program, year_level.program_id)

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
