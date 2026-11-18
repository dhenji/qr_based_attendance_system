from __future__ import annotations

from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH
from features.auth.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
)

EMAIL_MAX_LENGTH: int = 255

DEPARTMENT_MAX_LENGTH: int = 100

SORT_BY_OPTIONS: tuple[str, ...] = ("last_name", "email", "created_at")
SORT_DIR_OPTIONS: tuple[str, ...] = ("asc", "desc")

__all__: list[str] = [
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "DEPARTMENT_MAX_LENGTH",
    "EMAIL_MAX_LENGTH",
    "MAX_PAGE_SIZE",
    "NAME_MAX_LENGTH",
    "NAME_MIN_LENGTH",
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SEARCH_MAX_LENGTH",
    "SORT_BY_OPTIONS",
    "SORT_DIR_OPTIONS",
]
