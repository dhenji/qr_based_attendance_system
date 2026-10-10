"""The user-defined `username` handle contract.

Email is the login identity; `username` is a display handle the user picks
at self-registration. These pin the hardening:

- `normalize_username` strips + lowercases and rejects anything outside
  `[a-z0-9._-]` (length stays a `Field(min/max_length)` concern).
- `RegisterRequest` (required) and `AdminUserCreate` (optional) normalize
  through it, so `Foo.Bar ` and `foo.bar` are the same handle.
- Roster creates (`StudentCreate` / `ProfessorCreate`) take no `username`
  at all — a stray key from an old client is ignored, never stored.

Pure schema/validator checks, so these run as plain sync tests with no
database, like `test_shared_rates.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from features.admin.schema import AdminUserCreate
from features.auth.schema import RegisterRequest
from features.professor.schema import ProfessorCreate
from features.student.schema import StudentCreate
from shared.enums import UserRole
from shared.validators import normalize_username


def test_normalize_username_strips_and_lowercases() -> None:
    assert normalize_username("  Foo.Bar_Baz-9 ") == "foo.bar_baz-9"


@pytest.mark.parametrize(
    "bad", ["has space", "semi;colon", "bang!", "at@sign", "uniçode", "", "a/b"]
)
def test_normalize_username_rejects_outside_charset(bad: str) -> None:
    with pytest.raises(ValueError, match="username may only contain"):
        normalize_username(bad)


def _register_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": "new.holder@isu.edu.ph",
        "otp_code": "123456",
        "username": "  New.Holder_1 ",
        "password": "Aa1!aaaa",
        "security_question": "Pet?",
        "security_answer": "Cat",
    }
    payload.update(overrides)
    return payload


def test_register_request_normalizes_username() -> None:
    assert RegisterRequest(**_register_payload()).username == "new.holder_1"  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["has space", "bang!", "a/b", "x"])
def test_register_request_rejects_bad_username(bad: str) -> None:
    # "x" fails Field(min_length=3); the rest fail the charset rule.
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_payload(username=bad))


def test_admin_user_create_username_optional_but_normalized() -> None:
    base = {
        "email": "admin@isu.edu.ph",
        "role": UserRole.ADMIN,
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    assert AdminUserCreate(**base).username is None
    assert (
        AdminUserCreate(**base, username="  Ada.L_1 ").username == "ada.l_1"  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError):
        AdminUserCreate(**base, username="not ok!")


def test_student_create_ignores_stray_username() -> None:
    row = StudentCreate.model_validate(
        {
            "student_id": "2024-00001",
            "first_name": "Jose",
            "last_name": "Rizal",
            "email": "jose.rizal@isu.edu.ph",
            "program_id": 1,
            "year_level_id": 1,
            "username": "stray.handle",
        }
    )
    assert "username" not in row.model_dump()
    assert not hasattr(row, "username")


def test_professor_create_ignores_stray_username() -> None:
    row = ProfessorCreate.model_validate(
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada.lovelace@isu.edu.ph",
            "username": "stray.handle",
        }
    )
    assert "username" not in row.model_dump()
    assert not hasattr(row, "username")
