"""HTTP-level cover for ``/admin/face-enrollment/{student_id}``.

The service-level gates and the router contract are already covered by
``test_face_enrollment_service.py``. What only a real request can prove is
the multipart wiring, the admin role gate, the status codes the standard
error envelope produces, and that a successful upload lands a row in the DB.
"""

from __future__ import annotations

from typing import Any

import pytest
from shared.enums import UserRole
from shared.face_quality import FaceQualityResult
from tests.conftest import Factories


ENDPOINT = "/api/admin/face-enrollment"
VALID_BYTES = b"\xff\xd8\xff fake-jpeg-bytes"
CORRUPT_BYTES = b"not an image at all"


@pytest.fixture(autouse=True)
def _stub_quality_and_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the HTTP tests fast and deterministic.

    The real quality gates + MobileFaceNet inference need model files and a
    face in the image; the service-level suite already exercises them. Here
    we only care about the route wiring, auth, and status codes.
    """
    import features.face_enrollment.service as fe_service

    monkeypatch.setattr(fe_service, "assess_image_bytes", lambda _content: FaceQualityResult(ok=True))
    monkeypatch.setattr(
        fe_service,
        "generate_embedding_from_images",
        lambda front, left, right, algorithm="mobilefacenet-v1": (b"blob", "mobilefacenet-v1"),
    )


async def _seed_student(factories: Factories) -> Any:
    program = await factories.program()
    year_level = await factories.year_level(program)
    return await factories.student(year_level)


async def test_status_not_enrolled_then_enrolled(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    before = await api_client.get(f"{ENDPOINT}/{student.id}", headers=headers)
    assert before.status_code == 200
    assert before.json()["enrolled"] is False

    upload = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["student_id"] == student.id
    assert body["face_embedding_version"] == 1

    after = await api_client.get(f"{ENDPOINT}/{student.id}", headers=headers)
    assert after.status_code == 200
    assert after.json()["enrolled"] is True
    assert after.json()["face_embedding_version"] == 1


async def test_upload_bumps_version_on_reenroll(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    first = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert first.status_code == 201

    second = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert second.status_code == 201
    assert second.json()["face_embedding_version"] == 2


async def test_revoke_clears_enrollment(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )

    revoke = await api_client.delete(f"{ENDPOINT}/{student.id}", headers=headers)
    assert revoke.status_code == 204

    status = await api_client.get(f"{ENDPOINT}/{student.id}", headers=headers)
    assert status.json()["enrolled"] is False


async def test_empty_photo_is_400(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", b"", "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_image"
    assert "is empty" in detail["message"]


async def test_oversized_photo_is_400(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    big = b"x" * (5 * 1024 * 1024 + 1)
    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", big, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_image"
    assert "exceeds" in detail["message"]


async def test_corrupt_photo_is_400(
    api_client: Any, auth_headers: Any, factories: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    import features.face_enrollment.service as fe_service

    monkeypatch.setattr(
        fe_service,
        "assess_image_bytes",
        lambda _content: FaceQualityResult(ok=False, code="invalid_image", message="invalid image"),
    )

    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", CORRUPT_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_image"


async def test_quality_failure_is_422(
    api_client: Any, auth_headers: Any, factories: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    import features.face_enrollment.service as fe_service

    monkeypatch.setattr(
        fe_service,
        "assess_image_bytes",
        lambda _content: FaceQualityResult(ok=False, code="quality_too_low", message="Face too small"),
    )

    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "quality_too_low"


async def test_no_face_detected_is_400(
    api_client: Any, auth_headers: Any, factories: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    import features.face_enrollment.service as fe_service

    monkeypatch.setattr(
        fe_service,
        "assess_image_bytes",
        lambda _content: FaceQualityResult(ok=False, code="no_face_detected", message="No face detected"),
    )

    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "no_face_detected"


async def test_embedding_failure_is_400(
    api_client: Any, auth_headers: Any, factories: Factories, monkeypatch: pytest.MonkeyPatch
) -> None:
    import features.face_enrollment.service as fe_service
    from shared.face_embedding_generator import FaceEmbeddingGenerationError

    def _raise(*_a, **_kw):
        raise FaceEmbeddingGenerationError("boom")

    monkeypatch.setattr(fe_service, "generate_embedding_from_images", _raise)

    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "no_face_detected"


async def test_missing_field_is_422(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    student = await _seed_student(factories)

    response = await api_client.post(
        f"{ENDPOINT}/{student.id}",
        files={
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_requires_admin_role(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    student_user = await factories.user(role=UserRole.STUDENT.value)
    headers = await auth_headers(student_user)
    # need a student row owned by someone; create via admin? factory only. Use any student id 1 (may not exist -> 404/403).
    # Create a student row first as admin? We'll just hit endpoint with id=1.
    response = await api_client.get(f"{ENDPOINT}/1", headers=headers)
    assert response.status_code == 403

    professor = await factories.user(role=UserRole.PROFESSOR.value)
    prof_headers = await auth_headers(professor)
    response2 = await api_client.get(f"{ENDPOINT}/1", headers=prof_headers)
    assert response2.status_code == 403


async def test_anonymous_is_401(api_client: Any) -> None:
    response = await api_client.get(f"{ENDPOINT}/1")
    assert response.status_code == 401


async def test_unknown_student_is_404(
    api_client: Any, auth_headers: Any, factories: Factories
) -> None:
    admin = await factories.user(role=UserRole.ADMIN.value)
    headers = await auth_headers(admin)
    await factories.db.commit()

    get_resp = await api_client.get(f"{ENDPOINT}/999999", headers=headers)
    assert get_resp.status_code == 404

    del_resp = await api_client.delete(f"{ENDPOINT}/999999", headers=headers)
    assert del_resp.status_code == 404

    post_resp = await api_client.post(
        f"{ENDPOINT}/999999",
        files={
            "front": ("front.jpg", VALID_BYTES, "image/jpeg"),
            "left": ("left.jpg", VALID_BYTES, "image/jpeg"),
            "right": ("right.jpg", VALID_BYTES, "image/jpeg"),
        },
        headers=headers,
    )
    assert post_resp.status_code == 404