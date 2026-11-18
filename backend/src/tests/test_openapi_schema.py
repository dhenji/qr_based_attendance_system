"""The OpenAPI document must generate, with the excuse filters typed.

`features/excuse/professor_router.py` annotated eight range filters with
`datetime` but never imported it. Since the module uses
`from __future__ import annotations`, those annotations stayed unresolved
`ForwardRef`s: `/openapi.json` answered 500, and any request carrying a date
filter failed inside the service while unfiltered requests worked. Ruff's F821
caught the missing import when the backend gained its lint gate (ADR-094);
these tests pin the schema-level repair.

Driven over the real app like `test_unauthorized_response_headers.py`: the
schema endpoint is what a broken annotation actually takes down.
"""

from __future__ import annotations

from typing import Any

import httpx

from main import app

EXCUSE_LIST_PATH = "/api/professor/excuse-requests"

# Both spellings the endpoint accepts: the UI sends `from`/`to`, while
# `date_from`/`date_to` are their canonical aliases.
DATE_FILTERS = (
    "from",
    "date_from",
    "to",
    "date_to",
    "submitted_from",
    "submitted_to",
    "reviewed_from",
    "reviewed_to",
)


async def _get_openapi() -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get("/openapi.json")


async def test_openapi_json_is_served() -> None:
    response = await _get_openapi()

    assert response.status_code == 200, response.text


async def test_excuse_date_filters_are_typed_datetimes() -> None:
    schema: dict[str, Any] = (await _get_openapi()).json()
    parameters = schema["paths"][EXCUSE_LIST_PATH]["get"]["parameters"]
    by_name: dict[str, dict[str, Any]] = {p["name"]: p["schema"] for p in parameters}

    for name in DATE_FILTERS:
        formats = {option.get("format") for option in by_name[name].get("anyOf", [])}
        assert "date-time" in formats, f"{name} is not typed as a datetime"
