from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

STUDENT_NUMBER_MIN_LENGTH: int = 1
STUDENT_NUMBER_MAX_LENGTH: int = 50

GPS_LAT_MIN: float = -90.0
GPS_LAT_MAX: float = 90.0
GPS_LNG_MIN: float = -180.0
GPS_LNG_MAX: float = 180.0
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
