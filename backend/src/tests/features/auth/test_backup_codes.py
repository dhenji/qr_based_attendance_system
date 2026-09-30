from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.security import (
    backup_code_fingerprint,
    create_preauth_token,
    hash_password,
    normalize_backup_code,
)
from features.auth.exceptions import MfaVerifyException
from features.auth.service import AuthService


def _settings() -> Settings:
    return Settings(
        debug=True,
        jwt_secret="test-jwt-secret-for-unit-tests-000000",
    )


def _user(**kwargs):
    defaults = dict(
        id=1,
        role="student",
        email="u@example.com",
        is_active=True,
        mfa_enabled=True,
        mfa_secret="JBSWY3DPEB2XS2LP",
        must_change_password=False,
    )

    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _code_record(code, used_at=None, created_at=None):
    """Build a MfaBackupCodes row from the PLAINTEXT code.

    Both stored columns are derived the same way the service derives them, so a
    test can hand in the human-facing code ("ABCDE-FGHIJ" or "ABCDEFGHIJ") and
    have the fake session resolve it by fingerprint.
    """

    normalized = normalize_backup_code(code)

    return SimpleNamespace(
        code_hash=hash_password(normalized),
        used_at=used_at,
        created_at=created_at or datetime.now(timezone.utc),
        code_fingerprint=backup_code_fingerprint(normalized, _settings()),
    )


def _fingerprint_filter(stmt):
    """Pull the code_fingerprint equality value back out of a select statement.

    Lets the fake session emulate the indexed single-row lookup that
    verify_backup_code relies on, so these tests still assert the lookup path
    rather than just the Argon2id comparison.
    """

    for clause in getattr(stmt.whereclause, "clauses", []):
        left = getattr(clause, "left", None)

        if left is not None and str(left) == "mfa_backup_codes.code_fingerprint":
            return clause.right.value

    return None


class _FakeSession:
    def __init__(self, rows, user=None):
        self._rows = rows
        self._user = user
        self.scalar_calls = 0

    async def scalars(self, stmt):
        return SimpleNamespace(all=lambda: self._rows)

    async def scalar(self, stmt):
        self.scalar_calls += 1
        wanted = _fingerprint_filter(stmt)

        if wanted is None:
            return self._rows[0] if self._rows else None

        for row in self._rows:
            if row.code_fingerprint == wanted and row.used_at is None:
                return row

        return None

    async def get(self, entity, ident):
        return self._user

    async def flush(self):
        pass

    def add(self, obj):
        pass


def _service(rows, user=None):
    return AuthService(_FakeSession(rows, user), _settings())


def test_generate_backup_codes_returns_10_and_invalidates_stale() -> None:
    stale = [_code_record("AAAAAGGGGG")]

    service = _service(stale)

    result = asyncio.run(service.generate_backup_codes(_user()))

    assert len(result.codes) == 10
    assert result.remaining == 10
    assert stale[0].used_at is not None


def test_generate_codes_have_grouped_dashes() -> None:
    result = asyncio.run(_service([]).generate_backup_codes(_user()))
    assert all(code[4] == "-" and code[9] == "-" for code in result.codes)


def test_list_backup_codes_summary_latest_batch() -> None:
    created = datetime.now(timezone.utc)

    rows = [
        _code_record("AAAAAGGGGG", used_at=None, created_at=created) for _ in range(4)
    ] + [
        _code_record("CCCCCCTTTTT", used_at=created, created_at=created)
        for _ in range(6)
    ]

    summary = asyncio.run(_service(rows).list_backup_codes(_user()))

    assert summary.total == 10
    assert summary.remaining == 4
    assert summary.last_generated_at == created


def test_list_backup_codes_empty() -> None:
    summary = asyncio.run(_service([]).list_backup_codes(_user()))
    assert summary.total == 0
    assert summary.remaining == 0
    assert summary.last_generated_at is None


def test_verify_backup_code_accepts_hyphenated_input_and_marks_used() -> None:
    record = _code_record("ABCDEFGHIJ")
    service = _service([record])

    assert asyncio.run(service.verify_backup_code(_user(), "ABCDE-FGHIJ")) is True
    assert record.used_at is not None


def test_verify_backup_code_rejects_unknown_or_wrong_length() -> None:
    record = _code_record("ABCDEFGHIJ")
    service = _service([record])

    assert asyncio.run(service.verify_backup_code(_user(), "ZZZZZZZZZZ")) is False
    assert asyncio.run(service.verify_backup_code(_user(), "SHORT")) is False


def test_verify_backup_code_resolves_via_single_indexed_lookup() -> None:
    """Item 7: one indexed fingerprint lookup, not 10 sequential Argon2 verifies."""

    rows = [_code_record(f"CODE{index:06d}") for index in range(10)]
    session = _FakeSession(rows)
    service = AuthService(session, _settings())

    assert asyncio.run(service.verify_backup_code(_user(), "CODE000000")) is True
    assert session.scalar_calls == 1

    # An unknown code must short-circuit at the lookup, never reach Argon2id.
    session = _FakeSession(rows)
    service = AuthService(session, _settings())

    assert asyncio.run(service.verify_backup_code(_user(), "NOPE000000")) is False
    assert session.scalar_calls == 1


def test_verify_backup_code_ignores_already_used_codes() -> None:
    used = datetime.now(timezone.utc)
    record = _code_record("ABCDEFGHIJ", used_at=used)
    service = _service([record])

    assert asyncio.run(service.verify_backup_code(_user(), "ABCDE-FGHIJ")) is False


def test_verify_mfa_falls_back_to_backup_code() -> None:
    record = _code_record("ABCDEFGHIJ")
    service = _service([record])

    tokens = asyncio.run(service.verify_mfa("ABCDE-FGHIJ", user=_user()))

    assert tokens.access_token is not None
    assert record.used_at is not None


def test_verify_mfa_accepts_backup_code_via_preauth() -> None:
    record = _code_record("ABCDEFGHIJ")
    service = _service([record], _user())

    tokens = asyncio.run(
        service.verify_mfa(
            "ABCDE-FGHIJ",
            preauth_token=create_preauth_token(1, _settings()),
        )
    )

    assert tokens.access_token is not None
    assert record.used_at is not None


def test_verify_mfa_rejects_when_no_match() -> None:
    service = _service([])

    with pytest.raises(MfaVerifyException):
        asyncio.run(service.verify_mfa("000000", user=_user()))
