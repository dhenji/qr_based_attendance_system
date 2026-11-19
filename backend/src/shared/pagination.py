from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PAGE: int = 1
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 200
SEARCH_MAX_LENGTH: int = 100


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


def normalize_paging(page: int, size: int) -> tuple[int, int]:
    """Clamp a requested page and size to the supported bounds."""
    return max(page, 1), min(max(size, 1), MAX_PAGE_SIZE)


def paginate_query[T](
    query: Select[Any], page: int = DEFAULT_PAGE, size: int = DEFAULT_PAGE_SIZE
) -> Select[Any]:
    return query.offset((page - 1) * size).limit(size)


def paginated_response[T](
    items: list[T], total: int, page: int, size: int
) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "size": size}


async def paginate_scalars[T](
    session: AsyncSession,
    query: Select[Any],
    *,
    page: int,
    size: int,
) -> tuple[Sequence[T], int]:
    """Fetch one ordered page of ORM rows plus the unpaged total.

    The query must be an unpaged select of a single ORM entity (this uses
    ``scalars``); use ``session.execute`` for multi-entity selects.

    ``page`` and ``size`` are the caller's responsibility: list services that
    trust their router bounds must keep doing so, so this helper does not
    normalize them.
    """
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.scalars(paginate_query(query, page, size))).all()

    return rows, int(total or 0)
