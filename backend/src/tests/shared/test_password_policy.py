from __future__ import annotations

import pytest

from shared.validators import password_strength

# security-model.md:102 / wireframes.md:1909 / test-plan.md:289 (SH-AU-8):
# minimum 8 characters with at least 1 uppercase, 1 lowercase, 1 number and 1 symbol.
VALID = "Str0ng!Pass"


def test_accepts_password_meeting_full_policy() -> None:
    assert password_strength(VALID) == VALID


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("str0ng!pass", "uppercase"),
        ("STR0NG!PASS", "lowercase"),
        ("Strong!Pass", "number"),
        ("Str0ngPassw", "symbol"),
    ],
)
def test_rejects_each_missing_requirement(value: str, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        password_strength(value)


def test_whitespace_does_not_count_as_a_symbol() -> None:
    # A space must not satisfy the symbol rule, otherwise "Str0ng Pass " passes
    # on whitespace alone.
    with pytest.raises(ValueError, match="symbol"):
        password_strength("Str0ng Pass")


def test_punctuation_and_symbols_are_accepted() -> None:
    for symbol in ("!", "@", "#", "$", "-", "_", "="):
        assert password_strength(f"Str0ng{symbol}Pass") == f"Str0ng{symbol}Pass"


def test_length_is_not_checked_here() -> None:
    # Length is enforced by Field(min_length=PASSWORD_MIN_LENGTH) on the schemas,
    # so password_strength only owns the character-class rules.
    assert password_strength("Aa1!") == "Aa1!"
