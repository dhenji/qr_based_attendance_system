"""Single definition of per-session attempt accounting.

The durable ``attendance_attempt_counters`` row is the one source of truth;
this module is the one place that turns ``limit`` + ``used`` into the
contract fields exposed by ``submit_scan``, ``precheck_scan`` and
``verify_code`` (mirrors the ``shared/rates.py`` single-definition rule —
do not re-derive remaining attempts per call site).

Semantics (docs/architecture/api-contracts.md, attempt metadata):

- ``limit = 0`` means unlimited: ``remaining`` is ``None`` and nothing is
  consumed.
- ``used`` is the raw durable counter value **after** the operation's
  counter effect. It can exceed ``limit`` because blocked retries keep
  incrementing; callers must not clamp it.
- ``consumed`` reports whether *this* request incremented the counter.
  ``submit_scan`` increments before validating (so post-increment
  failures and the exhaustion rejection are all ``consumed=True``), while
  ``verify_code`` only reads the counter, so its exhaustion raise is
  ``consumed=False``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttemptMeta:
    """Contract payload for one request's attempt state."""

    limit: int
    used: int
    remaining: int | None
    consumed: bool

    def to_details(self) -> dict:
        """``AppException.details`` payload (snake_case, like the JSON body)."""
        return {
            "attempt_limit": self.limit,
            "attempts_used": self.used,
            "attempts_remaining": self.remaining,
            "attempt_consumed": self.consumed,
        }


def remaining_after(limit: int, used: int) -> int | None:
    """Attempts left after ``used`` attempts against ``limit``.

    ``None`` for unlimited sessions (``limit = 0``); clamped at 0 so the
    raw (possibly over-limit) ``used`` never produces a negative count.
    """
    if limit <= 0:
        return None
    return max(0, limit - used)


def meta_for(
    limit: int,
    used: int,
    *,
    consumed: bool,
) -> AttemptMeta:
    """Build the contract payload for one request.

    ``used`` must already reflect the request's own counter effect: pass
    the post-increment count when ``consumed`` is ``True``, the plain
    counter read when it is ``False``.
    """
    return AttemptMeta(
        limit=limit,
        used=used,
        remaining=remaining_after(limit, used),
        consumed=consumed,
    )
