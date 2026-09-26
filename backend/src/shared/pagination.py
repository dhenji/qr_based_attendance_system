from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select

DEFAULT_PAGE: int = 1
DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200
SEARCH_MAX_LENGTH: int = 100


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


def paginate_query[T](
    query: Select[Any], page: int = DEFAULT_PAGE, size: int = DEFAULT_PAGE_SIZE
) -> Select[Any]:
    return query.offset((page - 1) * size).limit(size)


def paginated_response[T](
    items: list[T], total: int, page: int, size: int
) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "size": size}
