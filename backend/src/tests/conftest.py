"""Shared pytest fixtures and sample-data factories.

Two storage backends, one interface. `TEST_DATABASE_URL` selects the backing
store; unset (the default) runs against in-memory SQLite, so the suite needs
no Postgres and no Docker. Point it at a real database to run the same tests
against the real dialect:

    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/attendance_test \\
        .venv/bin/python -m pytest src/tests

Two SQLite dialect shims are required by the models and are the only reason
this is not a three-line fixture. Both are registered for the `sqlite`
dialect only, so they are inert under `TEST_DATABASE_URL`:

- `JSONB` -> `JSON`: the Postgres JSONB type has no SQLite equivalent.
- `BigInteger` -> `INTEGER`: SQLite only auto-increments a column declared
  exactly `INTEGER PRIMARY KEY`. Every model declares its id as `BigInteger`,
  so without this the very first INSERT fails with
  `NOT NULL constraint failed: <table>.id`.

`PRAGMA foreign_keys=ON` is what makes `ondelete="RESTRICT"` real on SQLite.
SQLite parses those clauses but ignores them by default, which would let the
archive-guard tests pass against a database that is not enforcing anything.

Test functions are auto-detected as asyncio by `asyncio_mode = auto` in
pytest.ini. The pre-existing suite predates pytest-asyncio and drives
coroutines with `asyncio.run()` from synchronous test functions; auto mode
leaves those untouched, which is why both styles coexist here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import datetime, time, timedelta, timezone
from typing import Any

# Set before the first `core.config` import below: `Settings` validates
# `JWT_SECRET` at construction and `core.config` is imported at module scope
# by the very first feature import.
#
# Assigned rather than `setdefault`, so a stale short secret in the
# environment cannot leak in: `auth_headers` mints tokens with the
# `settings` fixture while `_get_current_user` verifies them with
# `api.deps.settings` built from this same variable, so the two must agree.
# It is also 32+ bytes, because PyJWT warns below that for HS256.
TEST_JWT_SECRET = "test-secret-0123456789abcdef-0123456789"
os.environ["DEBUG"] = "true"
os.environ["JWT_SECRET"] = TEST_JWT_SECRET

import pytest  # noqa: E402
from sqlalchemy import BigInteger, DateTime, event  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.dialects.sqlite.base import DATETIME as SQLiteDateTime  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from core.config import Settings  # noqa: E402
from core.database import Base  # noqa: E402
from features.attendance.model import Attendance  # noqa: E402
from features.auth.model import User  # noqa: E402
from features.course.model import Course, CourseOffering  # noqa: E402
from features.course_professor.model import CourseProfessor  # noqa: E402
from features.enrollment.model import Enrollment  # noqa: E402
from features.professor.model import Professor  # noqa: E402
from features.program.model import Program, YearLevel  # noqa: E402
from features.session.model import Session  # noqa: E402
from features.student.model import Student  # noqa: E402
from shared.enums import SyncStatus, UserRole, ValidationStatus  # noqa: E402

SQLITE_URL = "sqlite+aiosqlite:///:memory:"

DEFAULT_TERM_STRUCTURE: dict[str, Any] = {
    "terms": [
        {"code": "1ST_SEM", "label": "First Semester"},
        {"code": "2ND_SEM", "label": "Second Semester"},
    ]
}

# A counter, not a random suffix: the unique columns (`users.username`,
# `users.email`, `students.student_id`, `sessions.session_code`) collide
# across factories within a single test, and a deterministic sequence keeps
# failures reproducible.
_sequence: int = 0


def _next() -> int:
    global _sequence
    _sequence += 1
    return _sequence


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(
    type_: JSONB, compiler: Any, **kw: Any
) -> str:  # pragma: no cover - DDL shim
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(
    type_: BigInteger, compiler: Any, **kw: Any
) -> str:  # pragma: no cover - DDL shim
    return "INTEGER"


class UTCDateTime(SQLiteDateTime):
    """SQLite `DATETIME` that reads back as timezone-aware UTC.

    Postgres `now()` on a `timestamptz` column yields an aware datetime, and
    the services rely on that: `SessionService.create_session` computes
    `min(created_at + duration, scheduled_end_time)` where the second operand
    is built from `_utcnow()`. SQLite's `CURRENT_TIMESTAMP` yields a *naive*
    datetime, so that comparison raises `TypeError: can't compare
    offset-naive and offset-aware datetimes`.

    Applying the tzinfo on the way out rather than changing the stored value
    keeps the test database's semantics aligned with the production one. Only
    used on the SQLite path; the Postgres path is untouched.
    """

    def result_processor(
        self, dialect: Any, coltype: Any
    ) -> Callable[[bytes], datetime | None] | None:
        base = super().result_processor(dialect, coltype)

        if base is None:
            return None

        def process(value: bytes) -> datetime | None:
            parsed = base(value)

            if parsed is not None and parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)

            return parsed

        return process


def apply_utc_datetimes() -> None:
    """Swap every `DateTime` column's type for the aware variant.

    Done once at import, over the whole metadata, so a new model with a
    timestamp column is covered without editing this file.
    """

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime) and not isinstance(
                column.type, UTCDateTime
            ):
                column.type = UTCDateTime(timezone=column.type.timezone)


apply_utc_datetimes()


@pytest.fixture
def settings() -> Settings:
    """Settings with a valid secret; `Settings()` alone raises under DEBUG=false."""

    return Settings(debug=True, jwt_secret=TEST_JWT_SECRET)


@pytest.fixture
def now() -> datetime:
    """Frozen UTC clock anchor for time-sensitive assertions.

    The session fixtures and `test_db_session` use the wall clock, so tests
    that assert on expiry need a fixed `now` to anchor against rather than
    one that drifts between the fixture and the assertion.
    """

    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
async def test_engine() -> AsyncIterator[Any]:
    """Schema-per-test engine, SQLite by default.

    Fresh schema per test rather than one shared schema with truncated
    tables: SQLite in-memory has no `TRUNCATE ... RESTART IDENTITY`, and the
    alternative leaks rows from a failing test into the next one.
    """

    url: str = os.environ.get("TEST_DATABASE_URL") or SQLITE_URL
    engine = create_async_engine(url)

    if url.startswith("sqlite"):
        with_sqlite_foreign_keys(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


def with_sqlite_foreign_keys(engine: Any) -> None:
    """Turn on FK enforcement for one SQLite engine. No-op for other dialects."""

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture
async def test_db_session(test_engine: Any) -> AsyncIterator[AsyncSession]:
    """Session bound to `test_engine`, rolled back at teardown.

    The services under test only ever call `flush()`; commit stays in the
    request dependency. So the whole test is one uncommitted transaction and
    the rollback is what isolates it.
    """

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def _create(session: AsyncSession, model: type, **fields: Any) -> Any:
    row = model(**fields)
    session.add(row)
    await session.flush()
    return row


class Factories:
    """Sample-data factories bound to one session.

    Each method inserts and flushes, so the returned row has its generated id
    populated and can be used as a foreign key by the next factory call.
    Every keyword is a column override on top of a valid default, so a test
    only states the one field it cares about.
    """

    # Named `db`, not `session`: the factory method is `session()` and an
    # attribute of the same name would shadow it.
    def __init__(self, session: AsyncSession, now: datetime) -> None:
        self.db = session
        self.now = now
        # Per-program year-level counter, for the `uq_program_year_number`
        # unique constraint.
        self._year_levels_by_program: dict[int, int] = {}

    async def _make(self, model: type, **fields: Any) -> Any:
        return await _create(self.db, model, **fields)

    async def user(self, **overrides: Any) -> User:
        n = _next()
        return await self._make(
            User,
            username=overrides.pop("username", f"user{n}"),
            email=overrides.pop("email", f"user{n}@test.local"),
            password_hash=overrides.pop("password_hash", "not-a-real-hash"),
            role=overrides.pop("role", UserRole.STUDENT.value),
            **overrides,
        )

    async def program(self, **overrides: Any) -> Program:
        n = _next()
        return await self._make(
            Program,
            code=overrides.pop("code", f"PROG{n}"),
            name=overrides.pop("name", f"Program {n}"),
            description=overrides.pop("description", None),
            total_years=overrides.pop("total_years", 4),
            **overrides,
        )

    async def year_level(self, program: Program, **overrides: Any) -> YearLevel:
        # `year_levels` carries `uq_program_year_number`, so the default has
        # to advance per program or a second call in the same test collides.
        seen: int = self._year_levels_by_program.get(program.id, 0) + 1
        self._year_levels_by_program[program.id] = seen

        return await self._make(
            YearLevel,
            program_id=overrides.pop("program_id", program.id),
            year_number=overrides.pop("year_number", seen),
            label=overrides.pop("label", f"Year {seen}"),
            term_structure=overrides.pop("term_structure", DEFAULT_TERM_STRUCTURE),
            sort_order=overrides.pop("sort_order", seen),
            **overrides,
        )

    async def student(
        self, year_level: YearLevel, user: User | None = None, **overrides: Any
    ) -> Student:
        n = _next()
        return await self._make(
            Student,
            user_id=overrides.pop("user_id", user.id if user else None),
            student_id=overrides.pop("student_id", f"STU-{n:05d}"),
            email=overrides.pop("email", f"student{n}@test.local"),
            first_name=overrides.pop("first_name", "Test"),
            middle_name=overrides.pop("middle_name", None),
            last_name=overrides.pop("last_name", f"Student {n}"),
            year_level_id=overrides.pop("year_level_id", year_level.id),
            section=overrides.pop("section", "A1"),
            **overrides,
        )

    async def professor(self, user: User | None = None, **overrides: Any) -> Professor:
        n = _next()
        return await self._make(
            Professor,
            user_id=overrides.pop("user_id", user.id if user else None),
            email=overrides.pop("email", f"professor{n}@test.local"),
            first_name=overrides.pop("first_name", "Test"),
            middle_name=overrides.pop("middle_name", None),
            last_name=overrides.pop("last_name", f"Professor {n}"),
            department=overrides.pop("department", "Computer Science"),
            **overrides,
        )

    async def course(self, **overrides: Any) -> Course:
        n = _next()
        return await self._make(
            Course,
            course_code=overrides.pop("course_code", f"CS{n:03d}"),
            course_name=overrides.pop("course_name", f"Course {n}"),
            units=overrides.pop("units", 3),
            session_duration_hours=overrides.pop("session_duration_hours", 1.5),
            **overrides,
        )

    async def offering(
        self,
        course: Course,
        program: Program,
        year_level: YearLevel,
        **overrides: Any,
    ) -> CourseOffering:
        return await self._make(
            CourseOffering,
            course_id=overrides.pop("course_id", course.id),
            program_id=overrides.pop("program_id", program.id),
            year_level_id=overrides.pop("year_level_id", year_level.id),
            semester=overrides.pop("semester", "1ST_SEM"),
            academic_year=overrides.pop("academic_year", "2026-2027"),
            sessions_per_week=overrides.pop("sessions_per_week", 2),
            semester_weeks=overrides.pop("semester_weeks", 16),
            schedule_days=overrides.pop("schedule_days", "MWF"),
            schedule_start_time=overrides.pop("schedule_start_time", time(8, 0)),
            schedule_end_time=overrides.pop("schedule_end_time", time(9, 0)),
            **overrides,
        )

    async def session(
        self,
        offering: CourseOffering,
        professor: Professor,
        **overrides: Any,
    ) -> Session:
        n = _next()
        return await self._make(
            Session,
            offering_id=overrides.pop("offering_id", offering.id),
            professor_id=overrides.pop("professor_id", professor.id),
            session_code=overrides.pop("session_code", f"CODE{n:04d}XY"),
            duration_minutes=overrides.pop("duration_minutes", 60),
            present_window_minutes=overrides.pop("present_window_minutes", 5),
            late_window_minutes=overrides.pop("late_window_minutes", 10),
            scheduled_start_time=overrides.pop(
                "scheduled_start_time", self.now
            ),
            scheduled_end_time=overrides.pop(
                "scheduled_end_time", self.now + timedelta(minutes=60)
            ),
            expires_at=overrides.pop(
                "expires_at", self.now + timedelta(minutes=60)
            ),
            **overrides,
        )

    async def assignment(
        self,
        offering: CourseOffering,
        professor: Professor,
        assigned_by: User,
        **overrides: Any,
    ) -> CourseProfessor:
        """Effective-dated teaching assignment.

        `SessionService.create_session` requires one, so any test that opens
        a session through the service needs this rather than a bare professor.
        """

        return await self._make(
            CourseProfessor,
            offering_id=overrides.pop("offering_id", offering.id),
            professor_id=overrides.pop("professor_id", professor.id),
            effective_from=overrides.pop(
                "effective_from", self.now.date() - timedelta(days=30)
            ),
            effective_to=overrides.pop("effective_to", None),
            is_primary=overrides.pop("is_primary", True),
            semester=overrides.pop("semester", "1ST_SEM"),
            assigned_by=overrides.pop("assigned_by", assigned_by.id),
            **overrides,
        )

    async def enrollment(
        self, student: Student, offering: CourseOffering, **overrides: Any
    ) -> Enrollment:
        return await self._make(
            Enrollment,
            student_id=overrides.pop("student_id", student.id),
            offering_id=overrides.pop("offering_id", offering.id),
            semester=overrides.pop("semester", "1ST_SEM"),
            academic_year=overrides.pop("academic_year", "2026-2027"),
            **overrides,
        )

    async def attendance(
        self, student: Student, session: Session, **overrides: Any
    ) -> Attendance:
        return await self._make(
            Attendance,
            student_id=overrides.pop("student_id", student.id),
            session_id=overrides.pop("session_id", session.id),
            timestamp=overrides.pop("timestamp", self.now),
            gps_lat=overrides.pop("gps_lat", None),
            gps_lng=overrides.pop("gps_lng", None),
            validation_status=overrides.pop(
                "validation_status", ValidationStatus.PRESENT.value
            ),
            original_status=overrides.pop("original_status", None),
            sync_status=overrides.pop("sync_status", SyncStatus.SYNCED.value),
            liveness_evidence=overrides.pop("liveness_evidence", None),
            face_match_score=overrides.pop("face_match_score", None),
            scanned_via=overrides.pop("scanned_via", "qr_camera"),
            **overrides,
        )

    async def full_stack(self, **session_overrides: Any) -> dict[str, Any]:
        """program -> year_level -> student + professor -> course -> offering
        -> session, with the student enrolled.

        The dependency chain every scan needs. Returns a dict rather than a
        tuple so a test can address the parts it asserts on by name.

        The student is linked to a `users` row because the scan and precheck
        routes resolve the student from the *authenticated* account rather
        than from `payload.student_number`; a service-level test that wants to
        exercise those needs a `user_id` to pass. Created last so the id
        sequence every other factory draws from is unchanged by it.

        The session row is inserted directly rather than opened through
        `SessionService.create_session`, so `expires_at` and
        `scheduled_*` land exactly as the test states them. Tests that are
        about `create_session` itself should call it.
        """

        program: Program = await self.program()
        year_level: YearLevel = await self.year_level(program)
        student: Student = await self.student(year_level)
        professor: Professor = await self.professor()
        course: Course = await self.course()
        offering: CourseOffering = await self.offering(course, program, year_level)
        session: Session = await self.session(offering, professor, **session_overrides)
        enrollment: Enrollment = await self.enrollment(student, offering)
        user: User = await self.user(role=UserRole.STUDENT.value)

        student.user_id = user.id
        await self.db.flush()

        return {
            "program": program,
            "year_level": year_level,
            "student": student,
            "user": user,
            "professor": professor,
            "course": course,
            "offering": offering,
            "session": session,
            "enrollment": enrollment,
        }


@pytest.fixture
def factories(test_db_session: AsyncSession, now: datetime) -> Factories:
    return Factories(test_db_session, now)


@pytest.fixture
def db_factory(
    test_db_session: AsyncSession, now: datetime
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Insert-any-model shorthand: `await db_factory(Program, code="X", ...)`.

    Escape hatch for a model the typed factories do not cover yet. Prefer a
    named factory, so the defaults stay in one place.
    """

    async def _insert(model: type, **fields: Any) -> Any:
        return await _create(test_db_session, model, **fields)

    return _insert


