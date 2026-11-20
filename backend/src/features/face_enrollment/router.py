from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from api.deps import AdminUser, FaceEnrollmentServiceDep
from features.face_enrollment.schema import FaceEnrollmentResponse, FaceEnrollmentStatus

# This module owns /admin/face-enrollment ONLY.
#
# Prefix baked in here; mounted with no prefix= argument in api/router.py
# (the mount lives there - do NOT add an include_router call here).
# The slice stores no rows of its own: enrollment state is derived from
# students.face_embedding (NULL means not enrolled).
router = APIRouter(prefix="/admin/face-enrollment")


@router.get(
    "/{student_id}",
    response_model=FaceEnrollmentStatus,
    summary="Check face enrollment status",
)
async def get_face_enrollment_status(
    student_id: int,
    _: AdminUser,
    service: FaceEnrollmentServiceDep,
) -> FaceEnrollmentStatus:
    return await service.get_face_enrollment_status(student_id=student_id)


@router.post(
    "/{student_id}",
    response_model=FaceEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll face from 3 photos (front, left, right)",
)
async def enroll_face(
    student_id: int,
    front: Annotated[UploadFile, File(description="Front-facing photo")],
    left: Annotated[UploadFile, File(description="Left-profile photo")],
    right: Annotated[UploadFile, File(description="Right-profile photo")],
    user: AdminUser,
    service: FaceEnrollmentServiceDep,
) -> FaceEnrollmentResponse:
    front_bytes: bytes = await front.read()
    left_bytes: bytes = await left.read()
    right_bytes: bytes = await right.read()

    return await service.enroll_face(
        student_id=student_id,
        front=front_bytes,
        left=left_bytes,
        right=right_bytes,
        front_content_type=front.content_type,
        left_content_type=left.content_type,
        right_content_type=right.content_type,
        actor_id=user.id,
    )


@router.delete(
    "/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke face enrollment",
)
async def revoke_face_enrollment(
    student_id: int,
    user: AdminUser,
    service: FaceEnrollmentServiceDep,
) -> None:
    await service.revoke_face_enrollment(student_id=student_id, actor_id=user.id)
