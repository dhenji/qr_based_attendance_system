"""Attachment storage: presigned upload URLs and the pre-upload type/size gate.

Attachments (excuse evidence) are uploaded straight to storage so the file
bytes never pass through the API. The flow is:

1. client asks for a presigned URL for one file,
2. client PUTs the bytes to that URL,
3. client submits the excuse carrying `object_url`, which is what
   `excuse_requests.attachment_urls` records - a URL reference, never bytes.

Two backends, chosen by `attachments_storage_type`:

- `local` (dev default): no network and no dependency. The returned upload URL
  is a `file://` path the client can write to; nothing is mounted to receive
  the PUT, so this branch exists to keep the flow exercisable in development
  rather than to be a working upload endpoint.
- `s3`: S3-compatible object storage (S3 / R2 / Supabase Storage). `boto3` is
  imported lazily inside this branch only, so a deployment that never leaves
  `local` does not pay for it. Bucket and credentials are the backup ones -
  the two features are specified to share a backend.

Upload URLs are short-lived and the object key is randomised, so a key is not
a capability and an expired URL cannot be replayed against a predictable path.

Attachments are immutable once uploaded (excuse-workflow.md §7): they are kept
for the audit trail even when the excuse is rejected, so this module
deliberately exposes no delete.
"""

from __future__ import annotations

from datetime import datetime, timezone
from logging import Logger, getLogger
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config import Settings, get_settings
from core.exceptions import AppException
from features.excuse.constants import ALLOWED_ATTACHMENT_EXTENSIONS

logger: Logger = getLogger(__name__)

PRESIGNED_URL_EXPIRES_SECONDS: int = 900

# Attachments share the bucket with backups but stay in their own prefix, so
# backup retention pruning never touches student evidence.
OBJECT_KEY_PREFIX: str = "attachments/"

# Extension -> content type. The extension is the authority: the content type
# handed to storage is derived here, never taken from the client.
ATTACHMENT_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
}

# Declared types that carry no information and so do not conflict with the
# extension-derived type.
_UNSPECIFIED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"", "application/octet-stream", "binary/octet-stream"}
)


class AttachmentInvalidException(AppException):
    """400 - the file cannot be accepted as an attachment at all."""

    status_code: int = 400
    code: str = "invalid_attachment"

    def __init__(self, message: str, *, field: str = "filename") -> None:
        super().__init__(message=message, field=field)


class AttachmentTooLargeException(AppException):
    """413 - the file is larger than the configured attachment cap."""

    status_code: int = 413
    code: str = "file_too_large"

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            message=(
                f"Attachment is {size_bytes} bytes, which exceeds the "
                f"{max_bytes} byte limit"
            ),
            field="size_bytes",
        )


class StorageUnconfiguredException(AppException):
    """503 - the storage backend is selected but not usable as configured."""

    status_code: int = 503
    code: str = "storage_unconfigured"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


def validate_attachment(
    filename: str,
    size_bytes: int,
    *,
    max_bytes: int | None = None,
    settings: Settings | None = None,
) -> str:
    """Check one attachment and return its normalised extension.

    Accepts only the types in `ALLOWED_ATTACHMENT_EXTENSIONS` (PDF, JPG, PNG,
    HEIC) and rejects anything over `max_bytes`. The extension is matched
    case-insensitively; `jpeg` normalises to `jpg` so one type maps to one
    content type and one object key suffix.

    `max_bytes` defaults to `attachments_max_bytes` from the environment, so
    the cap is deployable without a code change.
    """

    current_settings: Settings = settings or get_settings()
    limit: int = (
        max_bytes if max_bytes is not None else current_settings.attachments_max_bytes
    )

    extension: str = _extract_extension(filename)

    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise AttachmentInvalidException(
            "Attachment must be one of PDF, JPG, PNG or HEIC"
        )

    if size_bytes <= 0:
        raise AttachmentInvalidException("Attachment is empty")

    if size_bytes > limit:
        raise AttachmentTooLargeException(size_bytes, limit)

    return "jpg" if extension == "jpeg" else extension


def build_object_key(extension: str, *, now: datetime | None = None) -> str:
    """Build a non-enumerable object key for one attachment.

    `<prefix><yyyy-mm>/<uuid4>.<ext>`. The original filename is deliberately
    dropped: it is caller-controlled, frequently carries identifying details,
    and a random name removes any guessable path for an unauthenticated PUT.

    The key is storage-agnostic - `local` and `s3` share the layout, so the
    same object is reachable under either backend.
    """

    stamp: datetime = now or datetime.now(timezone.utc)

    return f"{OBJECT_KEY_PREFIX}{stamp:%Y-%m}/{uuid4()}.{extension}"


