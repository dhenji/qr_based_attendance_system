from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement, Select, or_


def ilike_any(term: str, *columns: ColumnElement[Any]) -> ColumnElement[bool]:
    """Case-insensitive substring match across any of ``columns``.

    The term is used verbatim: callers that trim their input keep doing so,
    and wildcards retain their existing meaning.
    """
    pattern = f"%{term}%"

    return or_(*(column.ilike(pattern) for column in columns))


def ilike_search(
    stmt: Select[Any],
    term: str,
    *columns: ColumnElement[Any],
) -> Select[Any]:
    """Append a case-insensitive substring search over ``columns``."""
    return stmt.where(ilike_any(term, *columns))


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
