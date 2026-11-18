from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from shared.enums import AuditAction, AuditEntity
from shared.face_quality import FaceQualityResult

import features.face_enrollment.service as face_enrollment_service
from features.face_enrollment import router as face_router
from features.face_enrollment.exceptions import InvalidImageException
from features.face_enrollment.service import FaceEnrollmentService
from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from features.system.model import AuditLog

# Bypass quality gates in unit tests (quality is enforced via shared.face_quality)
face_enrollment_service.assess_image_bytes = lambda _content: FaceQualityResult(ok=True)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

_SETTINGS = SimpleNamespace(attachments_max_bytes=1024, face_embedding_version=1)
_PHOTO = b"\xff\xd8\xff fake-jpeg-bytes"


class _FakeSession:
    def __init__(self, *, objs: tuple = ()):
        self.store = {(type(o), o.id): o for o in objs}
        self.added: list = []

    async def get(self, model, ident):
        return self.store.get((model, ident))

    async def flush(self):
        pass

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 100
        self.added.append(obj)


def _service(session, settings: Any = _SETTINGS):
    return FaceEnrollmentService(session, settings)


def _student(**overrides):
    values: dict[str, Any] = {
        "id": 1,
        "user_id": None,
        "student_id": "S001",
        "email": "ada@example.com",
        "first_name": "Ada",
        "middle_name": None,
        "last_name": "Lovelace",
        "year_level_id": 1,
        "section": "B",
        "is_active": True,
        "face_embedding": None,
        "face_enrolled_at": None,
        "face_embedding_version": 0,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Student(**values)


def _run(coro):
    return asyncio.run(coro)


def _enroll_kwargs(**overrides):
    kwargs: dict[str, Any] = {
        "front": _PHOTO,
        "left": _PHOTO,
        "right": _PHOTO,
        "front_content_type": "image/jpeg",
        "left_content_type": "image/jpeg",
        "right_content_type": "image/jpeg",
    }
    kwargs.update(overrides)
    return kwargs


# -- status -----------------------------------------------------------------


def test_status_not_enrolled_when_blob_null() -> None:
    session = _FakeSession(objs=(_student(),))

    result = _run(_service(session).get_face_enrollment_status(student_id=1))

    assert result.enrolled is False
    assert result.face_enrolled_at is None
    assert result.face_embedding_version is None


def test_status_enrolled_when_blob_set() -> None:
    session = _FakeSession(
        objs=(
            _student(
                face_embedding=b"blob",
                face_enrolled_at=NOW,
                face_embedding_version=3,
            ),
        )
    )

    result = _run(_service(session).get_face_enrollment_status(student_id=1))

    assert result.enrolled is True
    assert result.face_enrolled_at == NOW
    assert result.face_embedding_version == 3


def test_status_unknown_student_404() -> None:
    session = _FakeSession()

    with pytest.raises(StudentNotFoundException):
        _run(_service(session).get_face_enrollment_status(student_id=9))


# -- enroll -----------------------------------------------------------------


def test_enroll_writes_stub_blob_and_bumps_version() -> None:
    session = _FakeSession(objs=(_student(),))

    result = _run(
        _service(session).enroll_face(student_id=1, actor_id=7, **_enroll_kwargs())
    )

    student = session.store[(Student, 1)]
    assert student.face_embedding is not None
    # New behavior: real embedding blob (versioned binary format)
    from shared.face_embeddings import deserialize_embedding, is_stub_embedding

    assert not is_stub_embedding(student.face_embedding)
    emb, algo, ver = deserialize_embedding(student.face_embedding)
    assert emb.shape[0] == 128
    assert student.face_enrolled_at is not None
    assert student.face_embedding_version == 1
    assert result.student_id == 1
    assert result.face_embedding_version == 1
    assert result.face_enrolled_at == student.face_enrolled_at

    audit = session.added[-1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.UPDATE
    assert audit.entity_type == AuditEntity.FACE_ENROLLMENT
    assert audit.entity_id == student.id
    assert audit.performed_by == 7
    assert audit.old_value == {
        "enrolled": False,
        "face_enrolled_at": None,
        "face_embedding_version": 0,
    }
    assert audit.new_value["enrolled"] is True
    assert audit.new_value["face_embedding_version"] == 1


def test_enroll_unknown_student_404() -> None:
    session = _FakeSession()

    with pytest.raises(StudentNotFoundException):
        _run(_service(session).enroll_face(student_id=9, **_enroll_kwargs()))


def test_enroll_rejects_empty_photo() -> None:
    session = _FakeSession(objs=(_student(),))

    with pytest.raises(InvalidImageException) as exc_info:
        _run(_service(session).enroll_face(student_id=1, **_enroll_kwargs(front=b"")))

    assert exc_info.value.code == "invalid_image"
    assert exc_info.value.status_code == 400


def test_enroll_ignores_non_image_content_type() -> None:
    session = _FakeSession(objs=(_student(),))

    result = _run(
        _service(session).enroll_face(
            student_id=1,
            **_enroll_kwargs(front_content_type="text/csv"),
        )
    )

    assert result.student_id == 1


def test_enroll_rejects_oversized_photo() -> None:
    session = _FakeSession(objs=(_student(),))

    with pytest.raises(InvalidImageException):
        _run(
            _service(session).enroll_face(
                student_id=1, **_enroll_kwargs(front=b"x" * 2048)
            )
        )


# -- revoke -----------------------------------------------------------------


def test_revoke_clears_blob_and_bumps_version() -> None:
    session = _FakeSession(
        objs=(
            _student(
                face_embedding=b"blob",
                face_enrolled_at=NOW,
                face_embedding_version=2,
            ),
        )
    )

    _run(_service(session).revoke_face_enrollment(student_id=1, actor_id=7))

    student = session.store[(Student, 1)]
    assert student.face_embedding is None
    assert student.face_enrolled_at is None
    assert student.face_embedding_version == 3

    audit = session.added[-1]
    assert isinstance(audit, AuditLog)
    assert audit.action == AuditAction.REVOKE
    assert audit.entity_type == AuditEntity.FACE_ENROLLMENT
    assert audit.old_value["enrolled"] is True
    assert audit.new_value["enrolled"] is False


def test_revoke_unknown_student_404() -> None:
    session = _FakeSession()

    with pytest.raises(StudentNotFoundException):
        _run(_service(session).revoke_face_enrollment(student_id=9))


# -- router contract --------------------------------------------------------


def test_router_prefix_and_routes() -> None:
    assert face_router.router.prefix == "/admin/face-enrollment"

    by_path = {(r.path, next(iter(r.methods))): r for r in face_router.router.routes}
    get_route = by_path.get(("/admin/face-enrollment/{student_id}", "GET"))
    post_route = by_path.get(("/admin/face-enrollment/{student_id}", "POST"))
    delete_route = by_path.get(("/admin/face-enrollment/{student_id}", "DELETE"))

    assert get_route is not None
    assert post_route is not None
    assert delete_route is not None
    assert post_route.methods == {"POST"}
    assert 201 in (post_route.status_code, getattr(post_route, "status_code", None))
    assert 204 in (delete_route.status_code, getattr(delete_route, "status_code", None))

    paths = [r.path for r in face_router.router.routes]
    assert not any(p.endswith("/status") for p in paths)
