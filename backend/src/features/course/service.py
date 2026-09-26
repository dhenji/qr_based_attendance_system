from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course.exceptions import (
    CourseCodeExistsException,
    CourseNotFoundException,
)
from features.course.model import Course
from features.course.schema import CourseCreate, CourseRead, CourseUpdate
from shared.base import BaseCRUD
from shared.pagination import PaginatedResponse


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._courses: BaseCRUD[Course] = BaseCRUD(Course, session)

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
