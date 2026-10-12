"""Admin PATCH /admin/students/{id} must accept middle_name.

Regression test: the edit modal sends middle_name, but StudentUpdate had no
such field, so renames were silently dropped (pydantic ignores extras) and
the table never changed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from features.student.schema import StudentUpdate
from features.student.service import StudentService
from tests.conftest import Factories


async def test_update_sets_middle_name(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year)
    admin = await factories.user(role="admin")

    updated = await StudentService(test_db_session).update(
        student_id=student.id,
        payload=StudentUpdate(middle_name="Reyes"),
        actor_id=admin.id,
    )

    assert updated.middle_name == "Reyes"


async def test_update_clears_middle_name_with_null(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year, middle_name="Reyes")
    admin = await factories.user(role="admin")

    updated = await StudentService(test_db_session).update(
        student_id=student.id,
        payload=StudentUpdate(middle_name=None),
        actor_id=admin.id,
    )

    assert updated.middle_name is None


async def test_update_leaves_middle_name_when_unset(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    program = await factories.program()
    year = await factories.year_level(program)
    student = await factories.student(year, middle_name="Reyes")
    admin = await factories.user(role="admin")

    updated = await StudentService(test_db_session).update(
        student_id=student.id,
        payload=StudentUpdate(first_name="Newname"),
        actor_id=admin.id,
    )

    assert updated.first_name == "Newname"
    assert updated.middle_name == "Reyes"
