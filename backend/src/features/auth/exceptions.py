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


class InvalidCredentialsException(AuthDomainException):
    """400 - email or password does not match."""

    status_code: int = 400
    code: str = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__(message="Email or password is incorrect")


class AccountLockedException(AuthDomainException):
    """423 - account locked after too many failed attempts."""

    status_code: int = 423
    code: str = "account_locked"

    def __init__(self, retry_after_minutes: int) -> None:
        super().__init__(
            message=(
                "Account is temporarily locked due to too many failed "
                f"attempts. Try again in {retry_after_minutes} minutes"
            )
        )


class OtpInvalidException(AuthDomainException):
    """400 - OTP code does not match."""

    status_code: int = 400
    code: str = "otp_invalid"

    def __init__(self, field: str = "otp_code") -> None:
        super().__init__(message="Invalid OTP code", field=field)


class OtpExpiredException(AuthDomainException):
    """400 - OTP code has expired or already consumed."""

    status_code: int = 400
    code: str = "otp_expired"

    def __init__(self) -> None:
        super().__init__(message="OTP code has expired or was already used")


class UnrecognizedEmailException(AuthDomainException):
    """404 - email is not in the roster (claim register)."""

    status_code: int = 404
    code: str = "unrecognized_email"

    def __init__(self) -> None:
        super().__init__(message="Email is not recognized in the roster")


class AmbiguousAccountException(AuthDomainException):
    """409 - email exists on both a student and professor roster."""

    status_code: int = 409
    code: str = "ambiguous_account"

    def __init__(self) -> None:
        super().__init__(
            message="This email matches more than one record; contact the administrator"
        )


class UserAlreadyClaimedException(AuthDomainException):
    """409 - email already has an active account."""

    status_code: int = 409
    code: str = "user_exists"

    def __init__(self) -> None:
        super().__init__(message="An account already exists for this email")


class MfaVerifyException(AuthDomainException):
    """400 - TOTP/backup code did not verify."""

    status_code: int = 400
    code: str = "invalid_mfa_code"

    def __init__(self) -> None:
        super().__init__(message="Invalid MFA code")


class MfaAlreadyEnabledException(AuthDomainException):
    """409 - MFA cannot be set up twice."""

    status_code: int = 409
    code: str = "mfa_already_enabled"

    def __init__(self) -> None:
        super().__init__(message="MFA is already enabled")


class SecurityAnswerInvalidException(AuthDomainException):
    """400 - security-question answer does not match."""

    status_code: int = 400
    code: str = "security_answer_invalid"

    def __init__(self) -> None:
        super().__init__(message="Security answer is incorrect")


class RecoveryLockedException(AuthDomainException):
    """423 - recovery aborted after too many failed answer attempts."""

    status_code: int = 423
    code: str = "recovery_locked"

    def __init__(self, retry_after_minutes: int) -> None:
        super().__init__(
            message=(
                "Recovery is temporarily locked due to too many failed "
                f"attempts. Try again in {retry_after_minutes} minutes"
            )
        )
