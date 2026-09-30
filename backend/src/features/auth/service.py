from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import (
    PREAUTH_TOKEN_TYPE,
    RECOVERY_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    backup_code_fingerprint,
    create_access_token,
    create_preauth_token,
    create_recovery_token,
    create_refresh_token,
    decode_access_token,
    decode_recovery_token,
    extract_user_id,
    generate_backup_code,
    generate_otp,
    hash_otp,
    hash_password,
    normalize_backup_code,
)
from core.security import verify_otp as verify_otp_hash
from core.security import verify_password
from features.auth.constants import (
    BACKUP_CODE_COUNT,
    BACKUP_CODE_GROUPS,
    BACKUP_CODE_LENGTH,
    SECURITY_QUESTION_POOL,
    SECURITY_RECOVERY_MAX_ATTEMPTS,
)
from features.auth.exceptions import (
    AccountLockedException,
    AmbiguousAccountException,
    CurrentPasswordInvalid,
    InvalidCredentialsException,
    MfaAlreadyEnabledException,
    MfaVerifyException,
    OtpExpiredException,
    OtpInvalidException,
    RecoveryGrantRequiredException,
    RecoveryLockedException,
    SecurityAnswerInvalidException,
    UnrecognizedEmailException,
    UserAlreadyClaimedException,
)
from features.auth.model import MfaBackupCodes, OtpCodes, User
from features.auth.schema import (
    BackupCodesResponse,
    BackupCodesSummaryResponse,
    MeResponse,
    MFASetupResponse,
    RecoveryGrantResponse,
    SecurityQuestionResponse,
    TokenResponse,
)
from features.professor.model import Professor
from features.student.model import Student
from shared.base import BaseCRUD
from shared.email import send_otp_email
from shared.enums import OtpPurpose, UserRole
from shared.rate_limit import FixedWindowLimiter

_recovery_limiter = FixedWindowLimiter()


