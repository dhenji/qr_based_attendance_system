def password_strength(value: str) -> str:
    # security-model.md:102 - min n chars, mixed case + number
    if not any(c.isupper() for c in value):
        raise ValueError("password must contain an uppercase letter")
    if not any(c.islower() for c in value):
        raise ValueError("password must contain a lowercase letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("password must contain a number")

    return value
