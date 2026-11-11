from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from pydantic.fields import Field

from features.auth.constants import (
    BACKUP_CODE_MAX_INPUT_LENGTH,
    OTP_CODE_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SECURITY_ANSWER_MAX_LENGTH,
    SECURITY_ANSWER_MIN_LENGTH,
    SECURITY_QUESTION_MAX_LENGTH,
    SECURITY_QUESTION_MIN_LENGTH,
)
from shared.enums import OtpPurpose, UserRole
from shared.validators import password_strength


class OTPRequest(BaseModel):
    email: EmailStr
    purpose: OtpPurpose = OtpPurpose.CLAIM
    # Required only when purpose=forget_password: proves step 2 of the recovery
    # flow was passed, so the mandatory security-question gate cannot be skipped.
    recovery_token: str | None = None


class _CodeRequest(BaseModel):
    code: str = Field(
        min_length=OTP_CODE_LENGTH, max_length=BACKUP_CODE_MAX_INPUT_LENGTH
    )


class _OTPCodeRequest(BaseModel):
    otp_code: str = Field(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)


class OTPVerifyRequest(OTPRequest, _CodeRequest):
    pass


class RegisterRequest(OTPRequest, _OTPCodeRequest):
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    security_question: str = Field(
        min_length=SECURITY_QUESTION_MIN_LENGTH, max_length=SECURITY_QUESTION_MAX_LENGTH
    )
    security_answer: str = Field(
        min_length=SECURITY_ANSWER_MIN_LENGTH, max_length=SECURITY_ANSWER_MAX_LENGTH
    )

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_pending: bool = False
    preauth_token: str | None = None  # grant no access; exchanged via /auth/mfa/verify
    otp_pending: bool = False
    otp_token: str | None = None  # grant no access; exchanged via /auth/login/verify
    must_change_password: bool = False


class LoginOtpVerifyRequest(BaseModel):
    """Exchange the login-OTP grant plus the emailed 6-digit code for tokens
    (or an MFA challenge for admins with MFA enabled)."""

    otp_token: str
    code: str = Field(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)


class LoginOtpResendRequest(BaseModel):
    """Mint a fresh LOGIN OTP; the grant proves the password gate was passed."""

    otp_token: str


class SetSecurityQuestionRequest(BaseModel):
    question: str = Field(
        min_length=SECURITY_QUESTION_MIN_LENGTH, max_length=SECURITY_QUESTION_MAX_LENGTH
    )

    answer: str = Field(
        min_length=SECURITY_ANSWER_MIN_LENGTH, max_length=SECURITY_ANSWER_MAX_LENGTH
    )


class SecurityQuestionResponse(BaseModel):
    question: str | None = None
    set: bool = False


class RecoveryGrantResponse(BaseModel):
    """Returned by forgot-password step 2; unlocks the FORGET_PASSWORD OTP."""

    recovery_token: str


class PasswordRecoveryStartResponse(BaseModel):
    """Returned when an authenticated user starts password recovery.

    The recovery token gates OTP minting on the same path as the public
    forgot-password flow; the masked email is for display only.
    """

    recovery_token: str
    masked_email: str


class ForgotPasswordStep1Request(OTPRequest):
    turnstile_token: str | None = None


class ForgotPasswordStep2Request(BaseModel):
    email: EmailStr
    answer: str = Field(
        min_length=SECURITY_ANSWER_MIN_LENGTH, max_length=SECURITY_ANSWER_MAX_LENGTH
    )


class _NewPasswordRequest(BaseModel):
    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return password_strength(value)


class ResetPasswordRequest(OTPRequest, _OTPCodeRequest, _NewPasswordRequest):
    pass


class PasswordRecoveryResetRequest(_OTPCodeRequest, _NewPasswordRequest):
    """Reset payload for the authenticated recovery flow (no email field)."""

    pass


class ChangePasswordRequest(_NewPasswordRequest):
    current_password: str
    security_question: str | None = None
    security_answer: str | None = None


class MFASetupResponse(BaseModel):
    secret: str
    qr_url: str
    manual_entry_key: str


class MFAVerifyRequest(_CodeRequest):
    preauth_token: str | None = (
        None  # present during login exchange, absent during setup
    )


class MFADisableRequest(BaseModel):
    """Body for `POST /auth/mfa/disable`.

    A bare `str`, not a `_NewPasswordRequest`: this authenticates the current
    password rather than setting a new one, so the strength policy (and the
    length bounds that come with it) do not apply.
    """

    password: str


class BackupCodesResponse(BaseModel):
    codes: list[str]
    remaining: int


class BackupCodesSummaryResponse(BaseModel):
    total: int
    remaining: int
    last_generated_at: datetime | None = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    mfa_enabled: bool = False
    must_change_password: bool = False
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    id: int
    role: UserRole
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr
    mfa_enabled: bool
    security_question_set: bool
    must_change_password: bool
    last_login: datetime | None = None

    face_enrolled: bool | None = None
    face_enrolled_at: datetime | None = None
    face_embedding_version: int | None = None

    claim_status: str | None = None


class AdminPasswordResetResponse(BaseModel):
    """Body for the three admin-initiated `.../reset-password` routes.

    Lives here rather than per-slice because all three reset the same thing — a
    `users` row — and `AuthService.admin_reset_password` is the single
    implementation behind them.
    """

    temp_password: str


class LockoutStatusResponse(BaseModel):
    user_id: int
    email: str | None = None
    role: str
    is_locked: bool
    is_permanently_locked: bool = False
    locked_at: datetime | None = None
    lockout_level: int = 0
    lockout_duration_minutes: int = 0
    locked_until: datetime | None = None
    remaining_minutes: int | None = None
    last_lockout_at: datetime | None = None
    override_until: datetime | None = None
    override_remaining_minutes: int | None = None


class LockoutReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class LockoutOverrideRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1)
    reason: str = Field(..., min_length=3, max_length=500)


class SessionPolicyResponse(BaseModel):
    idle_timeout_minutes: int
    idle_warning_minutes: int
