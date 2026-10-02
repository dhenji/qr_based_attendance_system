from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from features.analytics.batch import (
    compute_features,
    compute_weekly_absences,
    evaluate_risk,
    linear_regression_slope,
    run_risk_batch,
)
from features.analytics.model import StudentRiskScore
from features.analytics.service import AnalyticsService
from shared.enums import RiskLevel
from tests.conftest import Factories


def _record(status: str, moment: datetime, sync: str = "synced") -> SimpleNamespace:
    return SimpleNamespace(
        validation_status=status, sync_status=sync, timestamp=moment
    )


def test_slope_flat_is_zero() -> None:
    assert linear_regression_slope([1.0, 2.0, 3.0, 4.0], [2.0, 2.0, 2.0, 2.0]) == 0.0


def test_slope_rising_is_positive() -> None:
    slope = linear_regression_slope([1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 3.0])
    assert slope == pytest.approx(1.0)


def test_slope_needs_two_points() -> None:
    assert linear_regression_slope([1.0], [5.0]) == 0.0
    assert linear_regression_slope([1.0, 1.0], [2.0, 3.0]) == 0.0


def test_weekly_absences_buckets_last_four_weeks() -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    moments = [
        datetime(2026, 9, 29, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 22, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 22, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
    ]
    assert compute_weekly_absences(moments, now) == [3, 1, 2, 1]


def test_pending_does_not_break_streak_but_late_does(now: datetime) -> None:
    with_pending = [
        _record("absent", now - timedelta(days=3)),
        _record("pending", now - timedelta(days=2)),
        _record("absent", now - timedelta(days=1)),
    ]
    assert compute_features(with_pending, 32, now)["max_streak"] == 2

    broken = [
        _record("absent", now - timedelta(days=3)),
        _record("late", now - timedelta(days=2)),
        _record("absent", now - timedelta(days=1)),
    ]
    assert compute_features(broken, 32, now)["max_streak"] == 1


def test_rejected_excluded_and_zero_expected_guarded(now: datetime) -> None:
    records = [
        _record("rejected", now - timedelta(days=1)),
        _record("absent", now - timedelta(days=1)),
    ]
    features = compute_features(records, 0, now)
    assert features["absence_rate"] == 0.0
    assert features["actual_sessions"] == 1
    assert features["absent_count"] == 1


def test_sync_lag_counts_only_stale_pending(now: datetime) -> None:
    records = [
        _record("present", now - timedelta(hours=25), sync="pending"),
        _record("present", now - timedelta(hours=2), sync="pending"),
        _record("present", now - timedelta(hours=30), sync="synced"),
    ]
    assert compute_features(records, 32, now)["sync_lag"] == 1


def test_heuristic_first_match_wins(settings: Settings) -> None:
    high_rate = {
        "absence_rate": 0.5,
        "max_streak": 0,
        "sync_lag": 0,
        "trend_slope": 0.0,
    }
    assert evaluate_risk(high_rate, settings)[0] == RiskLevel.HIGH

    streak = {
        "absence_rate": 0.0,
        "max_streak": 5,
        "sync_lag": 0,
        "trend_slope": 0.0,
    }
    assert evaluate_risk(streak, settings)[0] == RiskLevel.HIGH

    medium_rate = {
        "absence_rate": 0.2,
        "max_streak": 0,
        "sync_lag": 0,
        "trend_slope": 0.0,
    }
    assert evaluate_risk(medium_rate, settings)[0] == RiskLevel.MEDIUM

    lag = {"absence_rate": 0.0, "max_streak": 0, "sync_lag": 9, "trend_slope": 0.0}
    assert evaluate_risk(lag, settings)[0] == RiskLevel.MEDIUM

    improving = {
        "absence_rate": 0.0,
        "max_streak": 0,
        "sync_lag": 0,
        "trend_slope": -0.5,
    }
    assert evaluate_risk(improving, settings)[0] == RiskLevel.MEDIUM

    clean = {"absence_rate": 0.0, "max_streak": 0, "sync_lag": 0, "trend_slope": 0.0}
    assert evaluate_risk(clean, settings)[0] == RiskLevel.LOW


def test_probability_weights_and_clamp(settings: Settings) -> None:
    features = {
        "absence_rate": 0.5625,
        "max_streak": 12,
        "sync_lag": 0,
        "trend_slope": 0.0,
    }
    _, probability = evaluate_risk(features, settings)
    assert probability == pytest.approx(0.65)


async def _high_absence_stack(
    factories: Factories, now: datetime, absent_count: int = 18
) -> dict:
    stack = await factories.full_stack()
    offering = stack["offering"]
    offering.semester_weeks = 16
    offering.sessions_per_week = 2
    student = stack["student"]
    professor = stack["professor"]
    base = now - timedelta(days=20)
    sessions = [
        await factories.session(
            offering,
            professor,
            scheduled_start_time=base + timedelta(days=i),
            scheduled_end_time=base + timedelta(days=i, minutes=60),
        )
        for i in range(absent_count)
    ]
    for session in sessions:
        await factories.attendance(
            student,
            session,
            validation_status="absent",
            sync_status="synced",
            timestamp=now - timedelta(hours=1),
        )
    return stack


async def test_run_risk_batch_writes_high_row(
    test_db_session: AsyncSession, factories: Factories, now: datetime
) -> None:
    stack = await _high_absence_stack(factories, now)
    summary = await run_risk_batch(test_db_session, now=now)
    assert summary["processed"] == 1
    assert summary["high"] == 1

    rows = (await test_db_session.scalars(select(StudentRiskScore))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.student_id == stack["student"].id
    assert row.offering_id == stack["offering"].id
    assert row.risk_level == RiskLevel.HIGH.value
    assert float(row.risk_probability) >= 0.65
    assert row.computed_day == now.date()
    assert row.features["absent_count"] == 18
    assert row.features["expected_sessions"] == 32


async def test_run_risk_batch_is_idempotent_same_day(
    test_db_session: AsyncSession, factories: Factories, now: datetime
) -> None:
    await _high_absence_stack(factories, now)
    first = await run_risk_batch(test_db_session, now=now)
    second = await run_risk_batch(test_db_session, now=now)
    assert first["processed"] == second["processed"] == 1
    count = len((await test_db_session.scalars(select(StudentRiskScore))).all())
    assert count == 1


async def test_refresh_risk_scoped_and_full(
    test_db_session: AsyncSession, factories: Factories, now: datetime
) -> None:
    stack = await _high_absence_stack(factories, now)
    service = AnalyticsService(test_db_session)

    scoped = await service.refresh_risk(student_id=stack["student"].id)
    assert scoped.processed == 1
    assert scoped.high == 1

    full = await service.refresh_risk()
    assert full.processed == 1
    assert full.high == 1


async def test_refresh_risk_requires_semester_with_offering(
    test_db_session: AsyncSession,
) -> None:
    service = AnalyticsService(test_db_session)
    with pytest.raises(Exception):
        await service.refresh_risk(offering_id=1)
