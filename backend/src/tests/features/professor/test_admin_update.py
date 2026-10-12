"""Admin PATCH /admin/professors/{id} must accept middle_name.

Regression test: the edit modal sends middle_name, but ProfessorUpdate had
no such field, so renames were silently dropped (pydantic ignores extras)
and the table never changed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from features.professor.schema import ProfessorUpdate
from features.professor.service import ProfessorService
from tests.conftest import Factories


async def test_update_sets_middle_name(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    professor = await factories.professor()
    admin = await factories.user(role="admin")

    updated = await ProfessorService(test_db_session).update(
        professor_id=professor.id,
        payload=ProfessorUpdate(middle_name="Reyes"),
        assigned_by=admin.id,
    )

    assert updated.middle_name == "Reyes"


async def test_update_clears_middle_name_with_null(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    professor = await factories.professor(middle_name="Reyes")
    admin = await factories.user(role="admin")

    updated = await ProfessorService(test_db_session).update(
        professor_id=professor.id,
        payload=ProfessorUpdate(middle_name=None),
        assigned_by=admin.id,
    )

    assert updated.middle_name is None


async def test_update_leaves_middle_name_when_unset(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    professor = await factories.professor(middle_name="Reyes")
    admin = await factories.user(role="admin")

    updated = await ProfessorService(test_db_session).update(
        professor_id=professor.id,
        payload=ProfessorUpdate(first_name="Newname"),
        assigned_by=admin.id,
    )

    assert updated.first_name == "Newname"
    assert updated.middle_name == "Reyes"
