from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH
from features.auth.constants import (
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

STUDENT_ID_MIN_LENGTH: int = 1
STUDENT_ID_MAX_LENGTH: int = 50

EMAIL_MAX_LENGTH: int = 255

SECTION_MAX_LENGTH: int = 20

SORT_BY_OPTIONS: tuple[str, ...] = ("last_name", "student_id", "created_at")
SORT_DIR_OPTIONS: tuple[str, ...] = ("asc", "desc")

__all__: list[str] = [
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "EMAIL_MAX_LENGTH",
    "MAX_PAGE_SIZE",
    "NAME_MAX_LENGTH",
    "NAME_MIN_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SEARCH_MAX_LENGTH",
    "SECTION_MAX_LENGTH",
    "SORT_BY_OPTIONS",
    "SORT_DIR_OPTIONS",
    "STUDENT_ID_MAX_LENGTH",
    "STUDENT_ID_MIN_LENGTH",
    "USERNAME_MAX_LENGTH",
    "USERNAME_MIN_LENGTH",
]
