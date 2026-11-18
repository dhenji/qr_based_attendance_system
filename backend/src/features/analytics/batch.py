from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
from core.scheduler import JOB_RISK_BATCH, track

from shared.datetimes import ensure_aware
from shared.enums import RiskLevel, SyncStatus, ValidationStatus
from shared.schedule import term_weeks

from features.analytics.constants import (
    FEATURE_DECIMALS,
    RISK_BATCH_RUNTIME_BUDGET_MS,
    SYNC_LAG_WINDOW,
    TREND_POSITIVE_NORM,
    TREND_WEEKS,
    TREND_XS,
    WEIGHT_ABSENCE_RATE,
    WEIGHT_MAX_STREAK,
    WEIGHT_SYNC_LAG,
    WEIGHT_TREND_SLOPE,
)
from features.analytics.model import StudentRiskScore, StudentRiskScoreStaging
from features.attendance.model import Attendance
from features.course.model import CourseOffering
from features.enrollment.model import Enrollment
from features.program.model import YearLevel
from features.session.model import Session

logger = logging.getLogger(__name__)


@dataclass
class _ScoredTarget:
    student_id: int
    offering_id: int
    semester: str
    level: RiskLevel
    probability: Decimal
    features: dict[str, Any]


def linear_regression_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return 0.0
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def _week_bucket(day: date, monday: date) -> int | None:
    """Zero-based trend bucket for `day`, or None when past the window."""
    delta = (monday - day).days
    if delta <= 0:
        return TREND_WEEKS - 1
    weeks_ago = (delta + 6) // 7
    if weeks_ago >= TREND_WEEKS:
        return None
    return TREND_WEEKS - 1 - weeks_ago


def compute_weekly_absences(
    absent_moments: Sequence[datetime],
    now: datetime,
) -> list[int]:
    anchor = ensure_aware(now).date()
    monday = anchor - timedelta(days=anchor.weekday())
    weeks: list[int] = [0] * TREND_WEEKS
    for moment in absent_moments:
        bucket = _week_bucket(ensure_aware(moment).date(), monday)
        if bucket is not None:
            weeks[bucket] += 1
    return weeks


def _usable_records(records: Sequence[Any]) -> list[Any]:
    """Drop rejected rows; they take part in neither numerator nor streak."""
    return [
        row
        for row in records
        if (row.validation_status or "") != ValidationStatus.REJECTED.value
    ]


def _record_moment(record: Any, fallback: datetime) -> datetime:
    if record.timestamp is not None:
        return ensure_aware(record.timestamp)
    return fallback


def _status_count(records: Sequence[Any], status: ValidationStatus) -> int:
    return sum(1 for row in records if row.validation_status == status.value)


def _longest_absence_streak(ordered: Sequence[Any]) -> int:
    best = 0
    current = 0
    for row in ordered:
        match row.validation_status or "":
            case ValidationStatus.ABSENT.value:
                current += 1
                best = max(best, current)
            case ValidationStatus.PENDING.value:
                continue
            case (
                ValidationStatus.PRESENT.value
                | ValidationStatus.LATE.value
                | ValidationStatus.EXCUSED.value
            ):
                current = 0
            case _:
                continue
    return best


def _stale_pending_count(records: Sequence[Any], cutoff: datetime) -> int:
    return sum(
        1
        for row in records
        if (row.sync_status or "") == SyncStatus.PENDING.value
        and row.timestamp is not None
        and ensure_aware(row.timestamp) < cutoff
    )


def _absent_moments(records: Sequence[Any]) -> list[datetime]:
    return [
        row.timestamp
        for row in records
        if row.validation_status == ValidationStatus.ABSENT.value
        and row.timestamp is not None
    ]