@pytest.fixture
async def api_client(
    test_db_session: AsyncSession,
) -> AsyncIterator[Any]:
    """`httpx.AsyncClient` over the real ASGI app, wired to the test database.

    `ASGITransport` rather than `TestClient`: `TestClient` blocks on a
    thread portal and raises if called from inside a running event loop, so
    it is unusable from an async test. The sync `TestClient` is still
    available as `test_client` for the DB-free cases.

    `_get_db` is overridden to hand the request the test session, committing
    at the end of the dependency exactly as the real one does, so a route
    under test sees the same transaction boundaries it sees in production.
    """

    from api.deps import _get_db
    from httpx import ASGITransport, AsyncClient
    from main import app

    async def _override() -> AsyncIterator[AsyncSession]:
        try:
            yield test_db_session
            await test_db_session.commit()
        except Exception:
            await test_db_session.rollback()
            raise

    app.dependency_overrides[_get_db] = _override

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(_get_db, None)


@pytest.fixture
def test_client() -> Any:
    """Sync `TestClient` for routing, auth and serialization checks.

    Deliberately not used as a context manager: entering it runs the app
    lifespan, which issues `SELECT 1` against the configured Postgres and
    fails when there is none. The override below means the dependency never
    reaches the database, but the lifespan probe still would.

    Use `api_client` when the request needs the database.
    """

    from starlette.testclient import TestClient

    from api.deps import _get_db
    from main import app

    async def _override() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[_get_db] = _override

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(_get_db, None)


