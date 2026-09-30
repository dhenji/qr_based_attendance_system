from __future__ import annotations

from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

STUDENT_NUMBER_MIN_LENGTH: int = 1
STUDENT_NUMBER_MAX_LENGTH: int = 50

GPS_ACCURACY_MIN: float = 0.0
GPS_ACCURACY_MAX: float = 1000.0

FACE_MATCH_SCORE_MIN: float = 0.0
FACE_MATCH_SCORE_MAX: float = 1.0

EAR_SAMPLES_MIN_COUNT: int = 1
EAR_SAMPLES_MAX_COUNT: int = 100
EAR_VALUE_MIN: float = 0.0
EAR_VALUE_MAX: float = 1.0

IDEMPOTENCY_KEY_MAX_LENGTH: int = 64

SCAN_RATE_LIMIT_MAX_CALLS: int = 30
SCAN_RATE_LIMIT_WINDOW_SECONDS: int = 60

SYNC_STALE_SECONDS: int = 60

HISTORY_SORT_FIELDS: frozenset[str] = frozenset(
    {"date", "course", "section", "status", "time"}
)
HISTORY_SORT_DIRS: frozenset[str] = frozenset({"asc", "desc"})

HISTORY_DEFAULT_SORT_BY: str = "time"
HISTORY_DEFAULT_SORT_DIR: str = "desc"

# Caps on the history filter strings. The accepted *values* are the
# HISTORY_SORT_FIELDS / HISTORY_SORT_DIRS sets; these only bound the wire length.
HISTORY_SORT_BY_MAX_LENGTH: int = 20
HISTORY_SORT_DIR_MAX_LENGTH: int = 4

REVIEW_STATUSES: frozenset[str] = frozenset({"pending", "approved", "rejected"})

# Caps the `?status=` filter string; the accepted values are REVIEW_STATUSES.
REVIEW_STATUS_MAX_LENGTH: int = 20

REVIEW_DEFAULT_STATUS: str = "pending"

REVIEW_DECISIONS: frozenset[str] = frozenset({"approve", "reject"})

REVIEW_NOTE_MAX_LENGTH: int = 1000
