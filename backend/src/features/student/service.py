from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.attendance.model import Attendance
from features.program.exceptions import (
    ProgramNotFoundException,
    YearLevelNotFoundException,
)
from features.program.model import Program, YearLevel
from features.student.exceptions import (
    StudentEmailExistsException,
    StudentIdExistsException,
    StudentNotFoundException,
    YearLevelMismatchException,
)
from features.student.model import Student
from features.student.schema import (
    StudentCreate,
    StudentDetail,
    StudentRead,
    StudentUpdate,
)
from shared.base import BaseCRUD
from shared.pagination import PaginatedResponse


class StudentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._students: BaseCRUD[Student] = BaseCRUD(Student, session)

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
