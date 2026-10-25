from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from features.face_enrollment.exceptions import (
    InvalidImageException,
    MultipleFacesException,
    NoFaceDetectedException,
    QualityTooLowException,
)
from features.face_enrollment.schema import FaceEnrollmentResponse, FaceEnrollmentStatus
from shared.face_quality import assess_image_bytes
from features.student.exceptions import StudentNotFoundException
from features.student.model import Student
from shared.audit import record_audit
from shared.cache import invalidate_face_embedding
from shared.enums import AuditAction, AuditEntity
from shared.face_embedding_generator import FaceEmbeddingGenerationError, generate_embedding_from_images
from shared.face_embeddings import is_stub_embedding


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

    # Content type is client-provided metadata and is not trusted. The actual
    # image format is verified by decoding the bytes in assess_image_bytes below;
    # a missing/mismatched content type is only rejected when decoding fails.


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
        actor_id: int | None = None,
    ) -> FaceEnrollmentResponse:
        """Store a new face enrollment, superseding any previous one."""
        student: Student | None = await self._session.get(Student, student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        for name, content, content_type in (
            ("front", front, front_content_type),
            ("left", left, left_content_type),
            ("right", right, right_content_type),
        ):
            _validate_photo(
                name=name,
                content=content,
                content_type=content_type,
                max_bytes=self._settings.attachments_max_bytes,
            )

            result = assess_image_bytes(content)
            if not result.ok:
                detail = f"{name}: {result.message or result.code}"
                code = result.code
                if code == "invalid_image":
                    raise InvalidImageException(detail)
                if code == "no_face_detected":
                    raise NoFaceDetectedException(detail)
                if code == "multiple_faces":
                    raise MultipleFacesException(detail)
                raise QualityTooLowException(detail)

        old_value: dict[str, Any] = self._face_snapshot(student)
        try:
            embedding_blob, algorithm = generate_embedding_from_images(
                front,
                left,
                right,
                algorithm=getattr(self._settings, "face_embedding_algorithm", "mediapipe-v1"),
            )
        except FaceEmbeddingGenerationError as e:
            from features.face_enrollment.exceptions import NoFaceDetectedException

            raise NoFaceDetectedException(str(e)) from e

        student.face_embedding = embedding_blob
        student.face_embedding_algorithm = algorithm
        student.face_enrolled_at = datetime.now(timezone.utc)
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._session.flush()

        invalidate_face_embedding(student.id)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.FACE_ENROLLMENT,
            entity_id=student.id,
            old_value=old_value,
            new_value=self._face_snapshot(student),
        )

        assert student.face_enrolled_at is not None

        return FaceEnrollmentResponse(
            student_id=student.id,
            face_enrolled_at=student.face_enrolled_at,
            face_embedding_version=student.face_embedding_version or 0,
        )

    async def revoke_face_enrollment(
        self, *, student_id: int, actor_id: int | None = None
    ) -> None:
        """Clear face data without deactivating the student record.

        The version is bumped rather than reset so devices holding a cached copy
        cannot keep matching against a stale embedding.
        """

        student: Student | None = await self._session.get(Student, student_id)

        if student is None:
            raise StudentNotFoundException(student_id)

        old_value: dict[str, Any] = self._face_snapshot(student)
        student.face_embedding = None
        student.face_embedding_algorithm = None
        student.face_enrolled_at = None
        student.face_embedding_version = (student.face_embedding_version or 0) + 1
        await self._session.flush()

        invalidate_face_embedding(student.id)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.REVOKE,
            entity_type=AuditEntity.FACE_ENROLLMENT,
            entity_id=student.id,
            old_value=old_value,
            new_value=self._face_snapshot(student),
        )

    @staticmethod
    def _face_snapshot(student: Student) -> dict[str, Any]:
        """Face state without the embedding.

        The blob is deliberately never copied into an audit row; the
        `face_embedding_version` bump is the signal that it changed. Once the
        real pipeline lands (D28) the blob will also be encrypted at rest — today
        it is the zero-filled `_stub_embedding_blob` placeholder, so the exclusion
        is carrying the weight on its own. See security-model.md
        *Client-Asserted Biometrics*.
        """
        return {
            "enrolled": student.face_embedding is not None,
            "face_enrolled_at": (
                student.face_enrolled_at.isoformat()
                if student.face_enrolled_at
                else None
            ),
            "face_embedding_version": student.face_embedding_version or 0,
        }
