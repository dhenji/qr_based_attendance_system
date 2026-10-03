"""HTTP-level cover for the admin analytics routes.

Risk math already has service-level cover in `test_risk_batch.py`; these
tests prove what only a real request can: role gating off a real JWT, the
response shapes the frontend reads, the CSV download, and the refresh-risk
rate limit.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from features.analytics.model import StudentRiskScore, StudentRiskScoreStaging
from shared.enums import UserRole, ValidationStatus
from tests.conftest import Factories

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


async def _seed(factories: Factories) -> dict[str, Any]:
    """One program/course/offering with a session, an enrollment, and a scan."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course = await factories.course()
    offering = await factories.offering(course, program, year_level)
    student_user = await factories.user()
    student = await factories.student(year_level, student_user)
    await factories.enrollment(student, offering)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    session = await factories.session(
        offering, professor, created_at=NOW, expires_at=NOW
    )
    await factories.attendance(student, session, timestamp=NOW)
    admin = await factories.user(role=UserRole.ADMIN.value)
    return {
        "program": program,
        "year_level": year_level,
        "course": course,
        "offering": offering,
        "student": student,
        "session": session,
        "admin": admin,
        "student_user": student_user,
    }


async def _admin_headers(auth_headers: Any, seed: dict[str, Any]) -> dict[str, str]:
    return await auth_headers(seed["admin"])


