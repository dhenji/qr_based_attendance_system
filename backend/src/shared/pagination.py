from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


def paginate_query[T](query: Select[Any], page: int = 1, size: int = 50) -> Select[Any]:
    return query.offset((page - 1) * size).limit(size)


def paginated_response[T](
    items: list[T], total: int, page: int, size: int
) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "size": size}
