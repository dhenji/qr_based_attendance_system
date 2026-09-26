from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.model import CourseOffering
from features.program.exceptions import (
    ProgramCodeExistsException,
    ProgramNotFoundException,
    YearLevelHasCoursesException,
    YearLevelNotFoundException,
    YearLevelNumberExistsException,
)
from features.program.model import Program, YearLevel
from features.program.schema import (
    ProgramCreate,
    ProgramDetail,
    ProgramRead,
    ProgramUpdate,
    YearLevelCreate,
    YearLevelRead,
    YearLevelUpdate,
)
from shared.base import BaseCRUD
from shared.pagination import PaginatedResponse


class ProgramService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._programs: BaseCRUD[Program] = BaseCRUD(Program, session)
        self._years: BaseCRUD[YearLevel] = BaseCRUD(YearLevel, session)

    async def create(self, *, payload: ProgramCreate) -> ProgramRead:
        if await self._programs.get_by(code=payload.code) is not None:
            raise ProgramCodeExistsException(payload.code)

        program: Program = await self._programs.create(
            code=payload.code,
            name=payload.name,
            description=payload.description,
            total_years=payload.total_years,
        )

        return ProgramRead(**self._read_fields(program))

    async def get(self, *, program_id: int) -> ProgramDetail:
        program: Program = await self._get_or_404(program_id)
        year_levels: Sequence[YearLevel] = await self._year_levels(program_id)

        return ProgramDetail(
            **self._read_fields(
                program,
                course_count=await self._course_count(program_id),
                year_level_count=len(year_levels),
                terms_count=self._terms_count(year_levels),
            ),
            year_levels=[
                YearLevelRead.model_validate(year_level) for year_level in year_levels
            ],
        )

    async def list(
        self,
        *,
        search: str | None,
        is_active: bool | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[ProgramRead]:
        stmt: Select[tuple[Program]] = select(Program)

        if is_active is not None:
            stmt = stmt.where(Program.is_active == is_active)

        if search:
            term: str = f"%{search.strip()}%"
            stmt = stmt.where(or_(Program.code.ilike(term), Program.name.ilike(term)))

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[Program] = (
            await self._session.scalars(
                stmt.order_by(Program.id).offset((page - 1) * size).limit(size)
            )
        ).all()

        items: list[ProgramRead] = []

        for program in rows:
            year_levels: Sequence[YearLevel] = await self._year_levels(program.id)
            fields: dict[str, Any] = self._read_fields(
                program,
                course_count=await self._course_count(program.id),
                year_level_count=len(year_levels),
                terms_count=self._terms_count(year_levels),
            )

            items.append(ProgramRead(**fields))

        return PaginatedResponse[ProgramRead](
            items=items, total=total, page=page, size=size
        )

    async def update(self, *, program_id: int, payload: ProgramUpdate) -> ProgramRead:
        program: Program = await self._get_or_404(program_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(program, field, value)

        await self._session.flush()

        return ProgramRead(**self._read_fields(program))

    async def archive(self, *, program_id: int) -> None:
        program: Program = await self._get_or_404(program_id)
        program.is_active = False
        await self._session.flush()

    async def list_years(
        self, *, program_id: int, page: int, size: int
    ) -> PaginatedResponse[YearLevelRead]:
        await self._get_or_404(program_id)

        stmt: Select[tuple[YearLevel]] = select(YearLevel).where(
            YearLevel.program_id == program_id
        )

        total: int = (
            await self._session.scalar(
                select(func.count()).select_from(stmt.subquery())
            )
            or 0
        )

        rows: Sequence[YearLevel] = (
            await self._session.scalars(
                stmt.order_by(YearLevel.year_number)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()

        return PaginatedResponse[YearLevelRead](
            items=[YearLevelRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def create_year(
        self, *, program_id: int, payload: YearLevelCreate
    ) -> YearLevelRead:
        await self._get_or_404(program_id)

        if (
            await self._years.get_by(
                program_id=program_id, year_number=payload.year_number
            )
            is not None
        ):
            raise YearLevelNumberExistsException(payload.year_number, program_id)

        year_level: YearLevel = await self._years.create(
            program_id=program_id,
            year_number=payload.year_number,
            label=payload.label,
            term_structure=payload.term_structure.model_dump(),
            sort_order=(
                payload.sort_order
                if payload.sort_order is not None
                else payload.year_number
            ),
        )

        return YearLevelRead.model_validate(year_level)

    async def get_year(self, *, program_id: int, year_id: int) -> YearLevelRead:
        return YearLevelRead.model_validate(
            await self._get_year_or_404(program_id, year_id)
        )

    async def update_year(
        self, *, program_id: int, year_id: int, payload: YearLevelUpdate
    ) -> YearLevelRead:
        year_level: YearLevel = await self._get_year_or_404(program_id, year_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(year_level, field, value)

        await self._session.flush()

        return YearLevelRead.model_validate(year_level)

    async def delete_year(self, *, program_id: int, year_id: int) -> None:
        year_level: YearLevel = await self._get_year_or_404(program_id, year_id)

        offering_count: int = (
            await self._session.scalar(
                select(func.count())
                .select_from(CourseOffering)
                .where(CourseOffering.year_level_id == year_id)
            )
            or 0
        )

        if offering_count > 0:
            raise YearLevelHasCoursesException(year_id)

        await self._session.delete(year_level)
        await self._session.flush()

    async def _get_or_404(self, program_id: int) -> Program:
        program: Program | None = await self._programs.get(program_id)

        if program is None:
            raise ProgramNotFoundException(program_id)

        return program

    async def _get_year_or_404(self, program_id: int, year_id: int) -> YearLevel:
        await self._get_or_404(program_id)

        year_level: YearLevel | None = await self._years.get(year_id)

        if year_level is None or year_level.program_id != program_id:
            raise YearLevelNotFoundException(year_id, program_id)

        return year_level

    async def _year_levels(self, program_id: int) -> Sequence[YearLevel]:
        return (
            await self._session.scalars(
                select(YearLevel)
                .where(YearLevel.program_id == program_id)
                .order_by(YearLevel.year_number)
            )
        ).all()

    async def _course_count(self, program_id: int) -> int:
        stmt: Select[tuple[int]] = select(
            func.count(func.distinct(CourseOffering.course_id))
        ).where(
            CourseOffering.program_id == program_id, CourseOffering.is_active.is_(True)
        )

        return (await self._session.scalars(stmt)).one()

    @staticmethod
    def _terms_count(year_levels: Sequence[YearLevel]) -> int:
        return sum(
            len((year_level.term_structure or {}).get("terms") or [])
            for year_level in year_levels
        )

    @staticmethod
    def _read_fields(
        program: Program,
        *,
        course_count: int = 0,
        year_level_count: int = 0,
        terms_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "id": program.id,
            "code": program.code,
            "name": program.name,
            "description": program.description,
            "total_years": program.total_years,
            "is_active": program.is_active,
            "course_count": course_count,
            "year_level_count": year_level_count,
            "terms_count": terms_count,
            "created_at": program.created_at,
            "updated_at": program.updated_at,
        }