async def test_overview_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.get(
        "/api/admin/analytics/overview",
        headers=await auth_headers(seed["student_user"]),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_permissions"


async def test_overview_reports_seeded_totals(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.get(
        "/api/admin/analytics/overview",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_students"] == 1
    assert body["total_courses"] == 1
    assert body["total_sessions"] == 1
    assert body["avg_compliance_rate"] == 1.0
    assert body["avg_participation_rate"] == 1.0


async def test_course_comparison_shape(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.get(
        "/api/admin/analytics/course-comparison",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    (item,) = body["items"]
    assert item["course_id"] == seed["course"].id
    assert item["course_code"] == seed["course"].course_code
    assert item["compliance_rate"] == 1.0
    assert item["total_sessions"] == 1


async def test_trends_buckets_by_day(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.get(
        "/api/admin/analytics/trends?granularity=daily",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    (item,) = body["items"]
    assert item["date"] == NOW.date().isoformat()
    assert item["compliance_rate"] == 1.0
    assert item["total_sessions"] == 1


async def test_at_risk_lists_stored_scores(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    await factories._make(
        StudentRiskScore,
        student_id=seed["student"].id,
        offering_id=seed["offering"].id,
        semester="1ST_SEM",
        risk_probability=0.85,
        risk_level="high",
        features={"absence_rate": 0.8, "max_streak": 4, "trend_slope": 0.05},
        computed_day=date(2026, 9, 30),
    )

    response = await api_client.get(
        "/api/admin/analytics/at-risk?risk_level=high",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    (item,) = body["items"]
    assert item["student_id"] == seed["student"].id
    assert item["risk_level"] == "high"
    assert item["course_code"] == seed["course"].course_code


async def test_at_risk_filter_excludes_other_levels(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    await factories._make(
        StudentRiskScore,
        student_id=seed["student"].id,
        offering_id=seed["offering"].id,
        semester="1ST_SEM",
        risk_probability=0.85,
        risk_level="high",
        features={"absence_rate": 0.8, "max_streak": 4, "trend_slope": 0.05},
        computed_day=date(2026, 9, 30),
    )

    response = await api_client.get(
        "/api/admin/analytics/at-risk?risk_level=low",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_refresh_risk_scoped_and_rate_limited(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    headers = await _admin_headers(auth_headers, seed)

    first = await api_client.post(
        f"/api/admin/analytics/refresh-risk?student_id={seed['student'].id}",
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["processed"] == 1

    second = await api_client.post(
        f"/api/admin/analytics/refresh-risk?student_id={seed['student'].id}",
        headers=headers,
    )

    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "rate_limited"


async def test_refresh_risk_offering_requires_semester(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.post(
        f"/api/admin/analytics/refresh-risk?offering_id={seed['offering'].id}",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 422


async def test_export_downloads_csv(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.post(
        "/api/admin/analytics/export",
        json={"format": "csv"},
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0].split(",")[:2] == ["course_id", "course_code"]
    assert seed["course"].course_code in lines[1]


async def test_export_pdf_is_rejected(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.post(
        "/api/admin/analytics/export",
        json={"format": "pdf"},
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


async def test_export_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.post(
        "/api/admin/analytics/export",
        json={"format": "csv"},
        headers=await auth_headers(seed["student_user"]),
    )

    assert response.status_code == 403


async def test_late_scan_lowers_compliance(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    other_user = await factories.user()
    other = await factories.student(seed["year_level"], other_user)
    await factories.enrollment(other, seed["offering"])
    await factories.attendance(
        other,
        seed["session"],
        timestamp=NOW,
        validation_status=ValidationStatus.LATE.value,
    )

    response = await api_client.get(
        "/api/admin/analytics/overview",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_students"] == 2
    assert body["avg_compliance_rate"] == 0.5
    assert body["avg_participation_rate"] == 1.0


async def _seed_staged(factories: Factories, seed: dict[str, Any]) -> None:
    await factories._make(
        StudentRiskScoreStaging,
        student_id=seed["student"].id,
        offering_id=seed["offering"].id,
        semester="1ST_SEM",
        risk_probability=0.85,
        risk_level="high",
        features={"absence_rate": 0.8, "max_streak": 4, "trend_slope": 0.05},
        computed_day=date(2026, 9, 30),
    )


async def test_risk_staging_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.get(
        "/api/admin/analytics/risk-staging",
        headers=await auth_headers(seed["student_user"]),
    )

    assert response.status_code == 403


async def test_risk_staging_lists_seeded_rows(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    await _seed_staged(factories, seed)

    response = await api_client.get(
        "/api/admin/analytics/risk-staging",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    (item,) = body["items"]
    assert item["student_id"] == seed["student"].id
    assert item["risk_level"] == "high"
    assert item["promoted_at"] is None


async def test_risk_staging_unpromoted_only_hides_promoted(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    await _seed_staged(factories, seed)
    headers = await _admin_headers(auth_headers, seed)

    promoted = await api_client.post(
        "/api/admin/analytics/risk-staging/promote",
        headers=headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["promoted"] == 1

    hidden = await api_client.get(
        "/api/admin/analytics/risk-staging?unpromoted_only=true",
        headers=headers,
    )
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    shown = await api_client.get(
        "/api/admin/analytics/risk-staging",
        headers=headers,
    )
    assert shown.status_code == 200
    assert shown.json()["total"] == 1
    assert shown.json()["items"][0]["promoted_at"] is not None


async def test_risk_staging_promote_round_trip(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)
    await _seed_staged(factories, seed)
    headers = await _admin_headers(auth_headers, seed)

    first = await api_client.post(
        "/api/admin/analytics/risk-staging/promote",
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["promoted"] == 1
    assert first.json()["skipped"] == 0

    second = await api_client.post(
        "/api/admin/analytics/risk-staging/promote",
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["promoted"] == 0
    assert second.json()["skipped"] == 1

    live = await api_client.get(
        "/api/admin/analytics/at-risk?risk_level=high",
        headers=headers,
    )
    assert live.status_code == 200
    assert live.json()["total"] == 1


async def test_risk_staging_promote_offering_requires_semester(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed(factories)

    response = await api_client.post(
        f"/api/admin/analytics/risk-staging/promote?offering_id={seed['offering'].id}",
        headers=await _admin_headers(auth_headers, seed),
    )

    assert response.status_code == 422
