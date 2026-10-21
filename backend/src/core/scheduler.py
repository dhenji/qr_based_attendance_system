"""Cron scheduling for the nightly background jobs.

The app lifespan owns one `AsyncIOScheduler` and registers a small, fixed set
of jobs on it: the nightly risk batch and the nightly full backup. Both bodies
live in the feature that owns the work; this module only owns *when* they run.

Two things live here that are worth reading before changing anything:

**In-flight tracking.** `_IN_FLIGHT` records the `asyncio.Task` behind each
running job, so `scheduled_job_running()` answers "is the scheduler busy right
now" for the admin maintenance endpoints, which refuse to run concurrently with
a backup or a risk batch. It is deliberately narrower than
`features.system.service.is_backup_running()`, which also reports a *manually*
triggered backup from `POST /admin/backups`; the maintenance guard composes the
two rather than one shadowing the other.

**Process-local, single instance.** Both `_IN_FLIGHT` and the backup lock in
`features/system/service.py` are per-process, like the scan idempotency store
and the rate limiter. Running more than one worker process would fire every job
once per process. A shared store or a Postgres advisory lock is the fix, and it
is not in place.

This module imports nothing from `features` or `shared`: the layering is
stdlib, third-party, `core`, `shared`, `features`, and the job bodies are
injected by the caller (`main.py`) rather than imported here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import tzinfo
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import Settings, get_settings
from core.timezones import resolve_timezone as resolve_zone

logger = logging.getLogger(__name__)

# Job names. Spelled once so a job, its logs and the maintenance guard's
# callers cannot drift apart.
JOB_BACKUP = "backup"
JOB_RISK_BATCH = "risk_batch"

# How long teardown waits for a cancelled job to unwind before giving up on it.
# Shutdown must not hang on a wedged `pg_dump`, and it must not return before
# the task has released its connection, so the bound is generous but finite.
SHUTDOWN_DRAIN_SECONDS = 30.0

JobBody = Callable[[], Awaitable[Any]]

_IN_FLIGHT: dict[str, set[asyncio.Task[Any]]] = {}


def resolve_timezone(name: str) -> tzinfo:
    """ZoneInfo for `name`, falling back to UTC when it cannot be resolved.

    A slim container image may ship without the tz database, and a cron that
    never fires is a silent data-loss bug. An unknown zone is therefore a
    warning, not a boot failure: the job still runs, on UTC.

    The rule itself lives in `core.timezones` so the session-plan resolver can
    share it without importing APScheduler (D93).
    """
    return resolve_zone(name, label="scheduler timezone")


@asynccontextmanager
async def track(name: str) -> AsyncIterator[None]:
    """Record the calling task as the in-flight run of job `name`.

    Removal happens in a `finally`, so a job that raises is no longer reported
    as running. Only the tasks started here are tracked, so a manual backup
    triggered over HTTP is invisible to `scheduled_job_running` by design.
    """
    task = asyncio.current_task()
    if task is None:  # pragma: no cover - only reachable off-loop
        yield
        return

    _IN_FLIGHT.setdefault(name, set()).add(task)
    try:
        yield
    finally:
        holders = _IN_FLIGHT.get(name)
        if holders is not None:
            holders.discard(task)
            if not holders:
                _IN_FLIGHT.pop(name, None)


def scheduled_job_running(name: str | None = None) -> bool:
    """Whether a scheduled job is in flight, optionally narrowed to `name`."""
    if name is not None:
        return bool(_IN_FLIGHT.get(name))
    return any(_IN_FLIGHT.values())


def in_flight_jobs() -> dict[str, int]:
    """Snapshot of running job names to concurrent run counts, for logging."""
    return {name: len(tasks) for name, tasks in _IN_FLIGHT.items() if tasks}


async def drain_in_flight(
    timeout: float = SHUTDOWN_DRAIN_SECONDS,
) -> set[asyncio.Task[Any]]:
    """Cancel every tracked job task and wait, bounded, for them to unwind.

    Returns the tasks that were still pending when the timeout expired. Callers
    dispose the database right after this, so anything left here is about to
    lose its connection and fail; that is the correct trade against hanging the
    process on a wedged subprocess.

    The calling task is never a candidate. A job body is always its own task, so
    in production this only excludes the lifespan task - but `track()` accepts
    whatever task enters it, and cancelling the caller mid-drain would take the
    process down during shutdown instead of the job.
    """
    caller = asyncio.current_task()
    pending = {
        task
        for tasks in _IN_FLIGHT.values()
        for task in tasks
        if task is not caller
    }
    if not pending:
        return set()

    names = in_flight_jobs()
    logger.info("Cancelling in-flight scheduler jobs: %s", names)
    for task in pending:
        task.cancel()

    done, still_pending = await asyncio.wait(pending, timeout=timeout)
    for task in done:
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Scheduler job raised during shutdown: %s",
                task.exception(),
                exc_info=task.exception(),
            )
    if still_pending:
        logger.error(
            "Scheduler jobs did not finish within %.0fs: %d task(s) abandoned",
            timeout,
            len(still_pending),
        )
    return still_pending


class BackgroundScheduler:
    """Lifespan-scoped wrapper around one `AsyncIOScheduler`.

    `start` and `shutdown` are idempotent. That is the guard against
    double-instantiation: `uvicorn --reload` tears the process down and rebuilds
    it on every file save, a lifespan may be entered twice in a test, and a
    second `add_job` with `replace_existing=True` would otherwise leave a stale
    trigger behind. Every job is registered with `max_instances=1`, so a slow
    run is skipped rather than stacked, and `coalesce=True`, so a backlog of
    missed fires collapses into one.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._timezone = resolve_timezone(self._settings.scheduler_timezone)
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def job_ids(self) -> list[str]:
        """Registered job ids, in registration order."""
        if self._scheduler is None:
            return []
        return [job.id for job in self._scheduler.get_jobs()]

    def register(self, name: str, cron: str, func: JobBody) -> None:
        """Schedule `func` on `cron`, a five-field crontab expression.

        The trigger is built here rather than handed to `add_job` as a string
        so a malformed expression raises during startup, while an operator is
        watching the boot log, instead of silently never firing at 02:00.

        Registering a name twice replaces it. `replace_existing=True` alone is
        not enough for that: while the scheduler is stopped, APScheduler keeps
        pending jobs in a *list* and appends to it unconditionally, so a second
        `register()` before `start()` would leave two triggers behind and the
        job would fire twice. Dropping the previous one first covers both the
        stopped and the running case.
        """
        trigger = CronTrigger.from_crontab(cron, timezone=self._timezone)
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(timezone=self._timezone)

        self.remove(name)
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=name,
            name=name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self._settings.scheduler_misfire_grace_seconds,
        )
        logger.info(
            "Scheduled job %r on cron %r (%s)",
            name,
            cron,
            self._settings.scheduler_timezone,
        )

    def start(self) -> None:
        if self.running:
            logger.debug("Scheduler already running; start() is a no-op")
            return
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler(timezone=self._timezone)

        self._scheduler.start()
        logger.info(
            "Background scheduler started with job(s): %s",
            ", ".join(self.job_ids()) or "none",
        )

    async def shutdown(self) -> None:
        """Stop accepting fires, then cancel whatever is still running.

        `wait=False` keeps teardown from blocking on a long backup; the explicit
        drain is what makes the ordering safe, since the caller disposes the
        database immediately afterwards.
        """
        scheduler = self._scheduler
        if scheduler is not None and scheduler.running:
            logger.info("Stopping background scheduler")
            scheduler.shutdown(wait=False)
        self._scheduler = None

        await drain_in_flight()

    def remove(self, name: str) -> bool:
        """Drop one registered job; False when there was nothing to drop."""
        if self._scheduler is None:
            return False
        try:
            self._scheduler.remove_job(name)
        except JobLookupError:
            return False
        return True


_SCHEDULER = BackgroundScheduler()


def get_scheduler() -> BackgroundScheduler:
    """The process-wide scheduler instance the lifespan drives."""
    return _SCHEDULER


def reset_scheduler() -> None:
    """Force the scheduler back to a never-started state, synchronously.

    The test suite's reset fixture is sync and cannot await `shutdown()`: by
    teardown the loop it was bound to is already closing, so there is nothing
    left to await on. Any executor is therefore stopped with `wait=False` and
    the instance is emptied in place rather than replaced, so a caller that
    already holds the singleton keeps a valid one. In-flight bookkeeping is
    dropped outright - those tasks died with their loop, and leaving them
    registered would make `scheduled_job_running()` lie to the next test.
    """
    stale = _SCHEDULER._scheduler
    if stale is not None:
        try:
            stale.shutdown(wait=False)
        except Exception:  # noqa: BLE001 - teardown is best-effort by design
            logger.debug("Ignoring scheduler teardown error", exc_info=True)
    _SCHEDULER._scheduler = None
    _IN_FLIGHT.clear()
