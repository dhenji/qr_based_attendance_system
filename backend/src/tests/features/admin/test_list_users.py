"""`AdminService.list_users` / `GET /admin/users` filter and pagination behaviour.

`test_admin_reset_password.py` already covers the writes on `/admin/users`; this
file pins the read side, which had never been exercised at all. That gap is what
let the empty-filter `ArgumentError` (#209) reach production: the page load sends
no query parameters, `_users_filters` returned `[]`, and `.where([])` blew up
with a 500. `test_lists_with_no_filters_supplied` is the regression for exactly
that.
"""

from __future__ import annotations

from typing import Any

from shared.enums import UserRole

from features.admin.service import AdminService
from tests.conftest import Factories

ADMIN_EMAIL = "list.admin@isu.edu.ph"
STUDENT_EMAIL = "list.student@isu.edu.ph"
PROFESSOR_EMAIL = "list.professor@isu.edu.ph"


async def _seed(factories: Factories) -> dict[str, Any]:
    """A super_admin, a student-linked account and a professor-linked account.

    The roster rows carry distinct names so a search term can be attributed to
    the right join. All three are active.
    """

    program = await factories.program()
    year_level = await factories.year_level(program)

    admin = await factories.user(
        email=ADMIN_EMAIL,
        role=UserRole.SUPER_ADMIN.value,
        is_active=True,
    )
    student_user = await factories.user(
        email=STUDENT_EMAIL,
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    await factories.student(
        year_level,
        user=student_user,
        email=STUDENT_EMAIL,
        first_name="Wilhelmina",
        last_name="Zephaniah",
    )
    professor_user = await factories.user(
        email=PROFESSOR_EMAIL,
        role=UserRole.PROFESSOR.value,
        is_active=True,
    )
    await factories.professor(
        user=professor_user,
        email=PROFESSOR_EMAIL,
        first_name="Bartholomew",
        last_name="Quillfeather",
    )
    return {
        "admin": admin,
        "student_user": student_user,
        "professor_user": professor_user,
    }


def _by_email(result: Any) -> dict[str, Any]:
    return {item.email: item for item in result.items}


# -- the regression: no filters at all -------------------------------------


async def test_lists_with_no_filters_supplied(
    test_db_session: Any, factories: Factories
) -> None:
    """The page load sends no query parameters; that must not raise.

    `_users_filters` returns `[]` in that case, and `.where([])` used to raise
    `ArgumentError: SQL expression for WHERE/HAVING role expected, got []`.
    """

    await _seed(factories)
    await test_db_session.commit()

    result = await AdminService(test_db_session).list_users(
        search=None, role=None, is_active=None, page=1, size=20
    )

    assert result.total == 3
    assert len(result.items) == 3


async def test_list_users_without_filters_over_http(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    """`GET /admin/users` with a super_admin token and no query params -> 200.

    This is the exact request the User Management page makes on load.
    """

    seeded = await _seed(factories)
    admin = seeded["admin"]
    await test_db_session.commit()

    response = await api_client.get(
        "/api/admin/users", headers=await auth_headers(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert {item["email"] for item in body["items"]} == {
        ADMIN_EMAIL,
        STUDENT_EMAIL,
        PROFESSOR_EMAIL,
    }


async def test_empty_search_means_no_search(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    """`?search=` is falsy, so it must behave like no search at all.

    An empty string must not fall through to an ILIKE on `%%` (which would match
    every row for a different reason) — and, more to the point, must not raise.
    """

    seeded = await _seed(factories)
    admin = seeded["admin"]
    await test_db_session.commit()

    response = await api_client.get(
        "/api/admin/users?search=", headers=await auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_empty_is_active_is_rejected_not_a_server_error(
    api_client: Any, auth_headers: Any, factories: Factories, test_db_session: Any
) -> None:
    """`?is_active=` is a malformed boolean, so FastAPI rejects it with a 422.

    The point is that it fails on the request-validation boundary with a 4xx and
    never reaches the service — it must not surface as a 500. The frontend only
    sends `is_active` when the toggle is set, so this is a hand-crafted request.
    """

    seeded = await _seed(factories)
    admin = seeded["admin"]
    await test_db_session.commit()

    response = await api_client.get(
        "/api/admin/users?is_active=", headers=await auth_headers(admin)
    )

    assert 400 <= response.status_code < 500
    assert response.status_code != 500


# -- each filter narrows the result ----------------------------------------


async def test_search_matches_a_student_roster_name(
    test_db_session: Any, factories: Factories
) -> None:
    await _seed(factories)
    await test_db_session.commit()

    result = await AdminService(test_db_session).list_users(
        search="wilhelmina", role=None, is_active=None, page=1, size=20
    )

    assert [item.email for item in result.items] == [STUDENT_EMAIL]
    matched = _by_email(result)[STUDENT_EMAIL]
    assert matched.first_name == "Wilhelmina"
    assert matched.last_name == "Zephaniah"


async def test_search_matches_a_professor_roster_name(
    test_db_session: Any, factories: Factories
) -> None:
    await _seed(factories)
    await test_db_session.commit()

    result = await AdminService(test_db_session).list_users(
        search="quillfeather", role=None, is_active=None, page=1, size=20
    )

    assert [item.email for item in result.items] == [PROFESSOR_EMAIL]


async def test_search_matches_email(test_db_session: Any, factories: Factories) -> None:
    await _seed(factories)
    await test_db_session.commit()

    by_student = await AdminService(test_db_session).list_users(
        search="list.student", role=None, is_active=None, page=1, size=20
    )
    by_email = await AdminService(test_db_session).list_users(
        search=ADMIN_EMAIL, role=None, is_active=None, page=1, size=20
    )

    assert [item.email for item in by_student.items] == [STUDENT_EMAIL]
    assert [item.email for item in by_email.items] == [ADMIN_EMAIL]


async def test_role_filter_narrows(test_db_session: Any, factories: Factories) -> None:
    await _seed(factories)
    await test_db_session.commit()

    result = await AdminService(test_db_session).list_users(
        search=None, role=UserRole.PROFESSOR, is_active=None, page=1, size=20
    )

    assert [item.email for item in result.items] == [PROFESSOR_EMAIL]
    assert result.total == 1


async def test_is_active_filter_narrows(
    test_db_session: Any, factories: Factories
) -> None:
    seeded = await _seed(factories)
    seeded["admin"].is_active = False
    await test_db_session.commit()

    result = await AdminService(test_db_session).list_users(
        search=None, role=None, is_active=False, page=1, size=20
    )

    assert [item.email for item in result.items] == [ADMIN_EMAIL]


async def test_filters_combine(test_db_session: Any, factories: Factories) -> None:
    await _seed(factories)
    await test_db_session.commit()

    hit = await AdminService(test_db_session).list_users(
        search="quillfeather",
        role=UserRole.PROFESSOR,
        is_active=True,
        page=1,
        size=20,
    )
    miss = await AdminService(test_db_session).list_users(
        search="quillfeather",
        role=UserRole.STUDENT,
        is_active=True,
        page=1,
        size=20,
    )

    assert [item.email for item in hit.items] == [PROFESSOR_EMAIL]
    assert miss.total == 0
    assert miss.items == []


# -- pagination -------------------------------------------------------------


async def test_pagination_reports_totals_across_pages(
    test_db_session: Any, factories: Factories
) -> None:
    await _seed(factories)
    await test_db_session.commit()

    first = await AdminService(test_db_session).list_users(
        search=None, role=None, is_active=None, page=1, size=2
    )
    second = await AdminService(test_db_session).list_users(
        search=None, role=None, is_active=None, page=2, size=2
    )

    assert first.total == 3
    assert second.total == 3
    assert len(first.items) == 2
    assert len(second.items) == 1
    assert first.page == 1
    assert second.page == 2
    # No row appears on both pages.
    assert {item.email for item in first.items}.isdisjoint(
        {item.email for item in second.items}
    )
