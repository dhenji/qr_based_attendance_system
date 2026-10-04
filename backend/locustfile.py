"""Concurrent-scan load test: 30 virtual students over a pool of sessions.

A single session admits one successful scan per student (repeats are
`duplicate_scan` rejections), so the run cycles a pool of fresh sessions:
each virtual user is pinned 1:1 to a `loadtestNN` account and walks the
pool in slot order, keeping every (student, session) pair unique until the
full 30 x N matrix is exhausted.

Provisioning (once)::

    cd backend && python test_seed_data.py --scale small --load-fixtures 150
    # API with the load profile (lifts the single-IP rate gate and the
    # geofence/liveness checks so the run measures routing + persistence):
    BENCHMARK_MODE=true FACE_MATCH_THRESHOLD=0.0 uvicorn main:app --app-dir src

Run (5-minute Poisson window)::

    cd backend && .venv/bin/locust -f locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 30 -r 6 --run-time 5m --csv load_run

Tuning: ``LOCUST_MEAN_WAIT_S`` (default 2.5, ~12 req/s across 30 users),
``LOCUST_POOL_SIZE`` (default 30, matches the ``loadtestNN`` seed accounts),
``LOCUST_PASSWORD`` (default ``Loadtest1!``),
``LOCUST_SESSION_CODE_PREFIX`` (default ``SEED-LOAD-``),
``LOCUST_SESSION_IDS`` (comma list, skips pool discovery),
``DATABASE_URL`` (pool discovery only).

Re-baselining the targets: ``LOCUST_MIN_RPS`` (default 10),
``LOCUST_MAX_P95_MS`` (1000), ``LOCUST_MAX_P99_MS`` (2000). The gate is a
real assertion - a run that misses any target exits non-zero, so it can gate
CI. It only ever forces failure: a clean run leaves the exit code to locust,
which still fails on any recorded request failure.

Pool discovery shells out to a clean interpreter (no gevent) running one
``SELECT id ... ORDER BY id`` over asyncpg, so the load process itself never
touches the database driver under monkey-patched sockets.

Bandwidth shaping is out of scope for the harness: apply ``tc`` (or a proxy
cap) on the load host to emulate 3G when that leg matters.

Targets: >=10 req/s, p95 <1s, p99 <2s, zero spurious duplicate rejections.
All four are asserted at the end of the run; missing any one exits non-zero.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone

from locust import HttpUser, events, task

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bench_timings import SlotAssigner
from bench_timings import discover_session_pool as _discover, poisson_wait

MEAN_WAIT_S = float(os.environ.get("LOCUST_MEAN_WAIT_S", "2.5"))
POOL_SIZE = int(os.environ.get("LOCUST_POOL_SIZE", "30"))
PASSWORD = os.environ.get("LOCUST_PASSWORD", "Loadtest1!")
# Must be a deliverable domain: the login contract validates with EmailStr,
# which rejects reserved TLDs such as `.test`.
EMAIL_DOMAIN = os.environ.get("LOCUST_EMAIL_DOMAIN", "load.uni.edu")
SESSION_CODE_PREFIX = os.environ.get("LOCUST_SESSION_CODE_PREFIX", "SEED-LOAD-")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys",
)

MIN_RPS = float(os.environ.get("LOCUST_MIN_RPS", "10"))
MAX_P95_MS = float(os.environ.get("LOCUST_MAX_P95_MS", "1000"))
MAX_P99_MS = float(os.environ.get("LOCUST_MAX_P99_MS", "2000"))

SESSION_IDS: list[int] = []

# Single-process runs (`--headless` without `--master`) share this counter,
# so slots 1..POOL_SIZE are unique per user. Distributed workers would each
# restart at 1 — shard POOL_SIZE/LOCUST_SESSION_IDS per worker instead.
_assigner = SlotAssigner(POOL_SIZE)

_failures: dict[str, int] = {"duplicate": 0, "rate_limited": 0, "error": 0}
_counters: dict[str, int] = {"scans_ok": 0}


def discover_session_pool() -> list[int]:
    """Pool ids from env: explicit list wins, else prefix lookup."""

    return _discover(
        prefix=SESSION_CODE_PREFIX,
        dsn=DATABASE_URL.replace("+asyncpg", ""),
        explicit=os.environ.get("LOCUST_SESSION_IDS", ""),
    )


@events.test_start.add_listener
def _load_session_pool(environment, **kwargs) -> None:
    ids = discover_session_pool()
    if not ids:
        raise RuntimeError(
            f"no sessions with prefix {SESSION_CODE_PREFIX!r}: "
            "seed with --load-fixtures first"
        )
    SESSION_IDS.extend(ids)
    print(f"load pool: {len(SESSION_IDS)} sessions from id {SESSION_IDS[0]}")


LOGIN_ATTEMPTS = 8


def _describe(response: object) -> str:
    """One-line status + body for a failed response, whatever failed."""

    status = getattr(response, "status_code", "?")
    if status == 0:
        return "0 (no response — is the API up?)"
    try:
        text = response.text  # type: ignore[union-attr]
    except Exception:
        return str(status)
    return f"{status} {text[:160]}"


class ScanningStudent(HttpUser):
    host = "http://127.0.0.1:8000"
    wait_time = poisson_wait(MEAN_WAIT_S)

    def on_start(self) -> None:
        if not SESSION_IDS:
            raise RuntimeError("session pool is empty")
        self.slot = _assigner.assign()
        self.username = f"loadtest{self.slot:02d}"
        self.scans = 0
        token = self._login_with_retry()
        self.headers = {"Authorization": f"Bearer {token}"}
        with self.client.get(
            "/api/student/profile", headers=self.headers, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"profile {_describe(response)}")
                raise RuntimeError(f"profile failed for {self.username}")
            body = response.json()
            self.student_number = body["student_number"] or body["student_id"]

    def _login_with_retry(self) -> str:
        # The login limiters stay enforced in the load profile (20/min per
        # IP), so the 30-user spawn wave absorbs 429s with backoff instead of
        # failing: throttled attempts are not the run's measured traffic.
        last = "never attempted"
        for attempt in range(1, LOGIN_ATTEMPTS + 1):
            with self.client.post(
                "/api/auth/login",
                json={"email": f"{self.username}@{EMAIL_DOMAIN}",
                      "password": PASSWORD},
                catch_response=True,
            ) as response:
                if response.status_code == 200:
                    response.success()
                    token = response.json()["access_token"]
                    if not token:
                        raise RuntimeError(
                            f"login returned no token for {self.username}"
                        )
                    return token
                last = _describe(response)
                if response.status_code == 429 and attempt < LOGIN_ATTEMPTS:
                    response.success()
                    time.sleep(min(15 * attempt, 60))
                    continue
                response.failure(f"login {last}")
        raise RuntimeError(f"login failed for {self.username}: {last}")

    @task
    def scan(self) -> None:
        session_id = SESSION_IDS[(self.slot + self.scans) % len(SESSION_IDS)]
        self.scans += 1
        payload = {
            "session_id": session_id,
            "student_number": self.student_number,
            # Seeded classroom of the SEED-LOAD-* sessions (Room 301):
            # a scan elsewhere is a genuine outside_geofence rejection.
            "gps": {"lat": 14.5995, "lng": 120.9842, "accuracy": 5.0},
            "liveness_evidence": {
                "blink_detected": True,
                "head_turn_left": True,
                "head_turn_right": True,
                "ear_samples": [0.20, 0.21, 0.19],
                "pnp_evidence": {"depth_mean": 0.4},
            },
            "face_match_score": 0.92,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "scanned_via": "qr_camera",
        }
        headers = {
            **self.headers,
            "X-Idempotency-Key": uuid.uuid4().hex,
        }
        with self.client.post(
            "/api/student/attendance/scan",
            json=payload,
            headers=headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                _counters["scans_ok"] += 1
                response.success()
                return
            try:
                code = response.json().get("detail", {}).get("code", "")
            except ValueError:
                code = ""
            if code == "duplicate_scan":
                _failures["duplicate"] += 1
            elif response.status_code == 429:
                _failures["rate_limited"] += 1
            else:
                _failures["error"] += 1
            response.failure(f"scan {_describe(response)} code={code}")


def _window_seconds(stats) -> float:
    """Wall-clock seconds over which the run actually issued requests.

    ``stats.total_time`` is the sum of response times, so it is not a
    denominator; ``total_rps`` uses these two timestamps instead.
    """

    if not stats.start_time or not stats.last_request_timestamp:
        return 0.0
    return max(stats.last_request_timestamp - stats.start_time, 0.0)


def _percentile(stats, fraction: float) -> float | None:
    """Percentile in ms, preferring the trailing window over the whole run.

    ``get_current_response_time_percentile`` reads a 10-second rolling cache
    and returns ``None`` when that window holds no samples — a short run, or
    one that just idled. Falling back to the lifetime percentile keeps the
    target meaningful; when even that has nothing to report the caller gets
    ``None`` and must treat the target as unmet rather than as a pass.
    """

    current = stats.get_current_response_time_percentile(fraction)
    if current is not None:
        return float(current)
    lifetime = stats.get_response_time_percentile(fraction)
    return float(lifetime) if lifetime is not None else None


def _describe_ms(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.0f}ms"


@events.test_stop.add_listener
def _report(environment, **kwargs) -> None:
    stats = environment.stats.total
    window_s = _window_seconds(stats)
    if stats.num_requests == 0 or window_s <= 0:
        print(
            "\nload summary: "
            f"requests={stats.num_requests} scans_ok={_counters['scans_ok']} "
            f"window={window_s:.0f}s failures={_failures}"
        )
        print("FAIL: no requests recorded — the run measured nothing")
        environment.process_exit_code = 1
        return
    scans_ok = _counters["scans_ok"]
    scan_rps = scans_ok / window_s
    p95 = _percentile(stats, 0.95)
    p99 = _percentile(stats, 0.99)
    print(
        "\nload summary: "
        f"requests={stats.num_requests} "
        f"scans_ok={scans_ok} "
        f"window={window_s:.0f}s "
        f"scan_rps={scan_rps:.1f} "
        f"blended_rps={stats.total_rps:.1f} "
        f"p95={_describe_ms(p95)} "
        f"p99={_describe_ms(p99)} "
        f"failures={_failures}"
    )
    targets = (
        (
            "scan throughput",
            f">={MIN_RPS:g} req/s",
            f"{scan_rps:.1f} req/s",
            scan_rps >= MIN_RPS,
        ),
        (
            "response time p95",
            f"<{MAX_P95_MS:g}ms",
            _describe_ms(p95),
            p95 is not None and p95 < MAX_P95_MS,
        ),
        (
            "response time p99",
            f"<{MAX_P99_MS:g}ms",
            _describe_ms(p99),
            p99 is not None and p99 < MAX_P99_MS,
        ),
        (
            "duplicate rejections",
            "0",
            str(_failures["duplicate"]),
            not _failures["duplicate"],
        ),
    )
    missed = 0
    for name, target, actual, met in targets:
        verdict = "PASS" if met else "FAIL"
        print(f"  {verdict}  {name:<20} target {target:<14} actual {actual}")
        missed += not met
    if missed:
        print(f"FAIL: {missed} target(s) missed")
        environment.process_exit_code = 1
    else:
        print("PASS: all targets met")
