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
