"""Unit cover for `shared/rate_limit.py`: the client-IP resolution behind
proxies, and that the `rate_limit` dependency buckets on the resolved IP.

`client_ip()` is a pure function of (request, settings), so every case below
builds both explicitly — no assertion depends on `get_settings()` reading the
developer's `.env`. The one dependency-level test patches the module's own
`get_settings` reference, the same pattern as `tests/shared/test_email.py`.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from core.config import Settings

from shared import rate_limit as rate_limit_module
from shared.rate_limit import RateLimitedException, client_ip, rate_limit


def _settings(**kwargs) -> Settings:
    defaults = dict(debug=True, jwt_secret="test-jwt-secret-for-unit-tests-000000")
    defaults.update(kwargs)
    return Settings(**defaults)


def _request(client_host: str | None, xff: str | None = None) -> Request:
    scope: dict = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/api/auth/login/verify",
        "query_string": b"",
        "headers": [],
    }
    if client_host is not None:
        scope["client"] = (client_host, 50000)
    if xff is not None:
        scope["headers"] = [(b"x-forwarded-for", xff.encode("latin-1"))]
    return Request(scope)


# --- client_ip: default (nothing trusted) ------------------------------------


def test_direct_peer_without_config() -> None:
    assert client_ip(_request("203.0.113.7"), _settings()) == "203.0.113.7"


def test_spoofed_header_ignored_without_config() -> None:
    # The whole point of default-deny: a client-supplied header must never
    # pick the bucket unless the peer is a configured proxy.
    request = _request("203.0.113.7", "198.51.100.9")
    assert client_ip(request, _settings()) == "203.0.113.7"


def test_missing_client_is_none() -> None:
    assert client_ip(_request(None), _settings()) is None


# --- client_ip: trusted proxy -------------------------------------------------


def test_trusted_peer_uses_leftmost_forwarded() -> None:
    request = _request("10.0.0.1", "198.51.100.9, 10.0.0.1")
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    assert client_ip(request, settings) == "198.51.100.9"


def test_trusted_peer_without_header_falls_back_to_peer() -> None:
    request = _request("10.0.0.1")
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    assert client_ip(request, settings) == "10.0.0.1"


def test_untrusted_peer_header_ignored() -> None:
    request = _request("203.0.113.7", "198.51.100.9")
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    assert client_ip(request, settings) == "203.0.113.7"


def test_malformed_cidr_fails_closed_to_peer() -> None:
    request = _request("10.0.0.1", "198.51.100.9")
    settings = _settings(trusted_proxy_cidrs="not-a-cidr")
    assert client_ip(request, settings) == "10.0.0.1"


def test_malformed_forwarded_falls_back_to_peer() -> None:
    request = _request("10.0.0.1", "garbage")
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    assert client_ip(request, settings) == "10.0.0.1"


def test_malformed_peer_fails_closed() -> None:
    request = _request("not-an-ip", "198.51.100.9")
    settings = _settings(trusted_proxy_cidrs="0.0.0.0/0")
    assert client_ip(request, settings) == "not-an-ip"


# --- dependency buckets on the resolved IP ------------------------------------


async def test_dependency_splits_buckets_per_forwarded_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: settings)

    gate = rate_limit(1, 60, key="ip")

    # Same balancer peer, two different clients behind it: separate buckets.
    await gate(_request("10.0.0.1", "198.51.100.9"))
    await gate(_request("10.0.0.1", "198.51.100.10"))

    # Same client again: the 1-call budget is spent.
    with pytest.raises(RateLimitedException):
        await gate(_request("10.0.0.1", "198.51.100.9"))


async def test_dependency_ignores_spoofed_header_from_untrusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(trusted_proxy_cidrs="10.0.0.0/8")
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: settings)

    gate = rate_limit(1, 60, key="ip")

    await gate(_request("203.0.113.7", "198.51.100.9"))

    # Same peer, different forged header: still the peer's bucket.
    with pytest.raises(RateLimitedException):
        await gate(_request("203.0.113.7", "198.51.100.99"))


# --- release() refunds a single hit ------------------------------------------


async def test_release_refunds_a_single_hit() -> None:
    # Use a fresh limiter to avoid cross-test state.
    from shared.rate_limit import FixedWindowLimiter

    lim = FixedWindowLimiter()
    assert await lim.hit("k", 5, 60) is True
    assert await lim.hit("k", 5, 60) is True
    await lim.release("k")
    # One hit refunded: budget still has room.
    assert await lim.hit("k", 5, 60) is True
    for _ in range(3):
        assert await lim.hit("k", 5, 60) is True
    assert await lim.hit("k", 5, 60) is False


async def test_release_on_missing_or_expired_bucket_is_noop() -> None:
    from shared.rate_limit import FixedWindowLimiter

    lim = FixedWindowLimiter()
    await lim.release("missing")  # must not raise
    assert await lim.hit("k", 5, 60) is True
    await lim.release("k")
    # Bucket dropped; a fresh hit starts a new window.
    assert await lim.hit("k", 5, 60) is True