def compute_features(
    records: Sequence[Any],
    expected_sessions: int,
    now: datetime,
) -> dict[str, Any]:
    moment = ensure_aware(now)
    usable = _usable_records(records)
    ordered = sorted(usable, key=lambda row: _record_moment(row, moment))

    absent_count = _status_count(usable, ValidationStatus.ABSENT)
    if expected_sessions > 0:
        absence_rate = absent_count / expected_sessions
    else:
        absence_rate = 0.0

    weekly_absences = compute_weekly_absences(_absent_moments(usable), moment)
    trend_slope = linear_regression_slope(
        TREND_XS,
        [float(value) for value in weekly_absences],
    )

    return {
        "expected_sessions": expected_sessions,
        "actual_sessions": len(usable),
        "absent_count": absent_count,
        "absence_rate": round(absence_rate, FEATURE_DECIMALS),
        "max_streak": _longest_absence_streak(ordered),
        "sync_lag": _stale_pending_count(usable, moment - SYNC_LAG_WINDOW),
        "weekly_absences": weekly_absences,
        "trend_slope": round(trend_slope, FEATURE_DECIMALS),
        "present_count": _status_count(usable, ValidationStatus.PRESENT),
        "late_count": _status_count(usable, ValidationStatus.LATE),
        "excused_count": _status_count(usable, ValidationStatus.EXCUSED),
    }


def _risk_level(
    absence_rate: float,
    max_streak: int,
    sync_lag: int,
    trend_slope: float,
    cfg: Settings,
) -> RiskLevel:
    """First match wins; higher-severity rules come first."""
    rules: tuple[tuple[bool, RiskLevel], ...] = (
        (absence_rate > cfg.risk_absence_rate_high, RiskLevel.HIGH),
        (max_streak >= cfg.risk_streak_gaps_high, RiskLevel.HIGH),
        (absence_rate > cfg.risk_absence_rate_medium, RiskLevel.MEDIUM),
        (sync_lag >= cfg.risk_sync_lag_high, RiskLevel.MEDIUM),
        (trend_slope < cfg.risk_trend_negative, RiskLevel.MEDIUM),
    )
    for hit, level in rules:
        if hit:
            return level
    return RiskLevel.LOW


def _capped_ratio(value: float, threshold: float) -> float:
    if not threshold:
        return 0.0
    return min(value / threshold, 1.0)


def _risk_probability(
    absence_rate: float,
    max_streak: int,
    sync_lag: int,
    trend_slope: float,
    cfg: Settings,
) -> float:
    blended = (
        WEIGHT_ABSENCE_RATE * _capped_ratio(absence_rate, cfg.risk_absence_rate_high)
        + WEIGHT_MAX_STREAK
        * _capped_ratio(float(max_streak), float(cfg.risk_streak_gaps_high))
        + WEIGHT_SYNC_LAG
        * _capped_ratio(float(sync_lag), float(cfg.risk_sync_lag_high))
        + WEIGHT_TREND_SLOPE * _capped_ratio(max(trend_slope, 0.0), TREND_POSITIVE_NORM)
    )
    return round(max(0.0, min(1.0, blended)), FEATURE_DECIMALS)


def evaluate_risk(
    features: Mapping[str, Any],
    settings: Settings | None = None,
) -> tuple[RiskLevel, float]:
    cfg = settings or get_settings()
    absence_rate = float(features.get("absence_rate", 0.0))
    max_streak = int(features.get("max_streak", 0))
    sync_lag = int(features.get("sync_lag", 0))
    trend_slope = float(features.get("trend_slope", 0.0))
    level = _risk_level(absence_rate, max_streak, sync_lag, trend_slope, cfg)
    probability = _risk_probability(
        absence_rate, max_streak, sync_lag, trend_slope, cfg
    )
    return level, probability


async def _load_active_targets(
    session: AsyncSession,
) -> list[tuple[int, int, str]]:
    rows: Sequence[tuple[int, int, str]] = (
        await session.execute(
            select(Enrollment.student_id, Enrollment.offering_id, Enrollment.semester)
            .join(CourseOffering, CourseOffering.id == Enrollment.offering_id)
            .where(CourseOffering.is_active.is_(True))
        )
    ).all()  # type: ignore[assignment]
    return list(dict.fromkeys(rows))


async def _load_expected_by_offering(
    session: AsyncSession,
    offering_ids: list[int],
) -> dict[int, int]:
    offerings: Sequence[CourseOffering] = (
        await session.scalars(
            select(CourseOffering).where(CourseOffering.id.in_(offering_ids))
        )
    ).all()

    # Session weeks are term-scoped (D86): resolve each offering's weeks from
    # its year level's term structure, batched by year level to avoid a query
    # per offering. An orphaned `semester` falls back to the shared default.
    year_level_ids = {row.year_level_id for row in offerings}
    structures: dict[int, dict] = {}
    if year_level_ids:
        rows = (
            await session.execute(
                select(YearLevel.id, YearLevel.term_structure).where(
                    YearLevel.id.in_(year_level_ids)
                )
            )
        ).all()
        structures = {row.id: row.term_structure for row in rows}

    return {
        row.id: term_weeks(structures.get(row.year_level_id), row.semester)
        * int(row.sessions_per_week or 0)
        for row in offerings
    }


