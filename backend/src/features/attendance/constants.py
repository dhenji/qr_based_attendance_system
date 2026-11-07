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
GPS_ACCURACY_MAX: float = 100000.0

FACE_MATCH_SCORE_MIN: float = 0.0
FACE_MATCH_SCORE_MAX: float = 1.0

EAR_SAMPLES_MIN_COUNT: int = 1
EAR_SAMPLES_MAX_COUNT: int = 100
EAR_VALUE_MIN: float = 0.0
EAR_VALUE_MAX: float = 1.0

# Acceptance band for the *mean* of `ear_samples` (EAR_VALUE_MIN/MAX above
# bound each individual sample). Distinct from them on purpose: an evidence
# blob can hold every sample inside [0.0, 1.0] and still fail on its mean.
EAR_MEAN_MIN: float = 0.05
EAR_MEAN_MAX: float = 0.5

IDEMPOTENCY_KEY_MAX_LENGTH: int = 64

# How long a cached scan response may be replayed for a repeated
# X-Idempotency-Key. Long enough to cover an offline-sync retry loop, short
# enough that a key reused days later does not resurrect a stale response.
IDEMPOTENCY_TTL_SECONDS: int = 900
_IDEMPOTENCY_MAX_ENTRIES: int = 10_000

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

# Why a row was flagged for the liveness review queue. Stored as an
# additive key inside `attendance_records.liveness_evidence` so historical
# rows that predate the key simply omit it.
REVIEW_REASON_FACE_BAND: str = "face_review_band"
REVIEW_REASON_GEOFENCE: str = "geofence_uncertainty"

# Where a reviewer's free-text note is stored: `attendance_records` has no
# dedicated column, so it rides inside the existing JSONB evidence blob.
REVIEW_NOTE_EVIDENCE_KEY: str = "review_note"

# Where the reviewer identity/timestamp are stored: `attendance_records` has
# no dedicated columns, so they ride inside the existing JSONB evidence blob
# alongside the note.
REVIEWED_BY_EVIDENCE_KEY: str = "reviewed_by"
REVIEWED_AT_EVIDENCE_KEY: str = "reviewed_at"

RECENT_SCANS_DEFAULT_LIMIT: int = 10
RECENT_SCANS_MAX_LIMIT: int = 100

# Minimum gap between first-half and second-half compliance rates before a
# per-course trend counts as moving up or down.
OVERVIEW_TREND_EPSILON: float = 0.01
