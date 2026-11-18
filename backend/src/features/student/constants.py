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

STUDENT_ID_MIN_LENGTH: int = 1
STUDENT_ID_MAX_LENGTH: int = 50

EMAIL_MAX_LENGTH: int = 255

# Per-IP throttle on POST /sessions/verify-code. Unlike the scan endpoint, a
# successful verify is a legitimate single retry (fat-fingered code), so the
# cap is deliberately tight to slow probing for a working session code while
# barely affecting a real student.
VERIFY_CODE_RATE_LIMIT_MAX_CALLS: int = 10
VERIFY_CODE_RATE_LIMIT_WINDOW_SECONDS: int = 60

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
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_LENGTH",
    "SEARCH_MAX_LENGTH",
    "SECTION_MAX_LENGTH",
    "SORT_BY_OPTIONS",
    "SORT_DIR_OPTIONS",
    "STUDENT_ID_MAX_LENGTH",
    "STUDENT_ID_MIN_LENGTH",
    "VERIFY_CODE_RATE_LIMIT_MAX_CALLS",
    "VERIFY_CODE_RATE_LIMIT_WINDOW_SECONDS",
]