async def _load_grouped_attendance(
    session: AsyncSession,
    student_ids: list[int],
    offering_ids: list[int],
) -> dict[tuple[int, int], list[Attendance]]:
    rows: Sequence[tuple[Attendance, int]] = (
        await session.execute(
            select(Attendance, Session.offering_id)
            .join(Session, Session.id == Attendance.session_id)
            .where(Attendance.student_id.in_(student_ids))
            .where(Session.offering_id.in_(offering_ids))
        )
    ).all()  # type: ignore[assignment]
    grouped: dict[tuple[int, int], list[Attendance]] = {}
    for record, offering_id in rows:
        grouped.setdefault((record.student_id, offering_id), []).append(record)
    return grouped


def _score_targets(
    resolved: list[tuple[int, int, str]],
    expected_by_offering: dict[int, int],
    grouped: dict[tuple[int, int], list[Attendance]],
    moment: datetime,
    cfg: Settings,
    chunk_size: int,
    workers: int = 1,
) -> list[_ScoredTarget]:
    slices = [
        resolved[start : start + chunk_size]
        for start in range(0, len(resolved), chunk_size)
    ]

    def _score_slice(
        targets: list[tuple[int, int, str]],
    ) -> list[_ScoredTarget]:
        scored: list[_ScoredTarget] = []
        for student_id, offering_id, semester in targets:
            expected = expected_by_offering.get(offering_id, 0)
            records = grouped.get((student_id, offering_id), [])
            features = compute_features(records, expected, moment)
            level, probability = evaluate_risk(features, cfg)
            scored.append(
                _ScoredTarget(
                    student_id=student_id,
                    offering_id=offering_id,
                    semester=semester,
                    level=level,
                    probability=Decimal(str(probability)),
                    features=features,
                )
            )
        return scored

    if workers <= 1 or len(slices) <= 1:
        return [item for part in slices for item in _score_slice(part)]

    # `executor.map` preserves input order, so sharded runs score identically
    # to the serial path while spreading chunks across worker threads.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return [item for part in executor.map(_score_slice, slices) for item in part]


async def _upsert_scores(
    session: AsyncSession,
    scored: list[_ScoredTarget],
    student_ids: list[int],
    offering_ids: list[int],
    computed_day: date,
    computed_at: datetime,
) -> tuple[int, int, int]:
    existing: Sequence[StudentRiskScore] = (
        await session.scalars(
            select(StudentRiskScore)
            .where(StudentRiskScore.student_id.in_(student_ids))
            .where(StudentRiskScore.offering_id.in_(offering_ids))
            .where(StudentRiskScore.computed_day == computed_day)
        )
    ).all()
    by_key = {(row.student_id, row.offering_id, row.semester): row for row in existing}

    high = medium = low = 0
    for item in scored:
        match item.level:
            case RiskLevel.HIGH:
                high += 1
            case RiskLevel.MEDIUM:
                medium += 1
            case _:
                low += 1
        row = by_key.get((item.student_id, item.offering_id, item.semester))
        if row is None:
            session.add(
                StudentRiskScore(
                    student_id=item.student_id,
                    offering_id=item.offering_id,
                    semester=item.semester,
                    risk_probability=item.probability,
                    risk_level=item.level.value,
                    features=item.features,
                    computed_at=computed_at,
                    computed_day=computed_day,
                )
            )
        else:
            row.risk_probability = item.probability
            row.risk_level = item.level.value
            row.features = item.features
            row.computed_at = computed_at
    await session.flush()
    return high, medium, low


