from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import (
    PREAUTH_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_preauth_token,
    create_refresh_token,
    decode_access_token,
    extract_user_id,
    generate_otp,
    hash_otp,
    hash_password,
)
from core.security import verify_otp as verify_otp_hash
from core.security import verify_password
from features.auth.exceptions import (
    AccountLockedException,
    AmbiguousAccountException,
    CurrentPasswordInvalid,
    InvalidCredentialsException,
    MfaAlreadyEnabledException,
    MfaVerifyException,
    OtpExpiredException,
    OtpInvalidException,
    UnrecognizedEmailException,
    UserAlreadyClaimedException,
)
from features.auth.model import OtpCodes, User
from features.auth.schema import MFASetupResponse, TokenResponse
from features.professor.model import Professor
from features.student.model import Student
from shared.base import BaseCRUD
from shared.email import send_otp_email
from shared.enums import OtpPurpose, UserRole


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

        self._users: BaseCRUD[User] = BaseCRUD(User, session)
        self._otp: BaseCRUD[OtpCodes] = BaseCRUD(OtpCodes, session)
        self._student: BaseCRUD[Student] = BaseCRUD(Student, session)
        self._professor: BaseCRUD[Professor] = BaseCRUD(Professor, session)

    async def request_otp(
        self, email: str, purpose: OtpPurpose = OtpPurpose.CLAIM
    ) -> None:
        code: str = generate_otp()

        await self._otp.create(
            email=email.lower(),
            purpose=purpose.value,
            otp_hash=hash_otp(code),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=self._settings.otp_expires_minutes),
        )

        send_otp_email(email, code)

    async def verify_otp(
        self, email: str, code: str, purpose: OtpPurpose = OtpPurpose.CLAIM
    ) -> None:
        now: datetime = datetime.now(timezone.utc)

        stmt: Select[tuple[OtpCodes]] = (
            select(OtpCodes)
            .where(
                OtpCodes.email == email.lower(),
                OtpCodes.purpose == purpose.value,
                OtpCodes.consumed_at.is_(None),
            )
            .order_by(OtpCodes.id.desc())
        )

        record: OtpCodes | None = (await self._session.scalars(stmt)).first()

        if record is None:
            raise OtpInvalidException()
        if record.expires_at < now:
            raise OtpExpiredException()
        if not verify_otp_hash(code, record.otp_hash):
            raise OtpInvalidException()

        record.consumed_at = now
        await self._session.flush()

    async def register(
        self,
        email: str,
        otp_code: str,
        username: str,
        password: str,
        security_question: str | None = None,
        security_answer: str | None = None,
    ) -> TokenResponse:
        normalized: str = email.lower()

        await self.verify_otp(normalized, otp_code, OtpPurpose.CLAIM)

        if await self._users.get_by(email=normalized) is not None:
            raise UserAlreadyClaimedException()

        student, professor = await self._find_roster_match(normalized)
        if student is not None and professor is not None:
            raise AmbiguousAccountException()
        if student is None and professor is None:
            raise UnrecognizedEmailException()

        role: UserRole = UserRole.STUDENT if student is not None else UserRole.PROFESSOR

        user = await self._users.create(
            username=username,
            email=normalized,
            password_hash=hash_password(password),
            security_question_hash=security_question,
            security_answer_hash=(
                hash_password(security_answer) if security_answer else None
            ),
            role=role.value,
        )

        if student is not None:
            student.user_id = user.id
        if professor is not None:
            professor.user_id = user.id

        return self._build_tokens(user)

    async def login(self, email: str, password: str) -> TokenResponse:
        user: User | None = await self._users.get_by(email=email.lower())

        if user is None or not user.is_active:
            raise InvalidCredentialsException()

        now: datetime = datetime.now(timezone.utc)

        if user.is_locked and user.locked_at is not None:
            locked_until: datetime = user.locked_at + timedelta(
                minutes=self._settings.lockout_duration_minutes
            )

            if now < locked_until:
                remaining: int = int((locked_until - now).total_seconds() // 60) + 1
                raise AccountLockedException(remaining)

            user.is_locked = False
            user.locked_at = None
            user.failed_login_attempts = 0

        if not verify_password(password, user.password_hash):
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= self._settings.lockout_attempts:
                user.is_locked = True
                user.locked_at = now

            await self._session.flush()
            raise InvalidCredentialsException()

        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.last_login = now
        await self._session.flush()

        if user.mfa_enabled:
            return TokenResponse(
                mfa_pending=True,
                preauth_token=create_preauth_token(user.id, self._settings),
            )

        return self._build_tokens(user)

    async def refresh_token(self, token: str) -> TokenResponse:
        payload: dict[str, Any] | None = decode_access_token(token, self._settings)

        if payload is None or payload.get("type") != REFRESH_TOKEN_TYPE:
            raise InvalidCredentialsException()

        user: User | None = await self._users.get(extract_user_id(payload))

        if user is None or not user.is_active:
            raise InvalidCredentialsException()

        return self._build_tokens(user)

    async def forgot_password(self, email: str) -> dict[str, Any]:
        user: User | None = await self._users.get_by(email=email)

        if user is None or user.security_question_hash is None:
            return {"security_question_set": False}

        return {
            "security_question_set": True,
            "question": user.security_question_hash,
        }

    async def reset_password(
        self, email: str, otp_code: str, new_password: str
    ) -> None:
        normalized: str = email.lower()
        await self.verify_otp(normalized, otp_code, OtpPurpose.FORGET_PASSWORD)

        user: User | None = await self._users.get_by(email=normalized)

        if user is None or not user.is_active:
            raise UnrecognizedEmailException()

        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.must_change_password = False

        await self._session.flush()

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise CurrentPasswordInvalid()

        user.password_hash = hash_password(new_password)
        user.must_change_password = False

        await self._session.flush()

    async def setup_mfa(self, user: User) -> MFASetupResponse:
        if user.mfa_enabled:
            raise MfaAlreadyEnabledException()

        secret: str = pyotp.random_base32()
        otpauth_url: str = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name=self._settings.app_name
        )

        user.mfa_secret = secret
        await self._session.flush()

        return MFASetupResponse(
            secret=secret, qr_url=otpauth_url, manual_entry_key=secret
        )

    async def verify_mfa(
        self, code: str, preauth_token: str | None = None, user: User | None = None
    ) -> TokenResponse:
        if preauth_token is not None:
            payload: dict[str, Any] | None = decode_access_token(
                preauth_token, self._settings
            )

            if payload is None or payload.get("type") != PREAUTH_TOKEN_TYPE:
                raise InvalidCredentialsException()

            user = await self._users.get(extract_user_id(payload))

            if user is None or not user.is_active:
                raise InvalidCredentialsException()

        if user is None or not user.mfa_secret or not self._valid_mfa_code(user, code):
            raise MfaVerifyException()

        if not user.mfa_enabled:
            user.mfa_enabled = True
            await self._session.flush()

        return self._build_tokens(user)

    def _build_tokens(self, user: User) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user.id, user.role, self._settings),
            refresh_token=create_refresh_token(user.id, self._settings),
        )

    @staticmethod
    def _valid_mfa_code(user: User, code: str) -> bool:
        if not user.mfa_secret:
            return False
        return pyotp.TOTP(user.mfa_secret).verify(code)

    async def _find_roster_match(
        self, email: str
    ) -> tuple[Student | None, Professor | None]:
        normalized: str = email.lower()

        student: Student | None = await self._student.get_by(
            email=normalized, is_active=True
        )

        professor: Professor | None = await self._professor.get_by(
            email=normalized, is_active=True
        )

        return student, professor
