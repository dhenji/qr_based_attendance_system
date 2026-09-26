import asyncio
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.security import (
    PREAUTH_TOKEN_TYPE,
    RECOVERY_TOKEN_TYPE,
    create_recovery_token,
    decode_access_token,
    decode_recovery_token,
    hash_password,
)
from features.auth.constants import SECURITY_QUESTION_POOL
from features.auth.exceptions import (
    RecoveryGrantRequiredException,
    SecurityAnswerInvalidException,
)
from features.auth.service import AuthService, _decoy_question
from shared.enums import OtpPurpose

QUESTION = "What was the name of your first pet?"


def _settings(minutes: int = 5) -> Settings:
    return Settings(
        debug=True,
        jwt_secret="test-jwt-secret-for-unit-tests-000000",
        recovery_token_expire_minutes=minutes,
    )


def _user(**kwargs):
    defaults = dict(
        id=7,
        role="student",
        email="u@example.com",
        is_active=True,
        mfa_enabled=False,
        must_change_password=False,
        security_question_hash=QUESTION,
        security_answer_hash=hash_password("bluebell"),
    )

    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class _Result:
    """Mimics the ScalarResult surface AuthService actually touches."""

    def __init__(self, value):
        self._value = value

    def one_or_none(self):
        return self._value

    def first(self):
        return self._value

    def all(self):
        return [] if self._value is None else [self._value]


class _FakeSession:
    def __init__(self, user):
        self._user = user
        self.added = []

    async def scalars(self, stmt):
        return _Result(self._user)

    async def scalar(self, stmt):
        return None

    async def get(self, entity, ident):
        return self._user

    async def flush(self):
        pass

    def add(self, obj):
        self.added.append(obj)


def _service(user):
    return AuthService(_FakeSession(user), _settings())


# --- item 5: step 1 must not reveal whether an email is registered -----------


def test_step1_returns_stored_question_for_known_email() -> None:
    result = asyncio.run(_service(_user()).forgot_password("u@example.com"))

    assert result.question == QUESTION
    assert result.set is True


def test_step1_returns_pooled_decoy_for_unknown_email() -> None:
    result = asyncio.run(_service(None).forgot_password("nobody@example.com"))

    assert result.question in SECURITY_QUESTION_POOL
    assert result.set is True


def test_step1_response_shape_is_identical_known_vs_unknown() -> None:
    known = asyncio.run(_service(_user()).forgot_password("u@example.com"))
    unknown = asyncio.run(_service(None).forgot_password("nobody@example.com"))

    assert type(known) is type(unknown)
    assert known.set == unknown.set
    assert known.question is not None and unknown.question is not None


def test_decoy_is_stable_per_email() -> None:
    settings = _settings()

    first = _decoy_question("nobody@example.com", settings)
    second = _decoy_question("nobody@example.com", settings)
    assert first == second


def test_decoy_varies_across_emails() -> None:
    settings = _settings()
    picks = {
        _decoy_question(f"user{index}@example.com", settings)
        for index in range(len(SECURITY_QUESTION_POOL) * 2)
    }

    # A constant decoy would be fine; what must never happen is a RANDOM one,
    # which would become its own enumeration oracle across repeated requests.
    assert len(picks) > 1


def test_decoy_never_echoes_the_address() -> None:
    result = _decoy_question("victim@example.com", _settings())

    assert "victim" not in result
    assert "example.com" not in result


# --- item 2: step 2 issues a grant that gates step 3 ------------------------


def test_step2_returns_grant_on_correct_answer() -> None:
    result = asyncio.run(
        _service(_user()).forgot_password_step2("u@example.com", "bluebell")
    )

    payload = decode_recovery_token(result.recovery_token, _settings())
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["email"] == "u@example.com"
    assert payload["type"] == RECOVERY_TOKEN_TYPE


def test_step2_answer_is_case_and_space_insensitive() -> None:
    result = asyncio.run(
        _service(_user()).forgot_password_step2("u@example.com", "  BlueBell ")
    )

    assert result.recovery_token is not None


def test_step2_rejects_wrong_answer() -> None:
    with pytest.raises(SecurityAnswerInvalidException):
        asyncio.run(
            _service(_user()).forgot_password_step2("u@example.com", "wrong")
        )


def test_step2_rejects_unknown_email_with_identical_error() -> None:
    with pytest.raises(SecurityAnswerInvalidException):
        asyncio.run(
            _service(None).forgot_password_step2("nobody@example.com", "bluebell")
        )


# --- item 2: the gate itself -------------------------------------------------


def test_forget_password_otp_requires_a_grant() -> None:
    with pytest.raises(RecoveryGrantRequiredException):
        asyncio.run(
            _service(_user()).request_otp(
                "u@example.com", OtpPurpose.FORGET_PASSWORD, None
            )
        )


def test_forget_password_otp_rejects_grant_for_another_email() -> None:
    other = create_recovery_token(7, "someone.else@example.com", _settings())

    with pytest.raises(RecoveryGrantRequiredException):
        asyncio.run(
            _service(_user()).request_otp(
                "u@example.com", OtpPurpose.FORGET_PASSWORD, other
            )
        )


def test_forget_password_otp_rejects_garbage_grant() -> None:
    with pytest.raises(RecoveryGrantRequiredException):
        asyncio.run(
            _service(_user()).request_otp(
                "u@example.com", OtpPurpose.FORGET_PASSWORD, "not-a-jwt"
            )
        )


def test_forget_password_otp_rejects_expired_grant() -> None:
    expired = create_recovery_token(7, "u@example.com", _settings(0))
    service = _service(_user())

    with pytest.raises(RecoveryGrantRequiredException):
        service._assert_recovery_grant("u@example.com", expired)


def test_valid_grant_passes_the_gate() -> None:
    grant = create_recovery_token(7, "u@example.com", _settings())
    service = _service(_user())

    service._assert_recovery_grant("u@example.com", grant)


def test_claim_otp_needs_no_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    # The gate must only apply to the recovery purpose.
    sent: list[str] = []
    monkeypatch.setattr(
        "features.auth.service.send_otp_email",
        lambda to, code, *a, **kw: sent.append(code),
    )

    asyncio.run(
        _service(_user()).request_otp("u@example.com", OtpPurpose.CLAIM, None)
    )

    assert len(sent) == 1


def test_grant_error_is_indistinguishable_from_bad_credentials() -> None:
    assert RecoveryGrantRequiredException().code == "invalid_credentials"
    assert RecoveryGrantRequiredException().message == "Invalid email or password"


def test_grant_cannot_be_replayed_as_an_access_token() -> None:
    # api/deps.py rejects any token carrying a `type` claim; assert the grant has
    # one so the MFA preauth token pattern cannot be replayed for API access.
    grant = create_recovery_token(7, "u@example.com", _settings())
    payload = decode_access_token(grant, _settings())

    assert payload is not None
    assert payload.get("type") == RECOVERY_TOKEN_TYPE
    assert payload.get("role") is None


def test_preauth_token_is_not_accepted_as_a_grant() -> None:
    from core.security import create_preauth_token

    preauth = create_preauth_token(7, _settings())
    service = _service(_user())

    with pytest.raises(RecoveryGrantRequiredException):
        service._assert_recovery_grant("u@example.com", preauth)


def test_expired_grant_is_rejected_by_decoder() -> None:
    assert decode_recovery_token(create_recovery_token(7, "a@b.c", _settings(-1)), _settings()) is None


def test_recovery_token_type_is_distinct() -> None:
    assert RECOVERY_TOKEN_TYPE not in (PREAUTH_TOKEN_TYPE, "refresh")
