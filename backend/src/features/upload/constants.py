from __future__ import annotations

# One filesystem path segment. Long enough for any real client-side filename
# and short enough that a long one is rejected before it reaches storage.
FILENAME_MAX_LENGTH: int = 255
FILENAME_MIN_LENGTH: int = 1

CONTENT_TYPE_MAX_LENGTH: int = 128