from __future__ import annotations

from shared.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
)

DURATION_MINUTES_MIN: int = 1
DURATION_MINUTES_MAX: int = 480

WINDOW_MINUTES_MIN: int = 1
WINDOW_MINUTES_MAX: int = 480

# How far in the past an overridden start time may point (D93). The default
# (unoverridden) start may be arbitrarily far in the past — a class that began
# this morning and is being opened at lunch is still that class — so this
# grace applies to an explicit override only, where it catches a mistyped
# time or a wrong day rather than a legitimate "it actually started earlier".
OVERRIDE_PAST_GRACE_MINUTES: int = 60

SESSION_CODE_MIN_LENGTH: int = 1
SESSION_CODE_MAX_LENGTH: int = 50

CLASSROOM_NAME_MAX_LENGTH: int = 100
