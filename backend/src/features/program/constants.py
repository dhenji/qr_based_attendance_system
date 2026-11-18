from __future__ import annotations

from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

from features.admin.constants import NAME_MAX_LENGTH, NAME_MIN_LENGTH

CODE_MIN_LENGTH: int = 2
CODE_MAX_LENGTH: int = 20

DESCRIPTION_MAX_LENGTH: int = 1000

TOTAL_YEARS_MIN: int = 1
TOTAL_YEARS_MAX: int = 10

YEAR_NUMBER_MIN: int = 1
YEAR_NUMBER_MAX: int = 10

LABEL_MIN_LENGTH: int = 1
LABEL_MAX_LENGTH: int = 50

SORT_ORDER_MIN: int = 1
SORT_ORDER_MAX: int = 100
