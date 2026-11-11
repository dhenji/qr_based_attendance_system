from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import argon2
import jwt

from core.config import Settings, get_settings

REFRESH_TOKEN_TYPE: str = "refresh"
PREAUTH_TOKEN_TYPE: str = "preauth"
RECOVERY_TOKEN_TYPE: str = "recovery"
LOGIN_OTP_TOKEN_TYPE: str = "login_otp"

_hasher = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (argon2.exceptions.VerificationError, argon2.exceptions.InvalidHash):
        return False


def create_preauth_token(user_id: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": PREAUTH_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.preauth_token_expire_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: int,
    role: str,
    settings: Settings | None = None,
    token_version: int = 0,
) -> str:
    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: int,
    settings: Settings | None = None,
    token_version: int = 0,
) -> str:
    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(
    token: str, settings: Settings | None = None
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=settings.jwt_algorithm)
    except jwt.PyJWTError:
        return None


def create_recovery_token(
    user_id: int, email: str, settings: Settings | None = None
) -> str:
    """Short-lived proof that the security-answer gate was passed (ADR-052).

    Issued by forgot-password step 2 and required before a FORGET_PASSWORD OTP
    can be minted. Because it carries a `type` claim it is rejected outright by
    the access-token dependency, so it can never be replayed for API access.
    """

    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email.lower(),
        "type": RECOVERY_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.recovery_token_expire_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_recovery_token(
    token: str, settings: Settings | None = None
) -> dict[str, Any] | None:
    """Return the recovery payload, or None if absent/expired/not a grant."""

    settings = settings or get_settings()

    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=settings.jwt_algorithm
        )
    except jwt.PyJWTError:
        return None

    if payload.get("type") != RECOVERY_TOKEN_TYPE:
        return None

    return payload


def create_login_otp_token(
    user_id: int, email: str, settings: Settings | None = None
) -> str:
    """Short-lived proof that the password gate was passed for login OTP.

    Issued by `login` after the password (and lockout) checks and required to
    verify or resend the LOGIN OTP. Reuses the preauth expiry: both are
    login-flow grants with the same 5-minute semantics, so one knob covers
    both. Carries a `type` claim, so like every other grant it is rejected
    outright by the access-token dependency and can never buy API access.
    """

    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email.lower(),
        "type": LOGIN_OTP_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.preauth_token_expire_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def extract_user_id(payload: dict) -> int:
    if "sub" not in payload:
        raise jwt.InvalidTokenError("Missing subject claim")

    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("Invalid subject claim")


# Otp utilities
def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


# Hashing same logics
def hash_otp(otp: str) -> str:
    return hash_password(otp)


def verify_otp(plain: str, hashed: str) -> bool:
    return verify_password(plain, hashed)


# Backup-code utilities
def generate_backup_code() -> str:
    raw: bytes = secrets.token_bytes(7)
    return base64.b32encode(raw).decode("ascii").rstrip("=")[:10]


def normalize_backup_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def backup_code_fingerprint(
    normalized_code: str, settings: Settings | None = None
) -> str:
    """Keyed digest of an already-normalized backup code.

    Used only as an index lookup key so verify_backup_code can find the single
    candidate row before paying for one Argon2id verify; it is not a substitute
    for the Argon2id code_hash. HMAC_SECRET_KEY is preferred, falling back to
    JWT_SECRET (always set when DEBUG=false) since the former is unused elsewhere.
    """

    current: Settings = settings or get_settings()
    secret: str = current.hmac_secret_key or current.jwt_secret

    if not secret:
        raise ValueError(
            "HMAC_SECRET_KEY or JWT_SECRET must be set to fingerprint backup codes"
        )

    return hmac.new(
        secret.encode("utf-8"), normalized_code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


_BASE62_ALPHABET: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
SESSION_CODE_LENGTH: int = 8


def _resolve_hmac_secret(settings: Settings | None = None) -> str:
    current: Settings = settings or get_settings()
    secret: str = current.hmac_secret_key or current.jwt_secret

    if not secret:
        raise ValueError(
            "HMAC_SECRET_KEY or JWT_SECRET must be set to generate session codes"
        )

    return secret


def generate_session_code(session_id: int, settings: Settings | None = None) -> str:
    secret: str = _resolve_hmac_secret(settings)
    digest: bytes = hmac.new(
        secret.encode("utf-8"), str(session_id).encode("utf-8"), hashlib.sha256
    ).digest()

    return "".join(_BASE62_ALPHABET[b % 62] for b in digest[:SESSION_CODE_LENGTH])


def verify_session_code(
    code: str, session_id: int, settings: Settings | None = None
) -> bool:
    return hmac.compare_digest(code, generate_session_code(session_id, settings))


def build_qr_payload(
    session_id: int,
    code: str,
    offering_id: int,
    radius: int,
    present_window: int,
    late_window: int,
) -> str:
    # session_id is the HMAC input for the code; the payload identifies the
    # session by code per the Session QR Payload contract.
    _ = session_id
    payload: dict[str, int | str] = {
        "v": 1,
        "code": code,
        "offering": offering_id,
        "radius": radius,
        "pw": present_window,
        "lw": late_window,
    }

    return json.dumps(payload, separators=(",", ":"))
