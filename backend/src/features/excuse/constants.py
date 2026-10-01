from __future__ import annotations

ATTACHMENT_MAX_BYTES: int = 5 * 1024 * 1024
ATTACHMENT_MAX_COUNT: int = 5

ALLOWED_ATTACHMENT_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "jpg", "jpeg", "png", "heic"}
)

REASON_MAX_LENGTH: int = 2000
REASON_MIN_LENGTH_QUICK: int = 10
REASON_MIN_LENGTH_STUDENT: int = 20

EXCUSE_TYPE_QUICK: str = "quick"
EXCUSE_TYPE_WITH_EVIDENCE: str = "prof_with_evidence"
EXCUSE_TYPE_REQUEST_APPROVED: str = "request_approved"
