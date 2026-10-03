from __future__ import annotations

from core.exceptions import AppException, DomainException


class SystemException(AppException):
    """Root umbrella for all system errors."""


class SystemDomainException(SystemException, DomainException):
    pass


class BackupStorageUnconfiguredException(SystemException):
    """503 - backup backend selected but unusable (no key, no bucket, no binary)."""

    status_code: int = 503
    code: str = "storage_unconfigured"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class BackupFailedException(SystemException):
    """500 - a dump/compress/encrypt/upload step failed; the row is marked failed."""

    status_code: int = 500
    code: str = "backup_failed"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class BackupInProgressException(SystemDomainException):
    """409 - a backup already holds the in-process lock."""

    status_code: int = 409
    code: str = "backup_in_progress"

    def __init__(self) -> None:
        super().__init__(message="A backup is already running")
