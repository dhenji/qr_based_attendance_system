from __future__ import annotations

import re


def password_strength(value: str) -> str:
    # security-model.md:102 - min 8 chars, mixed case + number + symbol.
    # Length is enforced separately via Field(min_length=PASSWORD_MIN_LENGTH).
    if not any(c.isupper() for c in value):
        raise ValueError("password must contain an uppercase letter")
    if not any(c.islower() for c in value):
        raise ValueError("password must contain a lowercase letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("password must contain a number")
    if not any(not c.isalnum() and not c.isspace() for c in value):
        raise ValueError("password must contain a symbol")

    return value


_USERNAME_RE: re.Pattern[str] = re.compile(r"^[a-z0-9._-]+$")


def normalize_username(value: str) -> str:
    """Normalize a user-defined handle: strip + lowercase, charset-guarded.

    Length is enforced separately via Field(min/max_length). Raises
    ValueError so Pydantic surfaces it as a 422.
    """
    normalized: str = value.strip().lower()
    if not _USERNAME_RE.match(normalized):
        raise ValueError(
            "username may only contain lowercase letters, numbers, dot, underscore and hyphen"
        )

    return normalized
