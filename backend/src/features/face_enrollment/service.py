from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from features.face_enrollment.exceptions import InvalidImageException
from features.face_enrollment.schema import FaceEnrollmentResponse, FaceEnrollmentStatus
from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from shared.cache import invalidate_face_embedding

_EMBEDDING_DIM: int = 128


def _stub_embedding_blob(*, version: int) -> bytes:
    """Build the placeholder embedding blob stored until real generation lands.

    Shape mirrors the documented storage format (mean + per-angle vectors)
    so swapping in the real pipeline only changes this builder.
    """

    angles: dict[str, list[float]] = {
        angle: [0.0] * _EMBEDDING_DIM for angle in ("front", "left", "right")
    }
    payload: dict[str, object] = {
        "mean": [0.0] * _EMBEDDING_DIM,
        "angles": angles,
        "stub": True,
        "version": version,
    }

    return json.dumps(payload).encode("utf-8")


def _validate_photo(
    *,
    name: str,
    content: bytes,
    content_type: str | None,
    max_bytes: int,
) -> None:
    if not content:
        raise InvalidImageException(f"{name} photo is empty")

    if len(content) > max_bytes:
        raise InvalidImageException(
            f"{name} photo exceeds {max_bytes} bytes ({len(content)} received)"
        )

    if content_type is None or not content_type.startswith("image/"):
        raise InvalidImageException(
            f"{name} photo must be an image upload "
            f"(received content type {content_type!r})"
        )


class FaceEnrollmentService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def get_face_enrollment_status(
        self, *, student_id: int
    ) -> FaceEnrollmentStatus:
        """Return whether the student currently has face data stored.

        An archived identity has its blob cleared, so a NULL blob always reads
        as "not enrolled" rather than relying on a separate flag.
        """

        student: Student | None = await self._session.get(Student, student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        if student.face_embedding is None:
            return FaceEnrollmentStatus(enrolled=False)

        return FaceEnrollmentStatus(
            enrolled=True,
            face_enrolled_at=student.face_enrolled_at,
            face_embedding_version=student.face_embedding_version or 0,
        )

    async def enroll_face(
        self,
        *,
        student_id: int,
        front: bytes,
        left: bytes,
        right: bytes,
        front_content_type: str | None = None,
        left_content_type: str | None = None,
        right_content_type: str | None = None,
    ) -> FaceEnrollmentResponse:
        """Store a new face enrollment, superseding any previous one."""

        student: Student | None = await self._session.get(Student, student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        _validate_photo(
            name="front",
            content=front,
            content_type=front_content_type,
            max_bytes=self._settings.attachments_max_bytes,
        )
        _validate_photo(
            name="left",
            content=left,
            content_type=left_content_type,
            max_bytes=self._settings.attachments_max_bytes,
        )
        _validate_photo(
            name="right",
            content=right,
            content_type=right_content_type,
            max_bytes=self._settings.attachments_max_bytes,
        )

        student.face_embedding = _stub_embedding_blob(
            version=self._settings.face_embedding_version
        )
        student.face_enrolled_at = datetime.now(timezone.utc)
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._session.flush()

        invalidate_face_embedding(student.id)

        assert student.face_enrolled_at is not None

        return FaceEnrollmentResponse(
            student_id=student.id,
            face_enrolled_at=student.face_enrolled_at,
            face_embedding_version=student.face_embedding_version or 0,
        )

    async def revoke_face_enrollment(self, *, student_id: int) -> None:
        """Clear face data without deactivating the student record.

        The version is bumped rather than reset so devices holding a cached copy
        cannot keep matching against a stale embedding.
        """

        student: Student | None = await self._session.get(Student, student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        student.face_embedding = None
        student.face_enrolled_at = None
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._session.flush()

        invalidate_face_embedding(student.id)
