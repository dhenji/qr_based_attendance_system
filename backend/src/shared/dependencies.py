from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.pagination import paginate_query, paginated_response


async def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, int]:
    """FastAPI dependency: validated ``?page=&size`` query params."""

    return {"page": page, "size": size}


async def paginated(
    session: AsyncSession, stmt: Select[Any], page: int, size: int
) -> dict[str, Any]:
    """Count + page a query and return the standard paginated shape"""

    total: int = (
        await session.scalars(select(func.count()).select_from(stmt.subquery()))
    ).one()

    rows: Sequence[Any] = (
        await session.scalars(paginate_query(stmt, page, size))
    ).all()

    return paginated_response(list(rows), total, page, size)


def api_error(
    status_code: int, code: str, message: str, field: str | None = None
) -> HTTPException:
    """Build an HTTPException with the standard ``{detail: {code, message, field}}`` shape."""

    detail: dict[str, Any] = {"code": code, "message": message}

    if field is not None:
        detail["field"] = field

    return HTTPException(status_code=status_code, detail=detail)
