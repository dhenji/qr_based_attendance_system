"""Risk-batch tuning owned by the analytics slice."""

from __future__ import annotations

from datetime import timedelta

# Records still `pending` in `sync_status` count toward `sync_lag` only once
# they are older than this window.
SYNC_LAG_WINDOW: timedelta = timedelta(hours=24)

# Weekly absence buckets cover the last four Monday-to-Sunday weeks,
# oldest first; the regression x-axis is the 1-based week index.
TREND_WEEKS: int = 4
TREND_XS: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0)

# Positive-slope normaliser for the probability blend: a slope of +0.10
# absences/week saturates the trend term.
TREND_POSITIVE_NORM: float = 0.10

# Blend weights for `risk_probability`; they sum to 1.0.
WEIGHT_ABSENCE_RATE: float = 0.40
WEIGHT_MAX_STREAK: float = 0.25
WEIGHT_SYNC_LAG: float = 0.15
WEIGHT_TREND_SLOPE: float = 0.20

# Decimals kept on the stored feature snapshot.
FEATURE_DECIMALS: int = 4

# Runtime budget for one batch, covering 10k active enrollments. Crossing it is
# reported, never enforced: partial results are written either way, so the run
# finishes and a warning goes out rather than the scores being abandoned.
RISK_BATCH_RUNTIME_BUDGET_MS: int = 300_000
