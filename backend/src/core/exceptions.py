from __future__ import annotations


class AppException(Exception):
    """Base class for all application exceptions."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"
    field: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        field: str | None = None,
    ) -> None:
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

        self.field = field

        super().__init__(self.message)

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}

        if self.field is not None:
            d["field"] = self.field

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
