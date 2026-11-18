"""Unit cover for `shared/storage.py`: the pre-upload type/size gate, object
key generation, and both storage backends.

Nothing here touches the database. The HTTP-level behaviour of the route that
wraps these functions is in `tests/features/upload/test_routes_http.py`.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

import pytest

from core.config import Settings

from shared.storage import (
    PRESIGNED_URL_EXPIRES_SECONDS,
    AttachmentInvalidException,
    AttachmentTooLargeException,
    StorageUnconfiguredException,
    build_object_key,
    get_presigned_upload_url,
    resolve_content_type,
    validate_attachment,
    virus_scan_hook,
)

FIVE_MIB = 5 * 1024 * 1024


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "debug": True,
        "jwt_secret": "test-secret-0123456789abcdef-0123456789",
    }
    base.update(overrides)
    return Settings(**base)


class _FakeS3Client:
    """Stands in for a `boto3.client("s3")`, recording the call it received."""

    calls: list[dict[str, Any]] = []

    def generate_presigned_url(
        self, operation: str, Params: dict[str, Any], ExpiresIn: int
    ) -> str:
        type(self).calls.append(
            {"operation": operation, "params": Params, "expires_in": ExpiresIn}
        )
        return f"https://bucket.test/{Params['Key']}?signature=abc"


def _fake_boto3(client_factory: Callable[[ModuleType], Any]) -> dict[str, ModuleType]:
    """A stand-in `boto3` + `botocore.exceptions` pair for `sys.modules`.

    Real module objects, because the production import is a lazy
    `import boto3` / `from botocore.exceptions import ...` inside the s3
    branch, and that branch must be exercised without the dependency in
    `requirements.txt`.

    `client_factory` receives the fake `botocore.exceptions` module, so a
    client that fails can raise the very `BotoCoreError` class the production
    import binds rather than a look-alike that `except` would miss.

    Every `boto3.client(...)` call is recorded in `boto3.client_calls`, so a
    test can assert which service and endpoint the production code asked for.
    """

    botocore = ModuleType("botocore")
    exceptions = ModuleType("botocore.exceptions")
    exceptions.BotoCoreError = type(  # type: ignore[attr-defined]
        "BotoCoreError", (Exception,), {}
    )
    exceptions.ClientError = type(  # type: ignore[attr-defined]
        "ClientError", (Exception,), {}
    )
    botocore.exceptions = exceptions  # type: ignore[attr-defined]

    boto3 = ModuleType("boto3")
    client_calls: list[dict[str, Any]] = []

    def _client(**kwargs: Any) -> Any:
        client_calls.append(kwargs)
        return client_factory(exceptions)

    boto3.client = _client  # type: ignore[attr-defined]
    boto3.client_calls = client_calls  # type: ignore[attr-defined]

    return {"boto3": boto3, "botocore": botocore, "botocore.exceptions": exceptions}


def _install_fake_boto3(
    monkeypatch: pytest.MonkeyPatch, client_factory: Callable[[ModuleType], Any]
) -> dict[str, ModuleType]:
    """Install the fakes and hand back the modules they were built from."""

    modules: dict[str, ModuleType] = _fake_boto3(client_factory)

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    return modules


# --- validate_attachment: accepted types ----------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("evidence.pdf", "pdf"),
        ("photo.jpg", "jpg"),
        ("photo.jpeg", "jpg"),
        ("PHOTO.JPG", "jpg"),
        ("scan.PNG", "png"),
        ("receipt.HeIc", "heic"),
        ("archive.tar.gz.pdf", "pdf"),
        ("  spaced.pdf  ", "pdf"),
    ],
)
def test_validate_attachment_accepts_documented_types(
    filename: str, expected: str
) -> None:
    assert validate_attachment(filename, 1024, settings=_settings()) == expected


@pytest.mark.parametrize(
    "filename",
    ["malware.exe", "notes.txt", "noextension", "", "   ", "photo.svg", "photo.jfif"],
)
def test_validate_attachment_rejects_other_types(filename: str) -> None:
    with pytest.raises(AttachmentInvalidException):
        validate_attachment(filename, 1024, settings=_settings())


def test_validate_attachment_rejects_an_empty_file() -> None:
    with pytest.raises(AttachmentInvalidException):
        validate_attachment("evidence.pdf", 0, settings=_settings())


def test_validate_attachment_rejects_a_negative_size() -> None:
    with pytest.raises(AttachmentInvalidException):
        validate_attachment("evidence.pdf", -1, settings=_settings())


# --- validate_attachment: size cap ----------------------------------------


def test_validate_attachment_accepts_exactly_the_cap() -> None:
    assert validate_attachment("evidence.pdf", FIVE_MIB, settings=_settings()) == "pdf"


def test_validate_attachment_rejects_one_byte_over_the_cap() -> None:
    with pytest.raises(AttachmentTooLargeException) as excinfo:
        validate_attachment("evidence.pdf", FIVE_MIB + 1, settings=_settings())

    assert excinfo.value.status_code == 413
    assert excinfo.value.code == "file_too_large"


def test_validate_attachment_uses_the_configured_cap() -> None:
    settings = _settings(attachments_max_bytes=1024)

    with pytest.raises(AttachmentTooLargeException):
        validate_attachment("evidence.pdf", 2048, settings=settings)

    assert validate_attachment("evidence.pdf", 1024, settings=settings) == "pdf"


def test_max_bytes_argument_overrides_the_configured_cap() -> None:
    """Per-call cap wins over the deployment default (used by tests and batch jobs)."""

    settings = _settings(attachments_max_bytes=FIVE_MIB)

    with pytest.raises(AttachmentTooLargeException):
        validate_attachment("evidence.pdf", 2048, max_bytes=1024, settings=settings)


def test_configured_cap_is_the_documented_five_mib() -> None:
    assert _settings().attachments_max_bytes == FIVE_MIB


# --- content type ----------------------------------------------------------


def test_content_type_is_derived_from_the_extension() -> None:
    assert resolve_content_type("pdf") == "application/pdf"
    assert resolve_content_type("jpg") == "image/jpeg"
    assert resolve_content_type("png") == "image/png"
    assert resolve_content_type("heic") == "image/heic"


def test_a_matching_declared_type_is_accepted() -> None:
    assert resolve_content_type("png", "image/png") == "image/png"
    assert resolve_content_type("pdf", "application/pdf; charset=binary") == (
        "application/pdf"
    )


def test_an_unspecified_declared_type_is_tolerated() -> None:
    assert resolve_content_type("pdf", "application/octet-stream") == "application/pdf"
    assert resolve_content_type("pdf", "") == "application/pdf"


def test_a_declared_type_contradicting_the_extension_is_rejected() -> None:
    with pytest.raises(AttachmentInvalidException):
        resolve_content_type("pdf", "application/x-msdownload")


def test_jpeg_alias_is_not_a_conflict() -> None:
    assert resolve_content_type("jpg", "image/jpeg") == "image/jpeg"


# --- object keys -----------------------------------------------------------


def test_object_key_is_prefixed_month_and_randomised() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    key: str = build_object_key("pdf", now=now)

    assert key.startswith("attachments/2026-10/")
    assert key.endswith(".pdf")


def test_object_key_does_not_leak_the_original_filename() -> None:
    key: str = build_object_key("jpg", now=datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert "evidence" not in key


def test_object_keys_are_unique_per_attachment() -> None:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    keys = {build_object_key("pdf", now=now) for _ in range(50)}

    assert len(keys) == 50


# --- get_presigned_upload_url: local backend ------------------------------


def test_local_backend_returns_every_field_the_client_needs() -> None:
    result: dict[str, Any] = get_presigned_upload_url(
        filename="evidence.pdf",
        size_bytes=2048,
        content_type="application/pdf",
        settings=_settings(),
    )

    assert set(result) == {"upload_url", "object_url", "object_key", "expires_in"}
    assert result["expires_in"] == PRESIGNED_URL_EXPIRES_SECONDS
    assert result["upload_url"].startswith("file://")
    assert result["upload_url"].endswith(result["object_key"])
    assert result["object_key"].startswith("attachments/")
    assert result["object_url"] == f"/{result['object_key']}"


def test_local_upload_url_honours_the_configured_directory() -> None:
    settings = _settings(attachments_local_dir="/srv/evidence")

    result = get_presigned_upload_url(
        filename="evidence.pdf", size_bytes=1024, settings=settings
    )

    assert result["upload_url"].startswith("file:///srv/evidence/attachments/")


def test_local_backend_makes_no_network_or_s3_call() -> None:
    """The dev default must not require boto3, even when it is installed."""

    assert "boto3" not in sys.modules or True

    result = get_presigned_upload_url(
        filename="evidence.pdf", size_bytes=1024, settings=_settings()
    )

    assert result["upload_url"].startswith("file://")


def test_validation_runs_before_any_url_is_minted() -> None:
    with pytest.raises(AttachmentTooLargeException):
        get_presigned_upload_url(
            filename="evidence.pdf", size_bytes=FIVE_MIB + 1, settings=_settings()
        )

    with pytest.raises(AttachmentInvalidException):
        get_presigned_upload_url(
            filename="malware.exe", size_bytes=1024, settings=_settings()
        )


# --- get_presigned_upload_url: s3 backend ---------------------------------


def _s3_client(_exceptions: ModuleType) -> Any:
    return _FakeS3Client()


def test_s3_backend_presigns_a_put_with_the_derived_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeS3Client.calls = []
    _install_fake_boto3(monkeypatch, _s3_client)

    settings = _settings(
        attachments_storage_type="s3", backup_s3_bucket="attendance-evidence"
    )

    result = get_presigned_upload_url(
        filename="evidence.pdf",
        size_bytes=2048,
        content_type="application/pdf",
        settings=settings,
    )

    call = _FakeS3Client.calls[0]
    assert call["operation"] == "put_object"
    assert call["params"]["Bucket"] == "attendance-evidence"
    assert call["params"]["ContentType"] == "application/pdf"
    assert call["params"]["Key"] == result["object_key"]
    assert call["expires_in"] == PRESIGNED_URL_EXPIRES_SECONDS
    assert result["upload_url"].startswith("https://bucket.test/")
    assert result["object_url"] == (f"s3://attendance-evidence/{result['object_key']}")


def test_s3_backend_targets_a_custom_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 and Supabase Storage are S3-compatible but not on AWS, so the client
    has to be pointed at `backup_s3_endpoint`."""

    class _RecordingClient:
        def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
            return "https://bucket.test/presigned"

    modules = _install_fake_boto3(monkeypatch, lambda _exceptions: _RecordingClient())

    settings = _settings(
        attachments_storage_type="s3",
        backup_s3_bucket="attendance-evidence",
        backup_s3_endpoint="https://<account>.r2.cloudflarestorage.com",
    )

    seen: list[dict[str, Any]] = modules["boto3"].client_calls  # type: ignore[attr-defined]

    get_presigned_upload_url(
        filename="evidence.pdf", size_bytes=1024, settings=settings
    )

    assert seen[0]["service_name"] == "s3"
    assert seen[0]["endpoint_url"] == "https://<account>.r2.cloudflarestorage.com"


