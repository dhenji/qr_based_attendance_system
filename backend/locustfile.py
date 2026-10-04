"""Concurrent-scan load test: 30 virtual students, one active session.

Provisioning (once)::

    cd backend && python test_seed_data.py --scale small
    # API with the load profile (lifts the single-IP rate gate and the
    # geofence/liveness checks so the run measures routing + persistence):
    BENCHMARK_MODE=true FACE_MATCH_THRESHOLD=0.0 uvicorn main:app --app-dir src
    export LOCUST_SESSION_ID=$(psql $DATABASE_URL -tAc \
        "SELECT id FROM sessions WHERE session_code='SEED-GE101-BSCS-00'")

Run (5-minute Poisson window)::

    cd backend && .venv/bin/locust -f locustfile.py \
        --headless -u 30 -r 6 --run-time 5m --csv load_run

Tuning: ``LOCUST_MEAN_WAIT_S`` (default 2.5, ~12 req/s across 30 users),
``LOCUST_POOL_SIZE`` (default 30, matches the ``loadtestNN`` seed accounts),
``LOCUST_PASSWORD`` (default ``Loadtest1!``).

Bandwidth shaping is out of scope for the harness: apply ``tc`` (or a proxy
cap) on the load host to emulate 3G when that leg matters.

Targets: >=10 req/s, p95 <1s, p99 <2s, zero spurious duplicate rejections.
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, events, task

MEAN_WAIT_S = float(os.environ.get("LOCUST_MEAN_WAIT_S", "2.5"))
POOL_SIZE = int(os.environ.get("LOCUST_POOL_SIZE", "30"))
PASSWORD = os.environ.get("LOCUST_PASSWORD", "Loadtest1!")
SESSION_ID = int(os.environ.get("LOCUST_SESSION_ID", "0"))

_failures: dict[str, int] = {"duplicate": 0, "rate_limited": 0, "error": 0}


def _wait() -> float:
    return random.expovariate(1.0 / MEAN_WAIT_S)


class ScanningStudent(HttpUser):
    wait_time = _wait  # type: ignore[assignment]

    def on_start(self) -> None:
        if not SESSION_ID:
            raise RuntimeError(
                "LOCUST_SESSION_ID is required: seed first, then export the id "
                "of session SEED-GE101-BSCS-00"
            )
        slot = (id(self) % POOL_SIZE) + 1
        self.username = f"loadtest{slot:02d}"
        with self.client.post(
            "/api/auth/login",
            json={"email": f"{self.username}@load.test", "password": PASSWORD},
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login {response.status_code}")
                raise RuntimeError(f"login failed for {self.username}")
            token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        with self.client.get(
            "/api/student/profile", headers=self.headers, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"profile {response.status_code}")
                raise RuntimeError(f"profile failed for {self.username}")
            body = response.json()
            self.student_number = body["student_number"] or body["student_id"]

    @task
    def scan(self) -> None:
        payload = {
            "session_id": SESSION_ID,
            "student_number": self.student_number,
            "gps": {"lat": 14.5995, "lng": 121.0001, "accuracy": 5.0},
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
            response.failure(f"scan {response.status_code} {code}")


@events.test_stop.add_listener
def _report(environment, **kwargs) -> None:
    stats = environment.stats.total
    print(
        "\nload summary: "
        f"requests={stats.num_requests} "
        f"rps={stats.total_rps:.1f} "
        f"p95={stats.get_current_response_time_percentile(0.95) or 0:.0f}ms "
        f"p99={stats.get_current_response_time_percentile(0.99) or 0:.0f}ms "
        f"failures={_failures}"
    )
    if _failures["duplicate"]:
        print("FAIL: spurious duplicate rejections observed")