def _decoy_question(email: str, settings: Settings) -> str:
    """Pick a stable decoy question for an unknown email (ADR-056).

    Keyed on the normalized email with HMAC_SECRET_KEY (falling back to
    JWT_SECRET) so the same address always maps to the same question. Never
    returns the address itself, which would defeat the purpose.
    """

    secret: str = settings.hmac_secret_key or settings.jwt_secret

    if not secret:
        return SECURITY_QUESTION_POOL[0]

    index: int = int(
        hmac.new(
            secret.encode("utf-8"), email.encode("utf-8"), hashlib.sha256
        ).hexdigest(),
        16,
    ) % len(SECURITY_QUESTION_POOL)

    return SECURITY_QUESTION_POOL[index]


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self._session = session
        self._settings = settings or get_settings()

        self._users: BaseCRUD[User] = BaseCRUD(User, session)
        self._otp: BaseCRUD[OtpCodes] = BaseCRUD(OtpCodes, session)
        self._student: BaseCRUD[Student] = BaseCRUD(Student, session)
        self._professor: BaseCRUD[Professor] = BaseCRUD(Professor, session)

        self._backup_codes: BaseCRUD[MfaBackupCodes] = BaseCRUD(MfaBackupCodes, session)

    async def request_otp(
        self,
        email: str,
        purpose: OtpPurpose = OtpPurpose.CLAIM,
        recovery_token: str | None = None,
    ) -> None:
        normalized: str = email.lower()
        now: datetime = datetime.now(timezone.utc)

        if purpose is OtpPurpose.FORGET_PASSWORD:
            self._assert_recovery_grant(normalized, recovery_token)

        # Resending must not leave a second code valid: burn any unconsumed OTP
        # for the same (email, purpose) so only the newest one can be verified.
        await self._consume_active_otps(normalized, purpose, now)

        code: str = generate_otp()

        await self._otp.create(
            email=normalized,
            purpose=purpose.value,
            otp_hash=hash_otp(code),
            expires_at=now + timedelta(minutes=self._settings.otp_expires_minutes),
        )

        send_otp_email(email, code)

    def _assert_recovery_grant(self, email: str, recovery_token: str | None) -> None:
        """Gate step 3 on a valid step-2 grant for the same address.

        Holding the OTP is what authorises step 4, so minting one is the only place
        the security-answer gate has to be enforced. A bad or mismatched grant is
        reported as a plain invalid-credentials 400 rather than a distinct error so
        this path stays indistinguishable from any other auth failure.
        """

        if not recovery_token:
            raise RecoveryGrantRequiredException()

        payload: dict[str, Any] | None = decode_recovery_token(
            recovery_token, self._settings
        )

        if payload is None or payload.get("email") != email:
            raise RecoveryGrantRequiredException()

    async def _consume_active_otps(
        self, email: str, purpose: OtpPurpose, now: datetime
    ) -> None:
        stmt: Select[tuple[OtpCodes]] = select(OtpCodes).where(
            OtpCodes.email == email,
            OtpCodes.purpose == purpose.value,
            OtpCodes.consumed_at.is_(None),
        )

        stale: Sequence[OtpCodes] = (await self._session.scalars(stmt)).all()

        for record in stale:
            record.consumed_at = now

        if stale:
            await self._session.flush()

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
                hash_password(self._normalize_answer(security_answer))
                if security_answer
                else None
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
                must_change_password=user.must_change_password,
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

    async def forgot_password(self, email: str) -> SecurityQuestionResponse:
        """Return the security question for step 2 of the recovery flow.

        api-contracts.md requires an identical response for unknown emails so the
        endpoint cannot be used to enumerate registered accounts, so an unknown
        email gets a deterministic decoy from SECURITY_QUESTION_POOL rather than a
        null question. The choice is keyed on the email (not random) because a
        varying decoy would itself become a reliable enumeration oracle, and it
        would change under a legitimate user who retried after a typo.
        """

        normalized: str = email.lower()
        user: User | None = await self._users.get_by(email=normalized)

        if user is None or user.security_question_hash is None:
            return SecurityQuestionResponse(
                question=_decoy_question(normalized, self._settings), set=True
            )

        return SecurityQuestionResponse(question=user.security_question_hash, set=True)

    async def forgot_password_step2(
        self, email: str, answer: str
    ) -> RecoveryGrantResponse:
        """Verify the security answer and issue a short-lived recovery grant.

        The grant is what gates step 3: without it a FORGET_PASSWORD OTP cannot be
        minted, so the mandatory security-question gate and its 3-attempt cap
        cannot be skipped. Unknown emails and wrong answers return the identical
        error and consume the same attempt budget, so this endpoint is not an
        enumeration oracle either.
        """

        normalized: str = email.lower()

        if not await _recovery_limiter.hit(
            f"forgot_password|{normalized}",
            SECURITY_RECOVERY_MAX_ATTEMPTS,
            self._settings.lockout_duration_minutes * 60,
        ):
            raise RecoveryLockedException(self._settings.lockout_duration_minutes)

        user: User | None = await self._users.get_by(email=normalized)

        if (
            user is None
            or user.security_answer_hash is None
            or not verify_password(
                self._normalize_answer(answer), user.security_answer_hash
            )
        ):
            await self._session.flush()
            raise SecurityAnswerInvalidException()

        return RecoveryGrantResponse(
            recovery_token=create_recovery_token(user.id, user.email, self._settings)
        )

    async def set_security_question(
        self, user: User, question: str, answer: str
    ) -> None:
        user.security_question_hash = question
        user.security_answer_hash = hash_password(self._normalize_answer(answer))

        await self._session.flush()

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

    async def generate_backup_codes(self, user: User) -> BackupCodesResponse:
        now: datetime = datetime.now(timezone.utc)

        stale: Sequence[MfaBackupCodes] = (
            await self._session.scalars(
                select(MfaBackupCodes).where(
                    MfaBackupCodes.user_id == user.id, MfaBackupCodes.used_at.is_(None)
                )
            )
        ).all()

        for record in stale:
            record.used_at = now

        plaintext: list[str] = []
        for _ in range(BACKUP_CODE_COUNT):
            code: str = generate_backup_code()
            normalized: str = self._normalize_backup_code(code)
            plaintext.append(self._format_backup_code(code))

            await self._backup_codes.create(
                user_id=user.id,
                code_hash=hash_password(normalized),
                code_fingerprint=backup_code_fingerprint(normalized, self._settings),
            )

        return BackupCodesResponse(codes=plaintext, remaining=BACKUP_CODE_COUNT)

    async def list_backup_codes(self, user: User) -> BackupCodesSummaryResponse:
        rows: Sequence[MfaBackupCodes] = (
            await self._session.scalars(
                select(MfaBackupCodes)
                .where(MfaBackupCodes.user_id == user.id)
                .order_by(MfaBackupCodes.created_at.desc())
            )
        ).all()

        if not rows:
            return BackupCodesSummaryResponse(
                total=0, remaining=0, last_generated_at=None
            )

        latest_generated_at: datetime = rows[0].created_at
        latest_batch: list[MfaBackupCodes] = [
            record for record in rows if record.created_at == latest_generated_at
        ]

        return BackupCodesSummaryResponse(
            total=len(latest_batch),
            remaining=sum(1 for r in latest_batch if r.used_at is None),
            last_generated_at=latest_generated_at,
        )

    async def verify_backup_code(self, user: User, code: str) -> bool:
        normalized: str = self._normalize_backup_code(code)

        if len(normalized) != BACKUP_CODE_LENGTH:
            return False

        # Resolve the single candidate row via the indexed fingerprint so we pay
        # for at most one Argon2id verify, then treat code_hash as authoritative.
        record: MfaBackupCodes | None = await self._session.scalar(
            select(MfaBackupCodes).where(
                MfaBackupCodes.user_id == user.id,
                MfaBackupCodes.used_at.is_(None),
                MfaBackupCodes.code_fingerprint
                == backup_code_fingerprint(normalized, self._settings),
            )
        )

        if record is None or not verify_password(normalized, record.code_hash):
            return False

        record.used_at = datetime.now(timezone.utc)
        await self._session.flush()

        return True

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

        if user is None:
            raise MfaVerifyException()

        is_totp: bool = bool(user.mfa_secret) and self._valid_mfa_code(user, code)
        is_backup: bool = not is_totp and await self.verify_backup_code(user, code)

        if not is_totp and not is_backup:
            raise MfaVerifyException()

        if not user.mfa_enabled:
            user.mfa_enabled = True
            await self._session.flush()

        return self._build_tokens(user)

    async def get_me(self, user: User) -> MeResponse:
        student: Student | None = await self._student.get_by(user_id=user.id)
        professor: Professor | None = await self._professor.get_by(user_id=user.id)

        first_name: str | None = None
        last_name: str | None = None

        if student is not None:
            first_name, last_name = student.first_name, student.last_name
        elif professor is not None:
            first_name, last_name = professor.first_name, professor.last_name

        claim_status: str | None = None
        if professor is not None:
            claim_status = "claimed" if professor.user_id is not None else "unclaimed"

        return MeResponse(
            id=user.id,
            role=UserRole(user.role),
            first_name=first_name,
            last_name=last_name,
            email=user.email,
            mfa_enabled=user.mfa_enabled,
            security_question_set=user.security_question_hash is not None,
            must_change_password=user.must_change_password,
            last_login=user.last_login,
            face_enrolled=(
                student.face_enrolled_at is not None if student is not None else None
            ),
            face_enrolled_at=student.face_enrolled_at if student is not None else None,
            face_embedding_version=(
                student.face_embedding_version if student is not None else None
            ),
            claim_status=claim_status,
        )

    def _build_tokens(self, user: User) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user.id, user.role, self._settings),
            refresh_token=create_refresh_token(user.id, self._settings),
            must_change_password=user.must_change_password,
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

    @staticmethod
    def _normalize_answer(answer: str) -> str:
        return answer.strip().casefold()

    @staticmethod
    def _normalize_backup_code(code: str) -> str:
        return normalize_backup_code(code)

    @staticmethod
    def _format_backup_code(code: str) -> str:
        chunks: list[str] = []
        index: int = 0

        for size in BACKUP_CODE_GROUPS:
            chunks.append(code[index : index + size])
            index += size

        return "-".join(chunks)