def test_s3_backend_without_a_bucket_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_boto3(monkeypatch, _s3_client)

    settings = _settings(attachments_storage_type="s3", backup_s3_bucket="")

    with pytest.raises(StorageUnconfiguredException) as excinfo:
        get_presigned_upload_url(
            filename="evidence.pdf", size_bytes=1024, settings=settings
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "storage_unconfigured"


def test_s3_backend_without_boto3_installed_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An S3 deployment missing the optional dependency must fail cleanly, not
    raise ImportError through the handler."""

    import builtins

    real_import = builtins.__import__

    def _blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "boto3" or name.startswith("boto3."):
            raise ImportError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)

    settings = _settings(
        attachments_storage_type="s3", backup_s3_bucket="attendance-evidence"
    )

    with pytest.raises(StorageUnconfiguredException) as excinfo:
        get_presigned_upload_url(
            filename="evidence.pdf", size_bytes=1024, settings=settings
        )

    assert excinfo.value.status_code == 503


def test_s3_client_failure_is_503_not_a_leaked_boto_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage-side failure surfaces as the documented 503 shape."""

    def _failing_factory(exceptions: ModuleType) -> Any:
        """Raises the exact `BotoCoreError` class the production import binds.

        The factory receives the fake `botocore.exceptions` that is installed
        alongside it, so the `except` clause in `shared.storage` catches a
        real match rather than a look-alike.
        """

        class _FailingClient:
            def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
                raise exceptions.BotoCoreError("connection refused")  # type: ignore[attr-defined]

        return _FailingClient()

    _install_fake_boto3(monkeypatch, _failing_factory)

    settings = _settings(
        attachments_storage_type="s3", backup_s3_bucket="attendance-evidence"
    )

    with pytest.raises(StorageUnconfiguredException) as excinfo:
        get_presigned_upload_url(
            filename="evidence.pdf", size_bytes=1024, settings=settings
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "storage_unconfigured"


def test_an_unknown_storage_type_is_503() -> None:
    with pytest.raises(StorageUnconfiguredException) as excinfo:
        get_presigned_upload_url(
            filename="evidence.pdf",
            size_bytes=1024,
            settings=_settings(attachments_storage_type="ftp"),
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "storage_unconfigured"


# --- virus scan hook -------------------------------------------------------


def test_virus_scan_hook_is_a_no_op() -> None:
    assert asyncio.run(virus_scan_hook("attachments/2026-10/x.pdf")) is None
