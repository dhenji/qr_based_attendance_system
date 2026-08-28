import jwt

from core.config import Settings


def decode_access_token(token: str, settings: Settings) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=settings.jwt_algorithm)


def extract_user_id(payload: dict) -> int:
    if "sub" not in payload:
        raise jwt.InvalidTokenError("Missing subject claim")

    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("Invalid subject claim")