def resolve_content_type(extension: str, declared: str | None = None) -> str:
    """Return the content type to sign the upload with.

    Derived from the validated extension. A `declared` type is only used to
    reject a body that contradicts the extension (`evidence.pdf` announced as
    `application/x-msdownload`); it never becomes the signed value.
    """

    derived: str = ATTACHMENT_CONTENT_TYPES[extension]

    if declared is None:
        return derived

    normalized: str = declared.split(";")[0].strip().lower()

    if normalized in _UNSPECIFIED_CONTENT_TYPES or normalized == derived:
        return derived

    raise AttachmentInvalidException(
        f"Declared content type {normalized} does not match a .{extension} attachment",
        field="content_type",
    )


def get_presigned_upload_url(
    *,
    filename: str,
    size_bytes: int,
    content_type: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Mint a presigned upload URL for one attachment.

    Validates the file first, so an oversized or disallowed attachment is
    rejected before any storage call. Returns the keys the client needs:
    `upload_url` (where to PUT), `object_url` (what to record on the excuse),
    `object_key`, and `expires_in`.
    """

    current_settings: Settings = settings or get_settings()
    extension: str = validate_attachment(
        filename, size_bytes, settings=current_settings
    )
    signed_content_type: str = resolve_content_type(extension, content_type)
    storage_type: str = current_settings.attachments_storage_type

    if storage_type not in ("local", "s3"):
        raise StorageUnconfiguredException(
            f"attachments_storage_type={storage_type!r} is not a supported "
            "storage backend"
        )

    # Both backends key objects the same way, so the key is built once here
    # rather than per arm.
    object_key: str = build_object_key(extension)
    upload_url: str
    object_url: str

    match storage_type:
        case "s3":
            upload_url = _s3_presigned_url(
                current_settings, object_key, signed_content_type
            )
            object_url = f"s3://{current_settings.backup_s3_bucket}/{object_key}"
        case _:
            upload_url = _local_upload_url(current_settings, object_key)
            object_url = f"/{object_key}"

    return {
        "upload_url": upload_url,
        "object_url": object_url,
        "object_key": object_key,
        "expires_in": PRESIGNED_URL_EXPIRES_SECONDS,
    }


def _extract_extension(filename: str) -> str:
    # Trimmed first: a browser can hand over "  spaced.pdf  ", and `Path`
    # would otherwise read the trailing spaces as part of the suffix.
    return Path(filename.strip()).suffix.lstrip(".").lower()


def _local_upload_url(settings: Settings, object_key: str) -> str:
    target: Path = (Path(settings.attachments_local_dir) / object_key).resolve()

    return target.as_uri()


def _s3_presigned_url(settings: Settings, object_key: str, content_type: str) -> str:
    if not settings.backup_s3_bucket:
        raise StorageUnconfiguredException(
            "ATTACHMENTS_STORAGE_TYPE=s3 requires BACKUP_S3_BUCKET to be set"
        )

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        raise StorageUnconfiguredException(
            "ATTACHMENTS_STORAGE_TYPE=s3 requires the boto3 package, which is "
            "not installed in this environment"
        )

    client_kwargs: dict[str, Any] = {"service_name": "s3"}

    if settings.backup_s3_endpoint:
        client_kwargs["endpoint_url"] = settings.backup_s3_endpoint

    try:
        client = boto3.client(**client_kwargs)
        return str(
            client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.backup_s3_bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=PRESIGNED_URL_EXPIRES_SECONDS,
            )
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Presigned URL generation failed: %s", exc)
        raise StorageUnconfiguredException(
            "Could not generate a presigned upload URL for the configured storage"
        )


async def virus_scan_hook(object_key: str) -> None:
    """Post-upload malware scan point (excuse-workflow.md §7).

    A deployment that runs a scanner replaces the body with the call and, when
    the file is flagged, keeps the URL for audit while holding the excuse for
    review. Deployments without a scanner skip it and rely on manual review, so
    the default is a no-op that never raises into the upload path.
    """

    logger.debug("No virus scanner configured; skipping scan for %s", object_key)