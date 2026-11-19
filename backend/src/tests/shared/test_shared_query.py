"""The shared ILIKE search helpers.

`ilike_search` centralizes the plain `stmt.where(or_(...))` sites and
`ilike_any` the composite sites that must OR the text match with a non-ILIKE
predicate (an id equality). Feature tests already cover the callers, but only
with data that happens to sit in one column, so the contracts pinned here are
the ones a consolidation can silently break: matching *any* supplied column,
case-insensitivity, and using the term verbatim.

Callers own trimming. `session/service.py` deliberately passes a raw term in
one attendance path, so stripping inside the helper would change its matching.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.query import ilike_any, ilike_search

from features.program.model import Program
from tests.conftest import Factories


async def _seed_programs(factories: Factories) -> tuple[Program, Program]:
    computer_science = await factories.program(code="BSCS", name="Computer Science")
    information_technology = await factories.program(
        code="BSIT", name="Information Technology"
    )

    return computer_science, information_technology


async def test_ilike_search_matches_any_supplied_column(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    await _seed_programs(factories)

    by_name = (
        await test_db_session.scalars(
            ilike_search(select(Program), "computer", Program.code, Program.name)
        )
    ).all()
    by_code = (
        await test_db_session.scalars(
            ilike_search(select(Program), "bsit", Program.code, Program.name)
        )
    ).all()

    assert [row.code for row in by_name] == ["BSCS"]
    assert [row.code for row in by_code] == ["BSIT"]


async def test_ilike_search_uses_the_term_verbatim(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Whitespace is part of the term; the helper must not trim it."""

    await _seed_programs(factories)

    rows = (
        await test_db_session.scalars(
            ilike_search(select(Program), " BSCS ", Program.code, Program.name)
        )
    ).all()

    assert rows == []


async def test_ilike_search_keeps_sql_wildcards(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """Escaping the term would turn this into a literal match for ``BS_T``."""

    await _seed_programs(factories)

    rows = (
        await test_db_session.scalars(
            ilike_search(select(Program), "BS_T", Program.code, Program.name)
        )
    ).all()

    assert [row.code for row in rows] == ["BSIT"]


async def test_ilike_any_composes_with_an_extra_or_predicate(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """The composite sites OR a text match with an id equality."""

    computer_science, information_technology = await _seed_programs(factories)

    rows = (
        await test_db_session.scalars(
            select(Program).where(
                or_(
                    ilike_any("bsit", Program.code, Program.name),
                    Program.id == computer_science.id,
                )
            )
        )
    ).all()

    assert {row.id for row in rows} == {
        computer_science.id,
        information_technology.id,
    }
