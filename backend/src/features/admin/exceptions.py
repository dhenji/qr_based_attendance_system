from core.exceptions import AppException, DomainException


class AdminException(AppException):
    """Root umbrella for all admin-module errors."""


class AdminDomainException(AdminException, DomainException):
    pass


class AdminUserNotFound(AdminDomainException):
    """404 - the target user does not exist."""

    status_code: int = 404
    code: str = "admin_user_not_found"

    def __init__(self) -> None:
        super().__init__(message="User not found")


class SelfDeactivationForbidden(AdminDomainException):
    """409 - a super_admin cannot deactivate their own account."""

    status_code: int = 409
    code: str = "self_deactivation_forbidden"

    def __init__(self) -> None:
        super().__init__(message="You cannot deactivate your own account")


class EmailAlreadyExists(AdminDomainException):
    """409 - email already taken by another account."""

    status_code: int = 409
    code: str = "admin_user_email_exists"

    def __init__(self) -> None:
        super().__init__(message="A user with this email already exists")


class UsernameAlreadyExists(AdminDomainException):
    """409 - username already taken by another account."""

    status_code: int = 409
    code: str = "admin_user_username_exists"

    def __init__(self) -> None:
        super().__init__(message="This username is already taken")
