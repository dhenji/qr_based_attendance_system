from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FaceEnrollmentStatus(BaseModel):
    enrolled: bool
    face_enrolled_at: datetime | None = None
    face_embedding_version: int | None = None


class FaceEnrollmentResponse(BaseModel):
    student_id: int
    face_enrolled_at: datetime
    face_embedding_version: int
