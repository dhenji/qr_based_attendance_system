from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from pydantic.fields import Field

from features.auth.constants import (
    OTP_CODE_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)
from shared.enums import UserRole
from shared.validators import password_strength


class OTPRequest(BaseModel):
    email: EmailStr


class _CodeRequest(BaseModel):
    code: str = Field(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)


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

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_pending: bool = False
    preauth_token: str | None = None  # grant no access; exchanged via /auth/mfa/verify


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
