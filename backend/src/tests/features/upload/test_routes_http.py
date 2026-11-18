"""HTTP-level cover for `POST /upload/presigned-url`.

The gate itself is unit-tested in `tests/shared/test_storage.py`. What only a
real request can show is the response *shape* the frontend reads, the auth
requirement, and the status codes the standard error envelope produces.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.config import Settings

from shared import storage as storage_module
from shared.enums import UserRole

ENDPOINT = "/api/upload/presigned-url"

FIVE_MIB = 5 * 1024 * 1024

BODY = {
    "filename": "evidence.pdf",
    "size_bytes": 2048,
    "content_type": "application/pdf",
}


@pytest.fixture(autouse=True)
def local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the storage backend to `local`.

    The route resolves settings through the cached `get_settings()`, which
    reads `backend/.env` — a machine with `ATTACHMENTS_STORAGE_TYPE=s3` would
    otherwise get a different backend than the assertions expect.
    """

    settings = Settings(
        debug=True,
        jwt_secret="test-secret-0123456789abcdef-0123456789",
        attachments_storage_type="local",
        attachments_local_dir="/tmp/attachments-test",
    )
    monkeypatch.setattr(storage_module, "get_settings", lambda: settings)


async def test_returns_the_fields_the_client_needs_to_upload(
    api_client: Any, auth_headers: Any
) -> None:
    response = await api_client.post(ENDPOINT, json=BODY, headers=await auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"upload_url", "object_url", "object_key", "expires_in"}
    assert body["expires_in"] == 900
    assert body["object_key"].startswith("attachments/")
    assert body["upload_url"].endswith(body["object_key"])


async def test_content_type_is_optional(api_client: Any, auth_headers: Any) -> None:
    response = await api_client.post(
        ENDPOINT,
        json={"filename": "scan.png", "size_bytes": 1024},
        headers=await auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["object_key"].endswith(".png")


async def test_filename_whitespace_is_trimmed(
    api_client: Any, auth_headers: Any
) -> None:
    response = await api_client.post(
        ENDPOINT,
        json={**BODY, "filename": "  evidence.pdf  "},
        headers=await auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["object_key"].endswith(".pdf")


@pytest.mark.parametrize("role", [UserRole.STUDENT, UserRole.PROFESSOR, UserRole.ADMIN])
async def test_any_authenticated_role_can_mint_a_url(
    api_client: Any, auth_headers: Any, role: UserRole
) -> None:
    """Both evidence-upload paths need this: student requests and professor
    Path B. Gating it to one role would break the other."""

    response = await api_client.post(
        ENDPOINT, json=BODY, headers=await auth_headers(role=role.value)
    )

    assert response.status_code == 200


async def test_anonymous_is_401(api_client: Any) -> None:
    response = await api_client.post(ENDPOINT, json=BODY)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "missing_token"


async def test_a_disallowed_type_is_400(api_client: Any, auth_headers: Any) -> None:
    response = await api_client.post(
        ENDPOINT,
        json={**BODY, "filename": "malware.exe"},
        headers=await auth_headers(),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_attachment"
    assert detail["field"] == "filename"


async def test_an_oversized_file_is_413(api_client: Any, auth_headers: Any) -> None:
    response = await api_client.post(
        ENDPOINT,
        json={**BODY, "size_bytes": FIVE_MIB + 1},
        headers=await auth_headers(),
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


async def test_a_declared_type_contradicting_the_extension_is_400(
    api_client: Any, auth_headers: Any
) -> None:
    response = await api_client.post(
        ENDPOINT,
        json={**BODY, "content_type": "application/x-msdownload"},
        headers=await auth_headers(),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_attachment"
    # The field points at the offending input, so the client can highlight it.
    assert detail["field"] == "content_type"


@pytest.mark.parametrize(
    "payload",
    [
        {"size_bytes": 1024},
        {"filename": "evidence.pdf"},
        {"filename": "", "size_bytes": 1024},
        {"filename": "evidence.pdf", "size_bytes": 0},
        {"filename": "evidence.pdf", "size_bytes": -1},
    ],
)
async def test_a_malformed_body_is_422(
    api_client: Any, auth_headers: Any, payload: dict[str, Any]
) -> None:
    response = await api_client.post(
        ENDPOINT, json=payload, headers=await auth_headers()
    )

    assert response.status_code == 422


async def test_every_url_is_unique(api_client: Any, auth_headers: Any) -> None:
    headers = await auth_headers()

    first = await api_client.post(ENDPOINT, json=BODY, headers=headers)
    second = await api_client.post(ENDPOINT, json=BODY, headers=headers)

    assert first.json()["object_key"] != second.json()["object_key"]
