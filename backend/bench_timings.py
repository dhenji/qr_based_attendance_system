"""One-shot timings for the verification legs. Run from ``backend/``::

    .venv/bin/python bench_timings.py --batch --workers 1
    .venv/bin/python bench_timings.py --batch --workers 4
    .venv/bin/python bench_timings.py --backup

Uses ``DATABASE_URL`` (defaults to the dev database). The risk batch prints
its own summary dict including ``duration_ms``; the backup leg prints the
finished row's size, backend, and wall time. Both commit through their own
sessions, like the nightly crons do.

`discover_session_pool` is shared with ``locustfile.py``: it lives here
rather than there because importing locust pulls in gevent monkey-patching,
which must never happen inside the pytest process.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def _settings(**overrides):
    from core.config import get_settings

    return get_settings().model_copy(update=overrides)


def poisson_wait(mean_s: float) -> Callable[[object], float]:
    """Poisson-distributed wait for the load harness.

    Lives here rather than in `locustfile.py` so the suite can cover it:
    locust calls the class's `wait_time` as `user.wait_time()`, i.e. bound,
    so the callable MUST accept the user argument — a zero-arg function
    crashes every virtual user on its first wait.
    """

    def _wait(_user: object) -> float:
        return random.expovariate(1.0 / mean_s)

    return _wait


def discover_session_pool(
    *, prefix: str, dsn: str, explicit: str = ""
) -> list[int]:
    """Session ids for the load pool, oldest first.

    Explicit ``"1,2,3"`` wins; otherwise one indexed lookup by session-code
    prefix in a subprocess, keeping asyncpg out of the gevent-patched load
    process.
    """

    if explicit.strip():
        return [int(part) for part in explicit.split(",") if part.strip()]

    script = """\
import asyncio
import asyncpg
import os

QUERY = (
    "SELECT id FROM sessions "
    "WHERE session_code LIKE $1 || '%' "
    "ORDER BY id"
)

async def main():
    conn = await asyncpg.connect(os.environ["LOCUST_DSN"])
    try:
        rows = await conn.fetch(QUERY, os.environ["LOCUST_PREFIX"])
        print(" ".join(str(row["id"]) for row in rows))
    finally:
        await conn.close()

asyncio.run(main())
"""
    env = {**os.environ, "LOCUST_DSN": dsn, "LOCUST_PREFIX": prefix}
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"session pool discovery failed: {completed.stderr.strip()}"
        )
    return [int(part) for part in completed.stdout.split()]


@asynccontextmanager
async def _session():
    import os as _os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = _os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys",
    )
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session:
            yield session
    finally:
        await engine.dispose()


async def time_batch(workers: int) -> dict:
    from features.analytics.batch import run_risk_batch

    settings = _settings(risk_batch_workers=workers)
    async with _session() as session:
        started = time.perf_counter()
        summary = await run_risk_batch(session, settings=settings)
        wall_s = time.perf_counter() - started
        await session.commit()
    print(f"workers={workers} wall_s={wall_s:.1f} summary={summary}")
    return summary


async def time_backup() -> dict:
    from features.system.service import SystemService

    async with _session() as session:
        service = SystemService(session)
        started = time.perf_counter()
        row = await service.run_backup(kind="full")
        wall_s = time.perf_counter() - started
        await session.commit()
    result = {
        "backup_id": row.id,
        "size_bytes": row.size_bytes,
        "storage": row.storage_backend,
        "status": row.status,
        "wall_s": round(wall_s, 1),
    }
    print(result)
    return result


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Time batch/backup legs.")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.batch:
        asyncio.run(time_batch(args.workers))
    elif args.backup:
        asyncio.run(time_backup())
    else:
        parser.error("pass --batch or --backup")


if __name__ == "__main__":
    main()
