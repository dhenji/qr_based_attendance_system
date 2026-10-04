from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
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
    TEMP_PASSWORD_LENGTH,
)
from features.auth.exceptions import (
    AccountLockedException,
    AmbiguousAccountException,
    CurrentPasswordInvalid,
    InvalidCredentialsException,
    MfaAlreadyEnabledException,
    MfaNotEnabledException,
    MfaVerifyException,
    OtpExpiredException,
    OtpInvalidException,
    RecoveryGrantRequiredException,
    RecoveryLockedException,
    SecurityAnswerInvalidException,
    UnrecognizedEmailException,
    UserAlreadyClaimedException,
    UserNotFoundException,
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
from shared.audit import record_audit
from shared.base import BaseCRUD
from shared.email import send_otp_email
from shared.enums import AuditAction, AuditEntity, OtpPurpose, UserRole
from shared.rate_limit import FixedWindowLimiter

logger: logging.Logger = logging.getLogger(__name__)

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


def _account_snapshot(user: User) -> dict[str, Any]:
    """The mutable account-state columns, and nothing else.

    Deliberately excludes the email, the password hash and every MFA secret:
    these dicts land in `audit_logs`, which every admin can read.
    """
    return {
        "failed_login_attempts": user.failed_login_attempts,
        "is_locked": user.is_locked,
        "locked_at": user.locked_at.isoformat() if user.locked_at else None,
        "must_change_password": user.must_change_password,
    }


@asynccontextmanager
async def _lockout_transaction() -> AsyncIterator[AsyncSession]:
    """A session that commits, for writes that must outlive a failed request.

    Every write on the login path describes a request that is about to raise
    `InvalidCredentialsException`, and `_get_db` rolls its transaction back on
    any exception. A counter written there would be discarded along with the
    audit row, which means the lockout threshold is never actually reached —
    the counter is the lockout mechanism, so it has to commit on its own.

    Failures are logged and swallowed: audit bookkeeping must never be the
    reason a login stops working.
    """
    async with database.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Lockout bookkeeping failed")


async def _clear_expired_lockout(user_id: int) -> None:
    """Release a lock whose window has elapsed, and record the release."""
    async with _lockout_transaction() as session:
        user: User | None = await session.get(User, user_id)

        if user is None:
            return

        old_value: dict[str, Any] = _account_snapshot(user)
        user.is_locked = False
        user.locked_at = None
        user.failed_login_attempts = 0

        await record_audit(
            session,
            actor_id=None,
            action=AuditAction.UNLOCK,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value=_account_snapshot(user),
        )


async def _register_failed_attempt(user_id: int, lockout_attempts: int) -> None:
    """Count one wrong password and lock the account on the threshold."""
    async with _lockout_transaction() as session:
        user: User | None = await session.get(User, user_id)

        if user is None:
            return

        old_value: dict[str, Any] = _account_snapshot(user)
        user.failed_login_attempts += 1
        locked: bool = user.failed_login_attempts >= lockout_attempts

        if locked:
            user.is_locked = True
            user.locked_at = datetime.now(timezone.utc)

        await record_audit(
            session,
            actor_id=None,
            action=AuditAction.LOCK if locked else AuditAction.LOGIN_FAILED,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value=_account_snapshot(user),
        )


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

            await _clear_expired_lockout(user.id)

        if not verify_password(password, user.password_hash):
            await _register_failed_attempt(user.id, self._settings.lockout_attempts)
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

        The cap counts *failures*, not attempts: `exhausted` is checked without
        recording, and the budget is only spent below on the failure branch.
        Calling `hit` up front would lock a legitimate user out after three
        correct answers inside the window.
        """

        normalized: str = email.lower()
        limiter_key: str = f"forgot_password|{normalized}"

        if await _recovery_limiter.exhausted(
            limiter_key,
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
            await _recovery_limiter.hit(
                limiter_key,
                SECURITY_RECOVERY_MAX_ATTEMPTS,
                self._settings.lockout_duration_minutes * 60,
            )
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

        old_value: dict[str, Any] = _account_snapshot(user)

        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.must_change_password = False

        await record_audit(
            self._session,
            actor_id=user.id,
            action=AuditAction.PASSWORD_RESET,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value=_account_snapshot(user),
        )
        await self._session.flush()

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise CurrentPasswordInvalid()

        user.password_hash = hash_password(new_password)
        user.must_change_password = False

        await self._session.flush()

    async def admin_reset_password(self, *, user_id: int, actor_id: int) -> str:
        """Set a temporary password on someone else's account. Returns it once.

        The one implementation behind all three admin routes
        (`/admin/users/{id}`, `/admin/students/{id}`, `/admin/professors/{id}`);
        the student and professor slices resolve their roster row to a
        `users.id` and call this, so the credential write has a single home.

        Clears the lockout alongside the password, same as the self-service
        `reset_password` above. Without that an admin could not actually help a
        locked-out account, which is the case the endpoint exists for — the
        counter and `is_locked` would survive the new password.

        Deliberately does *not* touch MFA. An admin able to clear MFA as a side
        effect of a password reset could remove a second factor the account
        owner chose and never see it in the trail; `POST /auth/mfa/disable` is
        the path for that, and it is password-verified for exactly this reason.

        `actor_id` is the admin, so `performed_by` says who did it while
        `entity_id` stays the account whose password changed.
        """
        user: User | None = await self._users.get(user_id)

        if user is None:
            raise UserNotFoundException()

        old_value: dict[str, Any] = _account_snapshot(user)

        temp_password: str = secrets.token_urlsafe(TEMP_PASSWORD_LENGTH)

        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.PASSWORD_RESET,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value=_account_snapshot(user),
        )
        await self._session.flush()

        return temp_password

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

    async def disable_mfa(self, user: User, password: str) -> None:
        """Turn MFA off, invalidating every outstanding backup code.

        The contract (api-contracts.md) is explicit about all four effects:
        verify the password, clear `mfa_enabled`, clear the TOTP secret, and
        invalidate the unconsumed backup codes. The last one is the security
        point — leaving them live would hand a caller ten working codes for an
        account that no longer challenges for a code.

        Codes are consumed with `used_at` rather than deleted, matching
        `generate_backup_codes`: the rows are the historical record, and
        `list_backup_codes` derives `remaining` from `used_at IS NULL`, so this
        is what makes a disabled account report zero remaining.
        """

        # Guard before the Argon2id verify: disabling MFA on an account that
        # never had it is a no-op call, and password hashing is deliberately
        # expensive. Checking the flag first also keeps the two failure modes
        # distinguishable — a wrong password is 400, no MFA is 409.
        if not user.mfa_enabled:
            raise MfaNotEnabledException()

        if not verify_password(password, user.password_hash):
            raise CurrentPasswordInvalid()

        now: datetime = datetime.now(timezone.utc)

        outstanding: Sequence[MfaBackupCodes] = (
            await self._session.scalars(
                select(MfaBackupCodes).where(
                    MfaBackupCodes.user_id == user.id, MfaBackupCodes.used_at.is_(None)
                )
            )
        ).all()

        for record in outstanding:
            record.used_at = now

        user.mfa_enabled = False
        user.mfa_secret = None

        # `_account_snapshot` deliberately omits every MFA field, so this audit
        # row carries its own snapshot rather than widening the three other
        # call sites' payloads. The secret is never included.
        await record_audit(
            self._session,
            actor_id=user.id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value={"mfa_enabled": True},
            new_value={"mfa_enabled": False},
        )

        await self._session.flush()

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
