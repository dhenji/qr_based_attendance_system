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

from bench_timings import discover_session_pool


def test_explicit_session_ids_skip_discovery() -> None:
    assert (
        discover_session_pool(prefix="X-", dsn="unused", explicit="7, 8,9")
        == [7, 8, 9]
    )


def test_discovery_probe_compiles_and_parses_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(
        argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="11 12 13\n", stderr=""
        )

    import bench_timings

    monkeypatch.setattr(bench_timings.subprocess, "run", fake_run)

    assert (
        discover_session_pool(prefix="SEED-LOAD-", dsn="postgresql://db")
        == [11, 12, 13]
    )

    import ast

    script = captured["argv"][2]
    ast.parse(script)
    assert "ORDER BY id" in script


def test_discovery_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
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