async def _stage_scores(
    session: AsyncSession,
    scored: list[_ScoredTarget],
    student_ids: list[int],
    offering_ids: list[int],
    computed_day: date,
    computed_at: datetime,
) -> tuple[int, int, int]:
    existing: Sequence[StudentRiskScoreStaging] = (
        await session.scalars(
            select(StudentRiskScoreStaging)
            .where(StudentRiskScoreStaging.student_id.in_(student_ids))
            .where(StudentRiskScoreStaging.offering_id.in_(offering_ids))
            .where(StudentRiskScoreStaging.computed_day == computed_day)
        )
    ).all()
    by_key = {(row.student_id, row.offering_id, row.semester): row for row in existing}

    high = medium = low = 0
    for item in scored:
        match item.level:
            case RiskLevel.HIGH:
                high += 1
            case RiskLevel.MEDIUM:
                medium += 1
            case _:
                low += 1
        row = by_key.get((item.student_id, item.offering_id, item.semester))
        if row is None:
            session.add(
                StudentRiskScoreStaging(
                    student_id=item.student_id,
                    offering_id=item.offering_id,
                    semester=item.semester,
                    risk_probability=item.probability,
                    risk_level=item.level.value,
                    features=item.features,
                    computed_at=computed_at,
                    computed_day=computed_day,
                    promoted_at=None,
                )
            )
        else:
            row.risk_probability = item.probability
            row.risk_level = item.level.value
            row.features = item.features
            row.computed_at = computed_at
            row.promoted_at = None
    await session.flush()
    return high, medium, low


async def run_risk_batch(
    session: AsyncSession,
    targets: list[tuple[int, int, str]] | None = None,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    started = time.perf_counter()
    cfg = settings or get_settings()
    if now is not None:
        moment = ensure_aware(now)
    else:
        moment = datetime.now(timezone.utc)

    resolved = targets if targets is not None else await _load_active_targets(session)
    resolved = list(dict.fromkeys(resolved))
    if not resolved:
        return {"processed": 0, "high": 0, "medium": 0, "low": 0, "duration_ms": 0}

    offering_ids = list({offering_id for _, offering_id, _ in resolved})
    student_ids = list({student_id for student_id, _, _ in resolved})
    expected = await _load_expected_by_offering(session, offering_ids)
    grouped = await _load_grouped_attendance(session, student_ids, offering_ids)

    chunk_size = max(int(cfg.risk_batch_chunk_size or 1000), 1)
    workers = max(int(cfg.risk_batch_workers or 1), 1)
    scored = _score_targets(
        resolved, expected, grouped, moment, cfg, chunk_size, workers
    )
    if cfg.risk_batch_dry_run:
        high, medium, low = await _stage_scores(
            session, scored, student_ids, offering_ids, moment.date(), moment
        )
    else:
        high, medium, low = await _upsert_scores(
            session, scored, student_ids, offering_ids, moment.date(), moment
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "risk batch%s: total=%d high=%d medium=%d low=%d duration_ms=%d",
        " (dry-run)" if cfg.risk_batch_dry_run else "",
        len(scored),
        high,
        medium,
        low,
        duration_ms,
    )
    return {
        "processed": len(scored),
        "high": high,
        "medium": medium,
        "low": low,
        "duration_ms": duration_ms,
    }


async def run_scheduled_risk_batch(
    settings: Settings | None = None,
) -> dict[str, int]:
    """Cron entry point: score every active enrollment and commit.

    This is the wrapper `run_risk_batch` does not have. Two things make it
    necessary rather than decorative:

    * `run_risk_batch` only ever `flush()`es. The request dependency commits on
      the way out, but a cron run has no request, so without an explicit commit
      every score it computed would be rolled back when the connection closed.
    * `database.get_session()` commits and rolls back nothing, so the rollback
      in the failure path is this function's job too.

    Failures are logged and swallowed: a scheduler job that raises is a lost
    night, and the next run is tomorrow either way. The scheduler itself must
    survive, so nothing propagates.

    Returns the batch summary, or an empty summary when the run failed.
    """
    cfg = settings or get_settings()
    empty: dict[str, int] = {
        "processed": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "duration_ms": 0,
    }

    started = time.perf_counter()
    logger.info("Risk batch started")
    async with track(JOB_RISK_BATCH), database.get_session() as session:
        try:
            summary = await run_risk_batch(session, settings=cfg)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Risk batch failed; scores left unchanged")
            return empty

    duration_s = time.perf_counter() - started
    logger.info(
        "Risk batch completed: %d students scored in %.1fs",
        summary["processed"],
        duration_s,
    )
    if summary["duration_ms"] > RISK_BATCH_RUNTIME_BUDGET_MS:
        logger.warning(
            "Risk batch exceeded its %d ms budget (%d ms); scores are still written",
            RISK_BATCH_RUNTIME_BUDGET_MS,
            summary["duration_ms"],
        )
    return summary
