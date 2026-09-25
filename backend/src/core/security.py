import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import argon2
import jwt

from core.config import Settings, get_settings

REFRESH_TOKEN_TYPE: str = "refresh"
PREAUTH_TOKEN_TYPE: str = "preauth"

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
    user_id: int, role: str, settings: Settings | None = None
) -> str:
    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now: datetime = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
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
