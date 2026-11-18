from __future__ import annotations

from fastapi import APIRouter

from shared.storage import get_presigned_upload_url

from api.deps import CurrentUserDep
from features.upload.schema import PresignedUrlRequest, PresignedUrlResponse

# Attachment upload routes. Prefix baked in here; mounted with no prefix=
# argument in api/router.py (the mount lives there - do NOT add an
# include_router call here).
#
# Deliberately its own mount point rather than a path under /student or
# /professor: excuse evidence is uploaded by students and professors alike,
# and the export reports built later share the same storage backend.
router = APIRouter(prefix="/upload")


@router.post(
    "/presigned-url",
    response_model=PresignedUrlResponse,
    summary="Mint a presigned upload URL for one attachment",
)
async def create_presigned_upload_url(
    payload: PresignedUrlRequest,
    _: CurrentUserDep,
) -> PresignedUrlResponse:
    # Any authenticated account may mint a URL: this writes nothing and the
    # storage layer rejects anything over the size cap or off the allowed
    # type list. The client PUTs the bytes itself, then submits the excuse
    # carrying the returned object_url.
    return PresignedUrlResponse(
        **get_presigned_upload_url(
            filename=payload.filename,
            size_bytes=payload.size_bytes,
            content_type=payload.content_type,
        )
    )
