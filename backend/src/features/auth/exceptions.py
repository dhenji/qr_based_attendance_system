from core.exceptions import AppException, DatabaseException, DomainException


class AuthException(AppException):
    """Root umbrella for all auth errors."""


class AuthDomainException(AuthException, DomainException):
    pass


class RoleMismatchException(AuthDomainException):
    """403 - user lacks the required role."""

    status_code: int = 403
    code: str = "role_mismatch"

    def __init__(self, required: str, actual: str) -> None:
        super().__init__(
            message=f"Requires {required} role, but user has {actual} role"
        )


class PasswordPolicyException(AuthDomainException):
    """422 - password violates policy."""

    code: str = "password_policy_violation"

    def __init__(self, field: str = "password") -> None:
        super().__init__(
            message="Password does not meet the required policy", field=field
        )


class CurrentPasswordInvalid(AuthDomainException):
    """400 = current password is incorrect."""

    status_code: int = 400
    code: str = "current_password_invalid"

    def __init__(self) -> None:
        super().__init__(message="Current password is incorrect")
