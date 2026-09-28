from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement, Select


def apply_if(
    stmt: Select[Any],
    value: Any,
    build: Callable[[Any], ColumnElement[bool]],
) -> Select[Any]:
    """Append a WHERE criterion only when its filter value was provided.

    The criterion is built lazily: comparisons like ``>=`` reject ``None``
    at construction time, so it must not be built for missing filters.
    """
    return stmt.where(build(value)) if value is not None else stmt
