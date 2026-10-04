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


class BackupNotFoundException(SystemDomainException):
    """404 - no backup row with this id, or its stored file is gone."""

    status_code: int = 404
    code: str = "backup_not_found"

    def __init__(self, backup_id: int) -> None:
        super().__init__(message=f"Backup {backup_id} not found")


class MaintenanceBusyException(SystemDomainException):
    """409 - a maintenance run was requested while another exclusive job holds
    the floor (a second maintenance run, a backup, or a scheduled batch)."""

    status_code: int = 409
    code: str = "maintenance_in_progress"

    def __init__(self) -> None:
        super().__init__(message="A maintenance task is already running")


class AuditFilterInvalidException(SystemDomainException):
    """422 - an audit filter names a value outside the recorded vocabulary.

    Rejected rather than passed through: the columns are free-form strings, so
    an unrecognised `entity_type` or `action` would otherwise come back as an
    empty page and read as "nothing happened", which is the opposite of what an
    administrator filtering the trail needs to be able to trust.
    """

    status_code: int = 422
    code: str = "invalid_audit_filter"

    def __init__(self, field: str, value: str) -> None:
        super().__init__(
            message=f"Unknown {field} '{value}'", field=field
        )


class AuditDateRangeInvalidException(SystemDomainException):
    """422 - `date_from` is later than `date_to`."""

    status_code: int = 422
    code: str = "invalid_audit_date_range"

    def __init__(self) -> None:
        super().__init__(
            message="date_from must not be later than date_to",
            field="date_from",
        )
