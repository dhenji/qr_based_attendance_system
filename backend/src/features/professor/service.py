from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.exceptions import OfferingNotFoundException
from features.course.model import Course, CourseOffering
from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor
from features.course_professor.service import CourseProfessorService
from features.professor.exceptions import (
    ProfessorEmailExistsException,
    ProfessorHasRecordsException,
    ProfessorNotArchivedException,
    ProfessorNotFoundException,
)
from features.professor.model import Professor
from features.professor.schema import (
    AssignedCourse,
    ProfessorCreate,
    ProfessorDetail,
    ProfessorImportError,
    ProfessorImportResult,
    ProfessorRead,
    ProfessorUpdate,
)
from features.session.model import Session
from shared.base import BaseCRUD
from shared.csv_import import is_valid_email, parse_csv
from shared.pagination import PaginatedResponse

ROSTER_CSV_COLUMNS: tuple[str, ...] = (
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "department",
)


@dataclass
class _RosterRow:
    line: int
    first_name: str
    middle_name: str | None
    last_name: str
    email: str
    department: str | None


def parse_professor_roster_csv(
    content: bytes,
) -> tuple[list[_RosterRow], list[ProfessorImportError]]:
    """Parse the professor roster-import CSV upload.

    Returns (valid_rows, errors). Never raises on bad rows — every problem
    is reported as a ProfessorImportError with its 1-based line number
    (header = 1). Emails are lowercased so duplicate detection agrees with
    single-create.
    """
    raw_rows, structural_errors = parse_csv(content, ROSTER_CSV_COLUMNS)

    errors: list[ProfessorImportError] = [
        ProfessorImportError(line=e.line, reason=e.reason)
        for e in structural_errors
    ]

    if structural_errors:
        return [], errors

    rows: list[_RosterRow] = []

    for raw in raw_rows:
        lineno = raw.line
        cell = raw.values.get

        first_name = (cell("first_name") or "").strip()
        last_name = (cell("last_name") or "").strip()
        email = (cell("email") or "").strip().lower()

        if not first_name or not last_name or not email:
            errors.append(
                ProfessorImportError(
                    line=lineno,
                    reason=f"missing required field for professor {email or 'on line'}",
                )
            )
            continue

        if not is_valid_email(email):
            errors.append(
                ProfessorImportError(
                    line=lineno,
                    reason=f"invalid email for professor {email}",
                )
            )
            continue

        rows.append(
            _RosterRow(
                line=lineno,
                first_name=first_name,
                middle_name=(cell("middle_name") or "").strip() or None,
                last_name=last_name,
                email=email,
                department=(cell("department") or "").strip() or None,
            )
        )

    return rows, errors


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

        return await self._to_read(professor)

    async def reactivate(self, *, professor_id: int) -> ProfessorRead:
        professor: Professor = await self._get_or_404(professor_id)
        professor.is_active = True
        await self._session.flush()

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
        rows: Sequence[tuple[int, str]] = (
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
            assigned_courses=await self._assigned_courses(professor.id),
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
