from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Row, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.exceptions import OfferingNotFoundException
from features.course.model import Course, CourseOffering
from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor
from features.course_professor.service import CourseProfessorService
from features.enrollment.model import Enrollment
from features.professor.exceptions import (
    ProfessorEmailExistsException,
    ProfessorHasRecordsException,
    ProfessorNotArchivedException,
    ProfessorNotFoundException,
)
from features.professor.model import Professor
from features.professor.schema import (
    AssignedCourse,
    AssignedOfferingItem,
    ProfessorCreate,
    ProfessorDetail,
    ProfessorImportError,
    ProfessorImportResult,
    ProfessorProfileRead,
    ProfessorRead,
    ProfessorUpdate,
)
from features.program.model import Program, YearLevel
from features.session.model import Session
from features.student.model import Student
from shared.base import BaseCRUD
from shared.csv_import import (
    CsvColumn,
    CsvEmailCheck,
    CsvGroup,
    CsvRow,
    CsvSchema,
    parse_import_csv,
    strip_lower,
)
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
)

ROSTER_CSV_COLUMNS: tuple[CsvColumn, ...] = (
    CsvColumn("first_name"),
    CsvColumn("middle_name"),
    CsvColumn("last_name"),
    CsvColumn("email", normalize=strip_lower),
    CsvColumn("department"),
)

ROSTER_CSV_SCHEMA = CsvSchema(
    columns=ROSTER_CSV_COLUMNS,
    subject="professor",
    subject_column="email",
    subject_fallback="on line",
    checks=(
        CsvGroup(
            columns=("first_name", "last_name", "email"),
            reason="missing required field for {subject} {key}",
        ),
        CsvEmailCheck("email", "invalid email for {subject} {key}"),
    ),
)


@dataclass
class _RosterRow:
    line: int
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    department: str | None


def _to_roster_row(raw: CsvRow) -> _RosterRow:
    values: dict[str, str] = raw.values

    return _RosterRow(
        line=raw.line,
        first_name=values["first_name"],
        middle_name=values["middle_name"] or None,
        last_name=values["last_name"],
        email=values["email"],
        department=values["department"] or None,
    )


def parse_professor_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[ProfessorImportError]]:
    """Parse the professor roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem
    is reported as a ProfessorImportError with its 1-based line number
    (header = 1). Emails are lowercased so duplicate detection agrees with
    single-create.
    """
    rows, errors = parse_import_csv(
        content,
        ROSTER_CSV_SCHEMA,
        error=lambda line, reason: ProfessorImportError(line=line, reason=reason),
    )

    return [_to_roster_row(row) for row in rows], errors


class ProfessorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._professors: BaseCRUD[Professor] = BaseCRUD(Professor, session)

    async def create(
        self, *, payload: ProfessorCreate, assigned_by: int
    ) -> ProfessorRead:
        if await self._professors.get_by(email=payload.email) is not None:
            raise ProfessorEmailExistsException(payload.email)

        professor: Professor = await self._professors.create(
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            email=payload.email,
            department=payload.department,
        )

        for offering_id in dict.fromkeys(payload.courses):
            await self._assign_offering(
                professor_id=professor.id,
                offering_id=offering_id,
                assigned_by=assigned_by,
            )

        return await self._to_read(professor)

    async def get(self, *, professor_id: int) -> ProfessorDetail:
        professor: Professor = await self._get_or_404(professor_id)
        read: ProfessorRead = await self._to_read(professor)

        return ProfessorDetail(**read.model_dump())

    async def list(
        self,
        *,
        search: str | None,
        department: str | None,
        is_active: bool | None,
        sort_by: str | None,
        sort_dir: str | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[ProfessorRead]:
        stmt: Select[tuple[Professor]] = select(Professor)

        if department is not None:
            stmt = stmt.where(Professor.department == department)

        if is_active is not None:
            stmt = stmt.where(Professor.is_active == is_active)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Professor.first_name.ilike(term),
                    Professor.middle_name.ilike(term),
                    Professor.last_name.ilike(term),
                    Professor.email.ilike(term),
                )
            )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Professor] = (
            await self._session.scalars(
                self._apply_order(stmt, sort_by=sort_by, sort_dir=sort_dir)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[ProfessorRead](
            items=[await self._to_read(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def update(
        self, *, professor_id: int, payload: ProfessorUpdate, assigned_by: int
    ) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        values: dict[str, Any] = payload.model_dump(exclude_unset=True)

        is_active: bool | None = values.pop("is_active", None)
        courses: list[int] | None = values.pop("courses", None)

        if "email" in values and values["email"] != professor.email:
            existing: Professor | None = await self._professors.get_by(
                email=values["email"]
            )

            if existing is not None and existing.id != professor.id:
                raise ProfessorEmailExistsException(values["email"])

        for field, value in values.items():
            setattr(professor, field, value)

        if is_active is False:
            await self._archive_row(professor)
        elif is_active is True:
            professor.is_active = True

        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(professor)

        if courses is not None:
            await self._replace_assignments(
                professor_id=professor.id,
                offering_ids=courses,
                assigned_by=assigned_by,
            )

        return await self._to_read(professor)

    async def archive(self, *, professor_id: int) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        await self._archive_row(professor)
        # _archive_row flushes, which expires the server-side `updated_at`.
        await self._session.refresh(professor)

        return await self._to_read(professor)

    async def reactivate(self, *, professor_id: int) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        professor.is_active = True
        await self._session.flush()
        # Reload after the flush: `updated_at` is server-side (TimestampMixin), so
        # it is expired and would raise MissingGreenlet if read synchronously.
        await self._session.refresh(professor)

        return await self._to_read(professor)

    async def import_roster(self, *, content: bytes) -> ProfessorImportResult:
        """Create NEW professor records from a CSV upload.

        Rows whose email already exists — in the database or earlier in the
        same file — are counted as duplicates, not errors. No user rows are
        created: imports stay Unclaimed until self-registration.
        """
        rows, errors = parse_professor_roster_csv(content)
        imported = 0
        duplicates = 0
        seen_emails: set[str] = set()

        for row in rows:
            if (
                row.email in seen_emails
                or await self._professors.get_by(email=row.email) is not None
            ):
                duplicates += 1
                seen_emails.add(row.email)
                continue

            seen_emails.add(row.email)
            self._session.add(
                Professor(
                    first_name=row.first_name,
                    middle_name=row.middle_name,
                    last_name=row.last_name,
                    email=row.email,
                    department=row.department,
                )
            )
            imported += 1

        await self._session.flush()

        errors.sort(key=lambda e: e.line)

        return ProfessorImportResult(
            imported=imported, duplicates=duplicates, errors=errors
        )

    async def hard_delete(self, *, professor_id: int) -> None:
        """Permanently delete an archived professor with no sessions."""
        professor: Professor = await self._get_or_404(professor_id)

        if professor.is_active:
            raise ProfessorNotArchivedException(professor.id)

        session_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.professor_id == professor.id)
            )
            or 0
        )

        if session_count:
            raise ProfessorHasRecordsException(professor.id)

        await self._session.delete(professor)
        await self._session.flush()

    async def resolve_professor_id(self, *, user_id: int) -> int:
        """Map a user id to its claimed professor row; 404 when unclaimed."""
        return (await self._get_professor_by_user_or_404(user_id)).id

    async def list_assigned_offerings(
        self,
        *,
        user_id: int,
        page: int = DEFAULT_PAGE,
        size: int = DEFAULT_PAGE_SIZE,
    ) -> PaginatedResponse[AssignedOfferingItem]:
        """Own active assignments with course-card enrichment.

        Active means the course_professors effective window covers today and
        the offering itself is active. Each row carries units, enrolled_count
        and the derived section set for the course cards.
        """
        professor: Professor = await self._get_professor_by_user_or_404(user_id)
        items: Sequence[AssignedOfferingItem] = await self._assigned_offerings(
            professor.id
        )
        window: list[AssignedOfferingItem] = list(
            items[(page - 1) * size : page * size]
        )
        await self._enrich_assigned_offerings(window)

        return PaginatedResponse[AssignedOfferingItem](
            items=window, total=len(items), page=page, size=size
        )

    async def get_self_profile(self, *, user_id: int) -> ProfessorProfileRead:
        """Self profile for the account header (wireframes 3.9).

        ``claim_status`` derives from ``professors.user_id`` non-null and
        ``session_count`` counts every session row owned by the professor.
        """
        professor: Professor = await self._get_professor_by_user_or_404(user_id)
        assigned: list[AssignedOfferingItem] = list(
            await self._assigned_offerings(professor.id)
        )
        await self._enrich_assigned_offerings(assigned)
        session_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(Session)
                .where(Session.professor_id == professor.id)
            )
            or 0
        )

        return ProfessorProfileRead(
            id=professor.id,
            first_name=professor.first_name,
            middle_name=professor.middle_name,
            last_name=professor.last_name,
            email=professor.email,
            department=professor.department,
            assigned_courses=assigned,
            claim_status="Claimed" if professor.user_id is not None else "Unclaimed",
            created_at=professor.created_at,
            session_count=session_count,
        )

    async def _archive_row(self, professor: Professor) -> None:
        # Soft archive touches only its own row (ADR-058): no cascade to
        # course_professors / sessions / users.
        professor.is_active = False
        await self._session.flush()

    async def _get_or_404(self, professor_id: int) -> Professor:
        professor: Professor | None = await self._professors.get(professor_id)

        if professor is None:
            raise ProfessorNotFoundException(professor_id)

        return professor

    async def _get_professor_by_user_or_404(self, user_id: int) -> Professor:
        professor: Professor | None = await self._professors.get_by(user_id=user_id)

        if professor is None:
            raise ProfessorNotFoundException(user_id)

        return professor

    async def _assigned_offerings(
        self, professor_id: int
    ) -> Sequence[AssignedOfferingItem]:
        """Active assignments ordered by offering id (base columns only)."""
        today: date = date.today()
        rows = (
            await self._session.execute(
                select(
                    CourseOffering.id,
                    CourseOffering.course_id,
                    Course.course_code,
                    Course.course_name,
                    CourseOffering.program_id,
                    Program.code,
                    CourseOffering.year_level_id,
                    YearLevel.label,
                    CourseOffering.semester,
                    CourseOffering.academic_year,
                    CourseProfessor.is_primary,
                    CourseProfessor.effective_from,
                    CourseProfessor.effective_to,
                    Course.units,
                )
                .join(
                    CourseProfessor,
                    CourseProfessor.offering_id == CourseOffering.id,
                )
                .join(Course, Course.id == CourseOffering.course_id)
                .join(Program, Program.id == CourseOffering.program_id)
                .join(YearLevel, YearLevel.id == CourseOffering.year_level_id)
                .where(
                    CourseProfessor.professor_id == professor_id,
                    CourseProfessor.effective_from <= today,
                    or_(
                        CourseProfessor.effective_to.is_(None),
                        CourseProfessor.effective_to >= today,
                    ),
                    CourseOffering.is_active.is_(True),
                )
                .order_by(CourseOffering.id.asc())
            )
        ).all()

        items: list[AssignedOfferingItem] = [
            AssignedOfferingItem(
                offering_id=offering_id,
                course_id=course_id,
                course_code=course_code,
                course_name=course_name,
                program_id=program_id,
                program_code=program_code,
                year_level_id=year_level_id,
                year_level_label=year_level_label,
                semester=semester,
                academic_year=academic_year,
                is_primary=bool(is_primary),
                effective_from=effective_from,
                effective_to=effective_to,
                units=int(units),
            )
            for (
                offering_id,
                course_id,
                course_code,
                course_name,
                program_id,
                program_code,
                year_level_id,
                year_level_label,
                semester,
                academic_year,
                is_primary,
                effective_from,
                effective_to,
                units,
            ) in rows
        ]

        return items

    async def _enrich_assigned_offerings(
        self, items: Sequence[AssignedOfferingItem]
    ) -> None:
        """Fill enrolled_count and section for one page of assignments.

        Both aggregates run as a single GROUP BY query each over the page's
        offering ids, so enrichment stays constant-query regardless of page
        size. `section` is the distinct set of `students.section` across the
        offering's enrollments (derived — no stored column backs it).
        """
        if not items:
            return

        offering_ids: list[int] = [item.offering_id for item in items]
        by_offering: dict[int, AssignedOfferingItem] = {
            item.offering_id: item for item in items
        }

        counts = (
            await self._session.execute(
                select(Enrollment.offering_id, func.count())
                .where(Enrollment.offering_id.in_(offering_ids))
                .group_by(Enrollment.offering_id)
            )
        ).all()

        for offering_id, count in counts:
            item = by_offering.get(offering_id)

            if item is not None:
                item.enrolled_count = int(count)

        section_rows = (
            await self._session.execute(
                select(Enrollment.offering_id, Student.section)
                .join(Student, Student.id == Enrollment.student_id)
                .where(
                    Enrollment.offering_id.in_(offering_ids),
                    Student.section.is_not(None),
                )
                .group_by(Enrollment.offering_id, Student.section)
                .order_by(Student.section.asc())
            )
        ).all()

        grouped: dict[int, list[str]] = {}

        for offering_id, section in section_rows:
            grouped.setdefault(offering_id, []).append(section)

        for offering_id, sections in grouped.items():
            item = by_offering.get(offering_id)

            if item is not None:
                item.section = sections

    async def _get_offering_or_404(self, offering_id: int) -> CourseOffering:
        offering: CourseOffering | None = await self._session.get(
            CourseOffering, offering_id
        )

        if offering is None:
            raise OfferingNotFoundException(offering_id)

        return offering

    async def _assign_offering(
        self, *, professor_id: int, offering_id: int, assigned_by: int
    ) -> CourseProfessor:
        offering: CourseOffering = await self._get_offering_or_404(offering_id)
        today: date = date.today()

        overlap_service = CourseProfessorService(self._session)
        overlap: list[CourseProfessor] = await overlap_service.check_overlap(
            offering_id, professor_id, today, None
        )

        if overlap:
            existing: CourseProfessor = overlap[0]
            raise OverlappingAssignmentException(
                offering_id,
                professor_id,
                today,
                None,
                existing.effective_from,
                existing.effective_to,
            )

        record = CourseProfessor(
            offering_id=offering_id,
            professor_id=professor_id,
            is_primary=False,
            effective_from=today,
            effective_to=None,
            semester=offering.semester,
            assigned_by=assigned_by,
        )
        self._session.add(record)
        await self._session.flush()

        return record

    async def _replace_assignments(
        self, *, professor_id: int, offering_ids: Sequence[int], assigned_by: int
    ) -> None:
        target: set[int] = set(dict.fromkeys(offering_ids))

        existing: Sequence[CourseProfessor] = (
            await self._session.scalars(
                select(CourseProfessor).where(
                    CourseProfessor.professor_id == professor_id
                )
            )
        ).all()
        current: set[int] = {row.offering_id for row in existing}

        for row in existing:
            if row.offering_id not in target:
                await self._session.delete(row)

        await self._session.flush()

        for offering_id in target - current:
            await self._assign_offering(
                professor_id=professor_id,
                offering_id=offering_id,
                assigned_by=assigned_by,
            )

    async def _assigned_courses(self, professor_id: int) -> Sequence[AssignedCourse]:
        rows: Sequence[Row[tuple[int, str]]] = (
            await self._session.execute(
                select(CourseOffering.id, Course.course_code)
                .join(CourseProfessor, CourseProfessor.offering_id == CourseOffering.id)
                .join(Course, CourseOffering.course_id == Course.id)
                .where(CourseProfessor.professor_id == professor_id)
                .order_by(CourseOffering.id)
            )
        ).all()

        return [
            AssignedCourse(offering_id=offering_id, course_code=course_code)
            for offering_id, course_code in rows
        ]

    async def _to_read(self, professor: Professor) -> ProfessorRead:
        return ProfessorRead(
            id=professor.id,
            first_name=professor.first_name,
            middle_name=professor.middle_name,
            last_name=professor.last_name,
            email=professor.email,
            department=professor.department,
            is_active=professor.is_active,
            claim_status="Claimed" if professor.user_id is not None else "Unclaimed",
            assigned_courses=list(await self._assigned_courses(professor.id)),
            created_at=professor.created_at,
        )

    @staticmethod
    def _apply_order(
        stmt: Select[tuple[Professor]], *, sort_by: str | None, sort_dir: str | None
    ) -> Select[tuple[Professor]]:
        direction: str = (sort_dir or "asc").lower()
        desc: bool = direction == "desc"

        def _order(*columns: Any) -> Any:
            ordered = [col.desc() if desc else col.asc() for col in columns]
            return stmt.order_by(*ordered, Professor.id.asc())

        if sort_by == "last_name":
            return _order(Professor.last_name, Professor.first_name)

        if sort_by == "email":
            return _order(Professor.email)

        if sort_by == "created_at":
            return _order(Professor.created_at)

        return stmt.order_by(Professor.id)
