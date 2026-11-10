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
from core.exceptions import ForbiddenException
from core.database import database
from core.security import (
    LOGIN_OTP_TOKEN_TYPE,
    PREAUTH_TOKEN_TYPE,
    RECOVERY_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    backup_code_fingerprint,
    create_access_token,
    create_login_otp_token,
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
    LOGIN_OTP_IP_MAX_ATTEMPTS,
    LOGIN_OTP_MAX_ATTEMPTS,
    SECURITY_QUESTION_POOL,
    SECURITY_RECOVERY_MAX_ATTEMPTS,
    TEMP_PASSWORD_LENGTH,
)
from features.auth.exceptions import (
    AccountLockedException,
    AmbiguousAccountException,
    CurrentPasswordInvalid,
    InvalidCredentialsException,
    InvalidOverrideDurationException,    LoginOtpLockedException,
    PermanentAccountLockedException,

    MfaAlreadyEnabledException,
    MfaNotEnabledException,
    MfaVerifyException,
    OtpInvalidException,
    OtpExpiredException,
    OtpMaxAttemptsException,
    PermanentAccountLockedException,
    PasswordReusedException,
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
    PasswordRecoveryStartResponse,
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
from shared.user_management_policy import (
    can_manage_target,
    can_mutate_lockout,
    can_read_lockout,
    can_view_target,
    hide_sensitive_fields,
)
from shared.rate_limit import FixedWindowLimiter, RateLimitedException

logger: logging.Logger = logging.getLogger(__name__)

_recovery_limiter = FixedWindowLimiter()
_login_otp_limiter = FixedWindowLimiter()
_login_otp_ip_limiter = FixedWindowLimiter()


def _mask_email(email: str) -> str:
    """Mask the local part of an email for display (e.g. j***@example.com)."""

    local, separator, domain = email.partition("@")
    if not separator:
        return email
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


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
        "lockout_level": user.lockout_level,
        "last_lockout_at": user.last_lockout_at.isoformat()
        if user.last_lockout_at
        else None,
        "lockout_override_until": user.lockout_override_until.isoformat()
        if user.lockout_override_until
        else None,
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


def _escalation_minutes(settings: Settings, level: int) -> int:
    raw: str = (settings.lockout_escalation_minutes or "").strip()
    table: list[int] = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                table.append(int(part))
            except ValueError:
                continue
    if not table:
        table = [settings.lockout_duration_minutes]
    if level < 1:
        level = 1
    return table[min(level - 1, len(table) - 1)]


def _escalation_table_len(settings: Settings) -> int:
    raw: str = (settings.lockout_escalation_minutes or "").strip()
    count: int = 0
    for part in raw.split(","):
        if part.strip():
            try:
                int(part.strip())
                count += 1
            except ValueError:
                continue
    return count if count > 0 else 1


def _override_active(user: User) -> bool:
    if user.lockout_override_until is None:
        return False
    return datetime.now(timezone.utc) < user.lockout_override_until


async def _clear_expired_lockout(user_id: int) -> None:
    """Release a lock whose window has elapsed, and record the release."""
    async with _lockout_transaction() as session:
        stmt = select(User).where(User.id == user_id).with_for_update()
        user: User | None = (await session.execute(stmt)).scalar_one_or_none()

        if user is None:
            return

        # Never auto-clear a permanent lock.
        if (user.lockout_level or 0) > _escalation_table_len(get_settings()):
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
        stmt = select(User).where(User.id == user_id).with_for_update()
        user: User | None = (await session.execute(stmt)).scalar_one_or_none()

        if user is None:
            return

        now: datetime = datetime.now(timezone.utc)

        old_value: dict[str, Any] = _account_snapshot(user)
        user.failed_login_attempts += 1
        locked: bool = user.failed_login_attempts >= lockout_attempts

        if locked:
            current_level: int = user.lockout_level or 0
            # Escalation table length determines the maximum normal level.
            try:
                from core.config import get_settings

                table_len: int = len(
                    [p for p in (get_settings().lockout_escalation_minutes or "").split(",") if p.strip()]
                )
            except Exception:
                table_len = 6
            if table_len < 1:
                table_len = 1
            if current_level >= table_len:
                # Promote to a permanent lock (level beyond the table).
                user.lockout_level = table_len + 1
            else:
                user.lockout_level = current_level + 1
            user.is_locked = True
            user.locked_at = now
            user.last_lockout_at = now

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

    async def _resolve_actor_role(
        self,
        *,
        actor_id: int | None = None,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> UserRole:
        if actor_role is not None:
            return actor_role if isinstance(actor_role, UserRole) else UserRole(actor_role)
        if viewer_role is not None:
            return viewer_role if isinstance(viewer_role, UserRole) else UserRole(viewer_role)
        if actor_id is not None:
            try:
                user: User | None = await self._users.get(actor_id)
            except AttributeError:
                user = None
            if user is not None:
                return UserRole(user.role)
        return UserRole.SUPER_ADMIN

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

        send_otp_email(email, code, purpose=purpose, settings=self._settings)

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
            .with_for_update()
        )

        record: OtpCodes | None = (await self._session.scalars(stmt)).first()

        if record is None:
            raise OtpInvalidException()
        if record.expires_at < now:
            raise OtpExpiredException()
        if not verify_otp_hash(code, record.otp_hash):
            current_attempts: int = getattr(record, "failed_attempts", 0) or 0
            record.failed_attempts = current_attempts + 1
            if record.failed_attempts >= self._settings.otp_max_attempts:
                record.consumed_at = now
                await self._session.flush()
                raise OtpMaxAttemptsException()
            await self._session.flush()
            raise OtpInvalidException()

        record.consumed_at = now
        await self._session.flush()

    async def register(
        self,
        email: str,
        otp_code: str,
        password: str,
        security_question: str | None = None,
        security_answer: str | None = None,
    ) -> TokenResponse:
        normalized: str = email.lower()

        await self.verify_otp(normalized, otp_code, OtpPurpose.CLAIM)

        existing: User | None = await self._users.get_by(email=normalized)

        if existing is not None and existing.is_active:
            raise UserAlreadyClaimedException()

        student, professor = await self._find_roster_match(normalized)
        if student is not None and professor is not None:
            raise AmbiguousAccountException()
        if student is None and professor is None:
            raise UnrecognizedEmailException()

        if existing is not None:
            # Inactive login for this email (e.g. orphaned by a roster
            # hard-delete): reclaim it for the fresh roster row instead of
            # minting a second users row the unique email constraint forbids.
            # No live roster match, no revival — a ban without a roster row
            # stays dead.
            return await self._reclaim_inactive_login(
                existing,
                student=student,
                professor=professor,
                password=password,
                security_question=security_question,
                security_answer=security_answer,
            )

        role: UserRole = UserRole.STUDENT if student is not None else UserRole.PROFESSOR

        user = await self._users.create(
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

    async def _reclaim_inactive_login(
        self,
        existing: User,
        *,
        student: Student | None,
        professor: Professor | None,
        password: str,
        security_question: str | None,
        security_answer: str | None,
    ) -> TokenResponse:
        """Reactivate a deactivated login for a freshly created roster row.

        Hard-delete retains (and deactivates) the linked `users` row so audit
        history stays joinable, which blocks re-creation: the email is still
        taken. When the caller proves current ownership of the address with a
        fresh CLAIM OTP and exactly one live, unclaimed roster row matches,
        the old login is revived for the new row instead of failing 409.

        Every check precedes the first write, and all writes stay in the
        caller's flush-only transaction, so a 409 leaves the orphan inactive,
        the roster row unlinked, and the trail untouched.
        """
        match: Student | Professor | None = (
            student if student is not None else professor
        )

        if match is None or match.user_id is not None:
            # Ambiguous/none is already rejected by the caller; an already
            # claimed match must not be stolen — report it as taken without
            # saying which account holds it.
            raise UserAlreadyClaimedException()

        now: datetime = datetime.now(timezone.utc)

        existing.password_hash = hash_password(password)
        existing.security_question_hash = security_question
        existing.security_answer_hash = (
            hash_password(self._normalize_answer(security_answer))
            if security_answer
            else None
        )
        existing.role = (
            UserRole.STUDENT if student is not None else UserRole.PROFESSOR
        ).value
        existing.is_active = True
        existing.failed_login_attempts = 0
        existing.is_locked = False
        existing.locked_at = None
        existing.must_change_password = False
        # The new holder must not inherit the old holder's second factor:
        # clear it and invalidate outstanding backup codes the same way
        # `disable_mfa` does (stamp `used_at`, never delete).
        outstanding: Sequence[MfaBackupCodes] = (
            await self._session.scalars(
                select(MfaBackupCodes).where(
                    MfaBackupCodes.user_id == existing.id,
                    MfaBackupCodes.used_at.is_(None),
                )
            )
        ).all()

        for record in outstanding:
            record.used_at = now

        existing.mfa_enabled = False
        existing.mfa_secret = None

        match.user_id = existing.id

        await self._session.flush()
        await record_audit(
            self._session,
            actor_id=None,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=existing.id,
            old_value={"is_active": False},
            new_value={"is_active": True},
        )

        return self._build_tokens(existing)

    async def login(self, email: str, password: str) -> TokenResponse:
        user: User | None = await self._users.get_by(email=email.lower())

        if user is None or not user.is_active:
            raise InvalidCredentialsException()

        now: datetime = datetime.now(timezone.utc)

        override_active: bool = _override_active(user)

        # Permanent lock: never auto-clears, even after the normal window.
        if (user.lockout_level or 0) > _escalation_table_len(self._settings) and user.is_locked:
            raise PermanentAccountLockedException()

        if user.is_locked and user.locked_at is not None and not override_active:
            duration_minutes: int = _escalation_minutes(
                self._settings, user.lockout_level or 1
            )
            locked_until: datetime = user.locked_at + timedelta(
                minutes=duration_minutes
            )

            if now < locked_until:
                remaining: int = int((locked_until - now).total_seconds() // 60) + 1
                if remaining < 1:
                    remaining = 1
                raise AccountLockedException(remaining)

            await _clear_expired_lockout(user.id)

        if not verify_password(password, user.password_hash):
            await _register_failed_attempt(user.id, self._settings.lockout_attempts)
            raise InvalidCredentialsException()

        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.lockout_level = 0
        user.last_lockout_at = None
        user.last_login = now
        await self._session.flush()

        # Second factor, by role. Students and professors who enrolled in MFA
        # keep their TOTP path (no email is sent): TOTP is strictly stronger
        # than an emailed code, so replacing the OTP loses no security while
        # sparing the SMTP relay one message per MFA login. Everyone else —
        # including admins with MFA, who chain OTP then TOTP on verify —
        # gets an email OTP first and a short-lived grant to exchange it.
        if user.mfa_enabled and user.role in (
            UserRole.STUDENT.value,
            UserRole.PROFESSOR.value,
        ):
            return TokenResponse(
                mfa_pending=True,
                preauth_token=create_preauth_token(user.id, self._settings),
                must_change_password=user.must_change_password,
            )

        await self.request_otp(user.email, OtpPurpose.LOGIN)

        return TokenResponse(
            otp_pending=True,
            otp_token=create_login_otp_token(user.id, user.email, self._settings),
            must_change_password=user.must_change_password,
        )

    async def verify_login_otp(
        self, otp_token: str, code: str, client_ip: str | None = None
    ) -> TokenResponse:
        """Exchange a login-OTP grant plus the emailed code for the session.

        The grant proves the password gate was passed; the code proves inbox
        access. Admins with MFA enabled get a preauth challenge back instead
        of tokens (OTP then TOTP); everyone else gets tokens directly.

        Two failure-only caps, each counting wrong codes alone:

        - per email (`423 login_otp_locked`): 3 guesses against the current
          code inside the OTP TTL. A resend mints a fresh code and resets
          this budget, so a lock can never outlive the credential it
          protects by more than 1x.
        - per IP (`429 rate_limited`, reused code): 15 misses inside the same
          window. Resends do NOT reset this one — that is what stops a client
          from dodging the email cap by rotating addresses. Successes and
          expired codes never touch either budget.

        No audit row is recorded here: like the recovery flow, a failure
        raises, and `_get_db` would roll the row back with it.
        """

        user: User = await self._user_from_login_otp_grant(otp_token)
        normalized: str = user.email.lower()
        limiter_key: str = f"login_otp|{normalized}"
        # Mirrors the router's own `ip or "unknown"` fallback: a missing
        # client pools unknowns, which can only ever happen off the wire.
        ip_key: str = f"login_otp_ip|{client_ip or 'unknown'}"
        window_seconds: int = self._settings.otp_expires_minutes * 60

        if await _login_otp_limiter.exhausted(
            limiter_key,
            LOGIN_OTP_MAX_ATTEMPTS,
            window_seconds,
        ):
            raise LoginOtpLockedException(self._settings.otp_expires_minutes)

        if await _login_otp_ip_limiter.exhausted(
            ip_key,
            LOGIN_OTP_IP_MAX_ATTEMPTS,
            window_seconds,
        ):
            retry_after: int = await _login_otp_ip_limiter.retry_after_seconds(ip_key)
            if retry_after <= 0:
                retry_after = window_seconds
            raise RateLimitedException(retry_after)

        try:
            await self.verify_otp(normalized, code, OtpPurpose.LOGIN)
        except OtpExpiredException:
            raise
        except OtpMaxAttemptsException:
            await _login_otp_limiter.hit(
                limiter_key,
                LOGIN_OTP_MAX_ATTEMPTS,
                window_seconds,
            )
            await _login_otp_ip_limiter.hit(
                ip_key,
                LOGIN_OTP_IP_MAX_ATTEMPTS,
                window_seconds,
            )
            raise
        except OtpInvalidException:
            await _login_otp_limiter.hit(
                limiter_key,
                LOGIN_OTP_MAX_ATTEMPTS,
                window_seconds,
            )
            await _login_otp_ip_limiter.hit(
                ip_key,
                LOGIN_OTP_IP_MAX_ATTEMPTS,
                window_seconds,
            )
            raise

        if user.mfa_enabled:
            return TokenResponse(
                mfa_pending=True,
                preauth_token=create_preauth_token(user.id, self._settings),
                must_change_password=user.must_change_password,
            )

        return self._build_tokens(user)

    async def resend_login_otp(self, otp_token: str) -> None:
        """Mint a fresh LOGIN OTP for the grant holder (burns the previous).

        Flood control lives at the router (`5/60s`); the grant itself is the
        per-account gate, so no service counter is needed here. The fresh code
        resets the email's wrong-code budget: guesses spent against the burned
        code are guesses against a dead credential. The per-IP budget is
        deliberately NOT reset — a resend loop is exactly what it exists to
        catch.
        """

        user: User = await self._user_from_login_otp_grant(otp_token)
        await self.request_otp(user.email, OtpPurpose.LOGIN)
        await _login_otp_limiter.reset(f"login_otp|{user.email.lower()}")

    async def _user_from_login_otp_grant(self, otp_token: str) -> User:
        """Resolve the grant to its live account, or fail non-probeably.

        A bad, expired, or wrong-typed grant and a missing/inactive account
        all report generic invalid-credentials, mirroring `_assert_recovery_grant`
        and the preauth branch of `verify_mfa`.
        """

        payload: dict[str, Any] | None = decode_access_token(
            otp_token, self._settings
        )

        if payload is None or payload.get("type") != LOGIN_OTP_TOKEN_TYPE:
            raise InvalidCredentialsException()

        user: User | None = await self._users.get(extract_user_id(payload))

        if (
            user is None
            or not user.is_active
            or user.email.lower() != str(payload.get("email", "")).lower()
        ):
            raise InvalidCredentialsException()

        return user

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
    ) -> TokenResponse:
        """Consume a FORGET_PASSWORD OTP and set the new password — then sign in.

        Step 4 of recovery returns the session directly instead of a 204, so a
        user who just proved inbox access (single-use OTP) plus the security
        answer does not have to prove the same inbox again through login+OTP.
        Anyone who can complete recovery could complete a login anyway, so the
        extra round is friction, not security. `must_change_password` is False:
        this is a user-chosen password, not an admin-issued temp.

        MFA is not skipped: an account with MFA enabled gets the preauth
        challenge back (same shape as `login`), and the caller finishes with
        TOTP. Mirrors `doRegister`'s contract on the frontend.
        """

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

        if user.mfa_enabled:
            return TokenResponse(
                mfa_pending=True,
                preauth_token=create_preauth_token(user.id, self._settings),
            )

        return self._build_tokens(user)

    async def start_password_recovery(self, user: User) -> PasswordRecoveryStartResponse:
        """Issue a recovery grant and OTP for the authenticated user's email.

        The recipient is derived from the session, never from client input, so
        an authenticated user can only ever recover their own account. The OTP
        is minted through the same ``request_otp`` path as the public flow.
        """

        normalized: str = user.email.lower()
        recovery_token: str = create_recovery_token(user.id, normalized, self._settings)

        await self.request_otp(
            normalized, OtpPurpose.FORGET_PASSWORD, recovery_token
        )

        return PasswordRecoveryStartResponse(
            recovery_token=recovery_token,
            masked_email=_mask_email(normalized),
        )

    async def reset_password_authenticated(
        self, user: User, otp_code: str, new_password: str
    ) -> TokenResponse:
        """Reset the authenticated user's password, keyed off their session email."""

        return await self.reset_password(user.email, otp_code, new_password)

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        security_question: str | None = None,
        security_answer: str | None = None,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise CurrentPasswordInvalid()

        if verify_password(new_password, user.password_hash):
            raise PasswordReusedException()

        user.password_hash = hash_password(new_password)
        user.must_change_password = False

        if security_question is not None or security_answer is not None:
            if not security_question or not security_answer:
                raise PasswordPolicyException(field="security_question")
            user.security_question_hash = security_question
            user.security_answer_hash = hash_password(
                self._normalize_answer(security_answer)
            )

        await self._session.flush()

    async def admin_reset_password(
        self,
        *,
        user_id: int,
        actor_id: int,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> str:
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

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_manage_target(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        old_value: dict[str, Any] = _account_snapshot(user)

        temp_password: str = secrets.token_urlsafe(TEMP_PASSWORD_LENGTH)

        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None
        user.lockout_level = 0
        user.last_lockout_at = None
        user.lockout_override_until = None

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

    async def get_lockout_status(
        self,
        user_id: int,
        *,
        actor_id: int | None = None,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> dict[str, Any]:
        user: User | None = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundException()

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_read_lockout(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        hide = hide_sensitive_fields(
            resolved_actor_role, UserRole(user.role), actor_id=actor_id, target_id=user.id
        )

        now: datetime = datetime.now(timezone.utc)
        is_permanent: bool = (user.lockout_level or 0) > _escalation_table_len(
            self._settings
        )
        if is_permanent:
            duration_minutes: int = 0
            locked_until = None
        else:
            duration_minutes: int = _escalation_minutes(
                self._settings, user.lockout_level or 1
            )
            locked_until: datetime | None = None
            if user.is_locked and user.locked_at is not None:
                locked_until = user.locked_at + timedelta(minutes=duration_minutes)

        remaining_minutes: int | None = None
        if locked_until is not None and now < locked_until:
            remaining_minutes = int((locked_until - now).total_seconds() // 60) + 1
            if remaining_minutes < 1:
                remaining_minutes = 1

        override_remaining: int | None = None
        if user.lockout_override_until is not None and now < user.lockout_override_until:
            override_remaining = int(
                (user.lockout_override_until - now).total_seconds() // 60
            ) + 1
            if override_remaining < 1:
                override_remaining = 1

        return {
            "user_id": user.id,
            "email": None if hide else user.email,
            "role": user.role,
            "is_locked": user.is_locked,
            "is_permanently_locked": is_permanent,
            "locked_at": user.locked_at.isoformat() if user.locked_at else None,
            "lockout_level": user.lockout_level or 0,
            "lockout_duration_minutes": duration_minutes,
            "locked_until": locked_until.isoformat() if locked_until else None,
            "remaining_minutes": remaining_minutes,
            "last_lockout_at": user.last_lockout_at.isoformat()
            if user.last_lockout_at
            else None,
            "override_until": user.lockout_override_until.isoformat()
            if user.lockout_override_until
            else None,
            "override_remaining_minutes": override_remaining,
        }

    async def release_lockout(
        self,
        *,
        user_id: int,
        actor_id: int,
        reason: str,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> None:
        user: User | None = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundException()

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_mutate_lockout(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        old_value: dict[str, Any] = _account_snapshot(user)
        user.is_locked = False
        user.locked_at = None
        user.failed_login_attempts = 0
        user.lockout_level = 0
        user.last_lockout_at = None

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UNLOCK,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value={**_account_snapshot(user), "reason": reason},
        )
        # store reason in audit via a separate field? record_audit signature?
        await self._session.flush()

    async def reset_violation_counter(
        self,
        *,
        user_id: int,
        actor_id: int,
        reason: str,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> None:
        user: User | None = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundException()

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_mutate_lockout(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        old_value: dict[str, Any] = _account_snapshot(user)
        user.lockout_level = 0
        user.last_lockout_at = None

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value={**_account_snapshot(user), "reason": reason},
        )
        await self._session.flush()

    async def grant_override(
        self,
        *,
        user_id: int,
        actor_id: int,
        duration_minutes: int,
        reason: str,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> None:
        if duration_minutes < 1 or duration_minutes > self._settings.lockout_override_max_minutes:
            raise InvalidOverrideDurationException(self._settings.lockout_override_max_minutes)

        user: User | None = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundException()

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_mutate_lockout(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        now: datetime = datetime.now(timezone.utc)
        old_value: dict[str, Any] = _account_snapshot(user)
        user.lockout_override_until = now + timedelta(minutes=duration_minutes)

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value={**_account_snapshot(user), "reason": reason},
        )
        await self._session.flush()

    async def revoke_override(
        self,
        *,
        user_id: int,
        actor_id: int,
        reason: str,
        viewer_role: UserRole | str | None = None,
        actor_role: UserRole | str | None = None,
    ) -> None:
        user: User | None = await self._users.get(user_id)
        if user is None:
            raise UserNotFoundException()

        resolved_actor_role = await self._resolve_actor_role(
            actor_id=actor_id, viewer_role=viewer_role, actor_role=actor_role
        )
        if not can_mutate_lockout(resolved_actor_role, UserRole(user.role)):
            raise ForbiddenException()

        old_value: dict[str, Any] = _account_snapshot(user)
        user.lockout_override_until = None

        await record_audit(
            self._session,
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=AuditEntity.USER,
            entity_id=user.id,
            old_value=old_value,
            new_value={**_account_snapshot(user), "reason": reason},
        )
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
