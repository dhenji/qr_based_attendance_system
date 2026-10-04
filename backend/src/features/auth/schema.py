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
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
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
    username: str = Field(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
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
    must_change_password: bool = False


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


class ChangePasswordRequest(_NewPasswordRequest):
    current_password: str


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
    username: str
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
