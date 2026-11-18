"""Partial security-question updates answer 422, not 500.

`AuthService.change_password` accepts an optional security question/answer
pair during the forced first-login change, but the guard for a *partial* pair
raised a class the module never imported. The documented 422
`password_policy_violation` contract (api-contracts.md) therefore died as a
`NameError` 500 instead. Ruff's F821 caught the missing import when the backend
gained its lint gate (ADR-094); these tests pin the contract through the HTTP
route, including the two complete cases so the guard cannot over-trigger.
"""

from __future__ import annotations

from typing import Any

from core.security import hash_password, verify_password

from features.auth.model import User
from tests.conftest import Factories

CURRENT_PASSWORD = "CurrentPass1!"
NEW_PASSWORD = "BrandNewPass2!"

# The factory default's `.local` address is special-use; a deliverable-looking
# one keeps the suite consistent with the other auth HTTP tests.
EMAIL = "change.password.subject@isu.edu.ph"

CHANGE_PASSWORD = "/api/auth/change-password"


async def _change(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    **extra: Any,
) -> tuple[int, Any]:
    user: User = await factories.user(
        email=EMAIL,
        password_hash=hash_password(CURRENT_PASSWORD),
    )
    user_id = user.id
    # Commit the seed: a failing request rolls the session back through the
    # api_client override, and the password assertions must still see the row.
    await factories.db.commit()
    response = await api_client.post(
        CHANGE_PASSWORD,
        json={
            "current_password": CURRENT_PASSWORD,
            "new_password": NEW_PASSWORD,
            **extra,
        },
        headers=await auth_headers(user),
    )
    return user_id, response


async def _assert_password_unchanged(test_db_session: Any, user_id: int) -> None:
    """The rejected request must leave the stored credential untouched."""

    stored = await test_db_session.get(User, user_id)
    assert stored is not None
    assert verify_password(CURRENT_PASSWORD, stored.password_hash)
    assert not verify_password(NEW_PASSWORD, stored.password_hash)


async def test_question_without_answer_is_a_policy_violation(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    user_id, response = await _change(
        api_client, auth_headers, factories, security_question="First pet?"
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "password_policy_violation"
    # The client points at the field it needs to complete.
    assert detail["field"] == "security_question"
    await _assert_password_unchanged(test_db_session, user_id)


async def test_answer_without_question_is_a_policy_violation(
    api_client: Any,
    auth_headers: Any,
    factories: Factories,
    test_db_session: Any,
) -> None:
    user_id, response = await _change(
        api_client, auth_headers, factories, security_answer="Rex"
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "password_policy_violation"
    assert detail["field"] == "security_question"
    await _assert_password_unchanged(test_db_session, user_id)


async def test_complete_pair_succeeds(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    _, response = await _change(
        api_client,
        auth_headers,
        factories,
        security_question="First pet?",
        security_answer="Rex",
    )

    assert response.status_code == 204, response.text


async def test_no_pair_succeeds(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    _, response = await _change(api_client, auth_headers, factories)

    assert response.status_code == 204, response.text
