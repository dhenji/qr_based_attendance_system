"""Pool discovery for the load harness.

`discover_session_pool` lives in `bench_timings` (not `locustfile`)
deliberately: importing locust pulls in gevent monkey-patching, which breaks
the async suite when it happens inside the pytest process.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bench_timings import SlotAssigner, discover_session_pool, poisson_wait


def test_wait_accepts_user_and_returns_positive() -> None:
    """Locust calls `user.wait_time()` bound: a zero-arg wait crashes every VU."""

    wait = poisson_wait(2.5)
    assert isinstance(wait(object()), float)
    assert wait(object()) > 0


def test_explicit_session_ids_skip_discovery() -> None:
    assert discover_session_pool(prefix="X-", dsn="unused", explicit="7, 8,9") == [
        7,
        8,
        9,
    ]


def test_discovery_probe_compiles_and_parses_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="11 12 13\n", stderr=""
        )

    import bench_timings

    monkeypatch.setattr(bench_timings.subprocess, "run", fake_run)

    assert discover_session_pool(prefix="SEED-LOAD-", dsn="postgresql://db") == [
        11,
        12,
        13,
    ]

    import ast

    script = captured["argv"][2]
    ast.parse(script)
    assert "ORDER BY id" in script


def test_discovery_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv, returncode=1, stdout="", stderr="boom"
        )

    import bench_timings

    monkeypatch.setattr(bench_timings.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="boom"):
        discover_session_pool(prefix="SEED-LOAD-", dsn="postgresql://db")


def test_locust_user_has_default_host() -> None:
    import re

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    source = open(os.path.join(root, "locustfile.py")).read()
    assert re.search(r'host = "http://127\.0\.0\.1:8000"', source)


def test_locustfile_asserts_the_documented_targets() -> None:
    """The five targets must stay enforced, not merely printed.

    Source-level because importing `locustfile` monkey-patches gevent and
    hangs the suite, so the report function cannot be called from here.
    """

    root = os.path.join(os.path.dirname(__file__), "..", "..")
    source = open(os.path.join(root, "locustfile.py")).read()

    for knob, default in (
        ("LOCUST_MIN_RPS", "10"),
        ("LOCUST_MAX_P95_MS", "1000"),
        ("LOCUST_MAX_P99_MS", "2000"),
        ("LOCUST_MAX_DRAIN_S", "60"),
        ("LOCUST_QUEUE_STALE_S", "90"),
    ):
        assert f'{knob}", "{default}"' in source, knob

    for target in (
        "scan throughput",
        "response time p95",
        "response time p99",
        "duplicate rejections",
        "queue drain",
    ):
        assert target in source, target

    # A missed target has to reach the shell, so it must set the exit code
    # rather than only printing. `None` must stay possible: leaving it unset
    # is what lets locust still fail the run on a recorded request failure.
    assert "environment.process_exit_code = 1" in source

    # Replays carry their own idempotency keys: a reused key returns the prior
    # result instead of queueing, which would make the drain leg vacuous.
    assert "uuid.uuid4().hex" in source


def test_slot_assigner_deals_unique_slots_then_wraps() -> None:
    assigner = SlotAssigner(30)
    assert sorted(assigner.assign() for _ in range(30)) == list(range(1, 31))
    assert assigner.assign() == 1
