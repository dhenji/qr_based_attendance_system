from __future__ import annotations


class AppException(Exception):
    """Base class for all application exceptions.

    ``details`` carries optional machine-readable context alongside the
    human-readable ``message``. It is additive: ``to_dict`` includes it only
    when set, so every existing response shape is unchanged for exceptions
    that do not populate it. The attendance attempt-limit contract uses it to
    report ``attempt_limit`` / ``attempts_used`` / ``attempts_remaining`` /
    ``attempt_consumed`` (docs/architecture/api-contracts.md).
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"
    field: str | None = None
    details: dict | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        field: str | None = None,
        details: dict | None = None,
    ) -> None:
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

        self.field = field
        self.details = details

        super().__init__(self.message)

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}

        if self.field is not None:
            d["field"] = self.field

        if self.details is not None:
            d["details"] = self.details

        return d


class DomainException(AppException):
    """Business-logic violations (client errors, 4xx)."""

    status_code: int = 422


class DatabaseException(AppException):
    """Data-layer errors: unique violations, FK constraints, etc."""

    status_code: int = 409
    code: str = "database_error"


class ForbiddenException(AppException):
    """403 - the actor is not permitted to perform this operation."""

    status_code: int = 403
    code: str = "insufficient_permissions"

    def __init__(self, message: str = "You do not have permissions to access this resource") -> None:
        super().__init__(message=message)
