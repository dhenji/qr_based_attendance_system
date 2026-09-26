import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.config import Settings
from features.auth.service import AuthService
from shared.enums import OtpPurpose
from sqlalchemy.sql import operators

PURPOSE = OtpPurpose.CLAIM


def _settings() -> Settings:
    return Settings(debug=True, jwt_secret="test-jwt-secret-for-unit-tests-000000")


def _otp(**kwargs):
    defaults = dict(
        id=1,
        email="u@example.com",
        purpose=PURPOSE.value,
        otp_hash="hash",
        consumed_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class _FakeSession:
    def __init__(self, existing):
        self.existing = existing
        self.added = []

    async def scalars(self, stmt):
        rows = [row for row in self.existing if _matches(row, stmt)]
        return SimpleNamespace(
            all=lambda: rows,
            first=lambda: rows[0] if rows else None,
            one_or_none=lambda: rows[0] if rows else None,
        )

    async def flush(self):
        pass

    def add(self, obj):
        obj.id = len(self.added) + 1
        self.added.append(obj)


def _matches(row, stmt) -> bool:
    """Honour the equality / IS NULL filters _consume_active_otps applies.

    Without this the fake would "burn" rows the real WHERE clause excludes, which
    is exactly the behaviour the purpose-isolation test exists to catch.
    """

    for clause in getattr(stmt.whereclause, "clauses", []):
        left = getattr(clause, "left", None)
        right = getattr(clause, "right", None)

        if left is None or right is None:
            return False

        actual = getattr(row, left.key, None)

        if clause.operator is operators.is_ or (
            clause.operator is operators.eq and right.value is None
        ):
            if actual is not None:
                return False
        elif clause.operator is operators.eq:
            if actual != right.value:
                return False
        else:
            raise AssertionError(f"unsupported operator in fake: {clause.operator}")

    return True


def _service(existing, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(
        "features.auth.service.send_otp_email",
        lambda to, code, *a, **kw: sent.append(code),
    )
    session = _FakeSession(existing)
    return AuthService(session, _settings()), session, sent


def test_resend_burns_the_previous_unconsumed_code(monkeypatch) -> None:
    """Item 6: only the newest OTP may stay valid, so a resend cannot leave two."""

    stale = [_otp(id=1)]
    service, _, sent = _service(stale, monkeypatch)

    asyncio.run(service.request_otp("u@example.com", PURPOSE))

    assert stale[0].consumed_at is not None
    assert len(sent) == 1


def test_resend_does_not_touch_already_consumed_codes(monkeypatch) -> None:
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    consumed = [_otp(id=1, consumed_at=old)]
    service, _, _ = _service(consumed, monkeypatch)

    asyncio.run(service.request_otp("u@example.com", PURPOSE))

    assert consumed[0].consumed_at == old


def test_resend_only_affects_the_same_purpose(monkeypatch) -> None:
    claim = [_otp(id=1, purpose=OtpPurpose.CLAIM.value)]
    forget = [_otp(id=2, purpose=OtpPurpose.FORGET_PASSWORD.value)]
    service = AuthService(_FakeSession(claim + forget), _settings())
    monkeypatch.setattr("features.auth.service.send_otp_email", lambda *a, **kw: None)

    asyncio.run(service.request_otp("u@example.com", PURPOSE))

    assert claim[0].consumed_at is not None
    assert forget[0].consumed_at is None


def test_otp_row_is_normalised_to_lowercase_email(monkeypatch) -> None:
    service, session, _ = _service([], monkeypatch)

    asyncio.run(service.request_otp("Mixed.Case@Example.COM", PURPOSE))

    assert session.added[0].email == "mixed.case@example.com"


def test_new_otp_carries_a_five_minute_expiry(monkeypatch) -> None:
    before = datetime.now(timezone.utc)
    service, session, _ = _service([], monkeypatch)

    asyncio.run(service.request_otp("u@example.com", PURPOSE))

    expires_at = session.added[0].expires_at
    # The service captures its own `now` a hair after `before`, so allow a sliver.
    assert timedelta(minutes=4) < (expires_at - before) <= timedelta(minutes=5, seconds=1)
