from __future__ import annotations

import httpx

from main import app

# Any authenticated route works: the 401 fires in the shared auth dependency
# before the router body (and before any database access), so these tests run
# against the real app without Postgres.
_PROTECTED_ROUTE = "/api/student/dashboard"


async def _get_without_www_authenticate(headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(_PROTECTED_ROUTE, headers=headers)


async def test_missing_token_401_is_json_without_www_authenticate() -> None:
    """401 responses must stay JSON-only, with no WWW-Authenticate header.

    A ``WWW-Authenticate`` header on a 401 makes the browser raise its native
    authentication dialog before the SPA can react — the popup that appeared
    and vanished whenever a session expired. The client handles auth failures
    itself (transparent refresh, then a redirect to the login page), so the
    header must never be sent.
    """
    response = await _get_without_www_authenticate()

    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
    body = response.json()
    assert body["detail"]["code"] == "missing_token"
    assert body["detail"]["message"] == "Authentication required"


async def test_invalid_token_401_is_json_without_www_authenticate() -> None:
    """The expired/corrupt-token path must not trigger the browser dialog either."""
    response = await _get_without_www_authenticate({"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
    assert response.json()["detail"]["code"] == "invalid_token"
