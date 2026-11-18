"""HTTP-level cover for the admin analytics routes.

Risk math already has service-level cover in `test_risk_batch.py`; these
tests prove what only a real request can: role gating off a real JWT, the
response shapes the frontend reads, the CSV download, and the refresh-risk
rate limit.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from shared.enums import UserRole, ValidationStatus

from features.analytics.model import StudentRiskScore, StudentRiskScoreStaging
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


async def test_course_comparison_splits_cohorts(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """One course offered to two programs is two rows, not one blended row.

    Regression for #277: grouping by course id alone merged both cohorts and
    labelled the merged row with whichever offering happened to come first.
    """
    program_a = await factories.program()
    year_a = await factories.year_level(program_a)
    program_b = await factories.program()
    year_b = await factories.year_level(program_b)
    course = await factories.course()
    offering_a = await factories.offering(course, program_a, year_a)
    offering_b = await factories.offering(course, program_b, year_b)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    session_a = await factories.session(
        offering_a, professor, created_at=NOW, expires_at=NOW
    )
    session_b = await factories.session(
        offering_b, professor, created_at=NOW, expires_at=NOW
    )

    # Cohort A: one of two enrolled students present (0.5). Cohort B: one of
    # one (1.0). A course-id grouping would blend these to 2/3.
    student_a1 = await factories.student(year_a, await factories.user())
    student_a2 = await factories.student(year_a, await factories.user())
    await factories.enrollment(student_a1, offering_a)
    await factories.enrollment(student_a2, offering_a)
    await factories.attendance(student_a1, session_a, timestamp=NOW)
    student_b = await factories.student(year_b, await factories.user())
    await factories.enrollment(student_b, offering_b)
    await factories.attendance(student_b, session_b, timestamp=NOW)
    admin = await factories.user(role=UserRole.ADMIN.value)

    response = await api_client.get(
        "/api/admin/analytics/course-comparison?size=200",
        headers=await auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    by_cohort = {
        (row["program_id"], row["year_level_id"]): row for row in body["items"]
    }
    assert set(by_cohort) == {(program_a.id, year_a.id), (program_b.id, year_b.id)}
    row_a = by_cohort[(program_a.id, year_a.id)]
    row_b = by_cohort[(program_b.id, year_b.id)]
    assert row_a["course_id"] == course.id
    assert row_b["course_id"] == course.id
    assert row_a["compliance_rate"] == 0.5
    assert row_b["compliance_rate"] == 1.0
    assert row_a["total_sessions"] == 1
    assert row_b["total_sessions"] == 1


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


# --- Scoped course picker (#279) -------------------------------------------
#
# The rail's course control now reads courses-with-an-offering-in-scope, and
# Overview/At-Risk/Staging honor `course_ids` the same way the comparison and
# trends tabs already did. These tests seed two courses in *one* program so a
# `course_ids` filter is the only thing that can separate them.


async def _seed_scope(factories: Factories) -> dict[str, Any]:
    """Two courses, each with its own offering/student, in one program."""
    program = await factories.program()
    year_level = await factories.year_level(program)
    course_a = await factories.course(course_code="AAA101", course_name="Alpha")
    course_b = await factories.course(course_code="BBB101", course_name="Bravo")
    offering_a = await factories.offering(course_a, program, year_level)
    offering_b = await factories.offering(course_b, program, year_level)
    student_a = await factories.student(year_level, await factories.user())
    student_b = await factories.student(year_level, await factories.user())
    await factories.enrollment(student_a, offering_a)
    await factories.enrollment(student_b, offering_b)
    professor_user = await factories.user(role=UserRole.PROFESSOR.value)
    professor = await factories.professor(professor_user)
    session_a = await factories.session(
        offering_a, professor, created_at=NOW, expires_at=NOW
    )
    session_b = await factories.session(
        offering_b, professor, created_at=NOW, expires_at=NOW
    )
    await factories.attendance(student_a, session_a, timestamp=NOW)
    await factories.attendance(student_b, session_b, timestamp=NOW)
    admin = await factories.user(role=UserRole.ADMIN.value)
    return {
        "program": program,
        "year_level": year_level,
        "course_a": course_a,
        "course_b": course_b,
        "offering_a": offering_a,
        "offering_b": offering_b,
        "student_a": student_a,
        "student_b": student_b,
        "admin": admin,
    }


async def _stage_row(
    factories: Factories,
    student: Any,
    offering: Any,
    *,
    prob: float = 0.85,
) -> None:
    await factories._make(
        StudentRiskScoreStaging,
        student_id=student.id,
        offering_id=offering.id,
        semester="1ST_SEM",
        risk_probability=prob,
        risk_level="high",
        features={"absence_rate": 0.7, "max_streak": 3, "trend_slope": 0.0},
        computed_day=date(2026, 9, 30),
    )


async def test_course_options_requires_admin(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    await _seed_scope(factories)
    viewer = await factories.user()

    response = await api_client.get(
        "/api/admin/analytics/course-options",
        headers=await auth_headers(viewer),
    )

    assert response.status_code == 403


async def test_course_options_lists_only_in_scope_courses(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """A course with no offering in scope must not be offered as an option."""
    seed = await _seed_scope(factories)
    orphan = await factories.course(course_code="ZZZ999", course_name="Orphan")

    response = await api_client.get(
        f"/api/admin/analytics/course-options?program_id={seed['program'].id}",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [i["course_code"] for i in body["items"]] == ["AAA101", "BBB101"]
    assert orphan.id not in {i["course_id"] for i in body["items"]}


async def test_course_options_search_matches_code_or_name(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_scope(factories)
    headers = await auth_headers(seed["admin"])

    by_code = await api_client.get(
        "/api/admin/analytics/course-options?q=bbb", headers=headers
    )
    assert [i["course_code"] for i in by_code.json()["items"]] == ["BBB101"]

    by_name = await api_client.get(
        "/api/admin/analytics/course-options?q=Ravo", headers=headers
    )
    assert [i["course_code"] for i in by_name.json()["items"]] == ["BBB101"]

    no_match = await api_client.get(
        "/api/admin/analytics/course-options?q=nomatch", headers=headers
    )
    assert no_match.json() == {"items": [], "total": 0}


async def test_course_options_rejects_overlong_query(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_scope(factories)

    response = await api_client.get(
        f"/api/admin/analytics/course-options?q={'x' * 101}",
        headers=await auth_headers(seed["admin"]),
    )

    assert response.status_code == 422


async def test_overview_honors_course_ids(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_scope(factories)
    headers = await auth_headers(seed["admin"])

    unfiltered = await api_client.get("/api/admin/analytics/overview", headers=headers)
    assert unfiltered.json()["total_courses"] == 2
    assert unfiltered.json()["total_sessions"] == 2

    filtered = await api_client.get(
        f"/api/admin/analytics/overview?course_ids={seed['course_a'].id}",
        headers=headers,
    )
    body = filtered.json()
    assert body["total_courses"] == 1
    assert body["total_sessions"] == 1
    assert body["total_students"] == 1


async def test_at_risk_honors_course_ids(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_scope(factories)
    for student, offering, prob in (
        (seed["student_a"], seed["offering_a"], 0.9),
        (seed["student_b"], seed["offering_b"], 0.8),
    ):
        await factories._make(
            StudentRiskScore,
            student_id=student.id,
            offering_id=offering.id,
            semester="1ST_SEM",
            risk_probability=prob,
            risk_level="high",
            features={"absence_rate": 0.7, "max_streak": 3, "trend_slope": 0.0},
            computed_day=date(2026, 9, 30),
        )
    headers = await auth_headers(seed["admin"])

    unfiltered = await api_client.get("/api/admin/analytics/at-risk", headers=headers)
    assert unfiltered.json()["total"] == 2

    filtered = await api_client.get(
        f"/api/admin/analytics/at-risk?course_ids={seed['course_a'].id}",
        headers=headers,
    )
    body = filtered.json()
    assert body["total"] == 1
    assert body["items"][0]["course_code"] == "AAA101"


async def test_risk_staging_honors_course_ids(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    seed = await _seed_scope(factories)
    await _stage_row(factories, seed["student_a"], seed["offering_a"])
    await _stage_row(factories, seed["student_b"], seed["offering_b"])
    headers = await auth_headers(seed["admin"])

    unfiltered = await api_client.get(
        "/api/admin/analytics/risk-staging?unpromoted_only=true", headers=headers
    )
    assert unfiltered.json()["total"] == 2

    filtered = await api_client.get(
        "/api/admin/analytics/risk-staging"
        f"?unpromoted_only=true&course_ids={seed['course_a'].id}",
        headers=headers,
    )
    body = filtered.json()
    assert body["total"] == 1
    assert body["items"][0]["course_code"] == "AAA101"


async def test_risk_staging_promote_honors_course_ids(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    """#279 behaviour change: promote acts on the rail's course scope.

    Previously the POST ignored program/year/course, so promoting a filtered
    review list promoted every unpromoted row in the semester.
    """
    seed = await _seed_scope(factories)
    await _stage_row(factories, seed["student_a"], seed["offering_a"], prob=0.9)
    await _stage_row(factories, seed["student_b"], seed["offering_b"], prob=0.8)
    headers = await auth_headers(seed["admin"])

    response = await api_client.post(
        f"/api/admin/analytics/risk-staging/promote?course_ids={seed['course_a'].id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["promoted"] == 1

    # Only course A reached the live scores; course B stays staged.
    live_b = await api_client.get(
        f"/api/admin/analytics/at-risk?course_ids={seed['course_b'].id}",
        headers=headers,
    )
    assert live_b.json()["total"] == 0

    still_staged = await api_client.get(
        "/api/admin/analytics/risk-staging"
        f"?unpromoted_only=true&course_ids={seed['course_b'].id}",
        headers=headers,
    )
    assert still_staged.json()["total"] == 1
