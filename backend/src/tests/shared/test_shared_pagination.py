"""The shared pagination helpers.

`normalize_paging` is pure, so those checks need no database. `paginate_scalars`
runs the count/page pair for the list services, so its tests use the same
`test_db_session` + `Factories` setup as the feature suites.

The "no internal normalization" contract matters: the CRUD list services trust
their router `Query` bounds and are called directly in tests, so a helper that
clamped on its own would change behaviour that is currently only enforced at
the HTTP edge.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.pagination import MAX_PAGE_SIZE, normalize_paging, paginate_scalars

from features.program.model import Program
from tests.conftest import Factories


def test_normalize_paging_keeps_values_inside_the_bounds() -> None:
    assert normalize_paging(page=3, size=50) == (3, 50)


def test_normalize_paging_clamps_low_values() -> None:
    assert normalize_paging(page=0, size=0) == (1, 1)
    assert normalize_paging(page=-5, size=-1) == (1, 1)


def test_normalize_paging_caps_the_page_size() -> None:
    assert normalize_paging(page=2, size=MAX_PAGE_SIZE + 1) == (2, MAX_PAGE_SIZE)
    assert normalize_paging(page=2, size=MAX_PAGE_SIZE) == (2, MAX_PAGE_SIZE)


async def _seed_programs(factories: Factories, count: int) -> None:
    for index in range(count):
        await factories.program(code=f"PG{index}", name=f"Program {index}")


async def test_paginate_scalars_returns_one_page_and_the_total(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    await _seed_programs(factories, 5)

    rows, total = await paginate_scalars(
        test_db_session,
        select(Program).order_by(Program.id),
        page=2,
        size=2,
    )

    assert total == 5
    assert [row.code for row in rows] == ["PG2", "PG3"]


async def test_paginate_scalars_past_the_last_page_returns_no_rows(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    await _seed_programs(factories, 3)

    rows, total = await paginate_scalars(
        test_db_session,
        select(Program).order_by(Program.id),
        page=99,
        size=10,
    )

    assert total == 3
    assert rows == []


async def test_paginate_scalars_does_not_normalize_the_size(
    test_db_session: AsyncSession, factories: Factories
) -> None:
    """A zero size must reach the query untouched, not be clamped to 1."""

    await _seed_programs(factories, 3)

    rows, total = await paginate_scalars(
        test_db_session,
        select(Program).order_by(Program.id),
        page=1,
        size=0,
    )

    assert total == 3
    assert rows == []