@pytest.fixture
async def auth_headers(
    factories: Factories, settings: Settings
) -> Callable[..., Coroutine[Any, Any, dict[str, str]]]:
    """Build a real bearer header for a seeded user.

    Mints an actual access token from `core.security` rather than faking the
    dependency, so the auth path under test is the auth path in production.
    """

    from core.security import create_access_token

    async def _headers(user: User | None = None, **overrides: Any) -> dict[str, str]:
        if user is None:
            user = await factories.user(**overrides)

        token: str = create_access_token(user.id, user.role, settings)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture(autouse=True)
def reset_process_globals() -> Any:
    """Clear module-level caches that would otherwise leak across tests.

    Six of them, all process-global:

    - `features.attendance.service._IDEMPOTENCY_STORE` is the scan
      idempotency cache, keyed by user/session/caller-supplied key. A scan
      cached in one test would be replayed by another.
    - `shared.rate_limit._limiter` is a process-global fixed-window limiter.
      Without this, the 30-calls-per-60s budget on `POST /attendance/scan`
      is shared by the whole test session, so an unrelated test eventually
      gets a spurious 429.
    - `features.auth.service._recovery_limiter` caps security-answer failures
      at 3 per email. It keys on the email, so it only stayed invisible while
      every recovery test happened to use a distinct address; one test reusing
      another's address would lock itself out for the rest of the window.
    - `shared.cache._cache` holds face embeddings keyed by `student.id`. The
      factory id counter restarts every test, so student 1 in this test is the
      same cache key as student 1 in the last one - a test that enrolls a face
      hands its blob to the next test that reads an unenrolled student.
    - `shared.email._PENDING` holds the futures of in-flight notification
      sends. A test that dispatches an email parks one there, and the next test
      would inherit it (and any `SMTP_*` monkeypatch it was queued under).
    - `core.scheduler._IN_FLIGHT` and the scheduler singleton. A test that
      starts a scheduler or enters `track()` leaves both behind; worse, a
      started scheduler stays bound to the loop that has just closed, so the
      next test's `start()` would try to reuse a dead loop. `reset_scheduler()`
      is sync because this fixture is - by teardown there is no loop left to
      await `shutdown()` on.
    """

    from core import scheduler as core_scheduler
    from features.attendance import service as attendance_service
    from features.auth import service as auth_service
    from shared import cache, email, rate_limit

    def _clear() -> None:
        attendance_service._IDEMPOTENCY_STORE.clear()
        rate_limit._limiter._windows.clear()
        auth_service._recovery_limiter._windows.clear()
        cache._cache._store.clear()
        email._PENDING.clear()
        core_scheduler.reset_scheduler()

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def reset_sequence() -> Any:
    """Restart the factory sequence per test so ids are stable per test."""

    global _sequence
    _sequence = 0
    yield
    _sequence = 0
