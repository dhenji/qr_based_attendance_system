from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from core.database import Base

import features.analytics.model  # noqa: F401
import features.excuse.model  # noqa: F401
import features.sync.model  # noqa: F401
import features.system.model  # noqa: F401
import tests.conftest  # noqa: F401
from features.auth.model import User
from features.auth.schema import LoginRequest
from features.course.model import Course, CourseOffering
from features.enrollment.model import Enrollment
from features.program.model import Program
from features.session.model import Session
from tests.seed_data import seed


def test_load_emails_pass_login_contract() -> None:
    """The load accounts must survive EmailStr: reserved TLDs 422 every login."""

    for idx in range(1, 31):
        request = LoginRequest(
            email=f"loadtest{idx:02d}@load.uni.edu", password="Loadtest1!"
        )
        assert request.email == f"loadtest{idx:02d}@load.uni.edu"


async def _fresh_db(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def test_load_fixtures_created_and_idempotent(tmp_path: object) -> None:
    from pathlib import Path

    url = f"sqlite+aiosqlite:///{Path(str(tmp_path)) / 'load.db'}"
    await _fresh_db(url)

    first = await seed("small", load_sessions=5, database_url=url)
    assert first["load_sessions"] == 5

    engine = create_async_engine(url)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        async with async_sessionmaker(engine)() as db:
            codes = (
                await db.scalars(
                    select(Session.session_code)
                    .where(Session.session_code.like("SEED-LOAD-%"))
                    .order_by(Session.session_code)
                )
            ).all()
            assert codes == [f"SEED-LOAD-{i:03d}" for i in range(5)]

            now = datetime.now(timezone.utc)
            upcoming = (
                await db.scalars(
                    select(func.count())
                    .select_from(Session)
                    .where(Session.session_code.like("SEED-LOAD-%"))
                    .where(Session.expires_at > now)
                )
            ).one()
            assert upcoming == 5

            ge_offering_id = (
                await db.scalars(
                    select(CourseOffering.id)
                    .join(Course, Course.id == CourseOffering.course_id)
                    .join(Program, Program.id == CourseOffering.program_id)
                    .where(Course.course_code == "GE101")
                    .where(Program.code == "BSCS")
                )
            ).one()
            enrolled = (
                await db.scalars(
                    select(func.count())
                    .select_from(Enrollment)
                    .where(Enrollment.offering_id == ge_offering_id)
                )
            ).one()
            assert enrolled == 30
    finally:
        await engine.dispose()

    second = await seed("small", load_sessions=5, database_url=url)
    assert second["load_sessions"] == 0
    assert second["students"] == 0
    assert second["records"] == 0


async def test_load_email_migrated_from_reserved_domain(tmp_path: object) -> None:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import async_sessionmaker

    url = f"sqlite+aiosqlite:///{Path(str(tmp_path)) / 'legacy.db'}"
    await _fresh_db(url)

    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as db:
            db.add(
                User(
                    email="loadtest01@load.test",
                    password_hash="legacy",
                    role="student",
                )
            )
            await db.commit()

        await seed("small", database_url=url)

        async with async_sessionmaker(engine)() as db:
            row = (
                await db.scalars(
                    select(User).where(User.email == "loadtest01@load.uni.edu")
                )
            ).one()
            assert row.email == "loadtest01@load.uni.edu"

            domains = (
                await db.scalars(select(User.email).where(User.email.like("loadtest%")))
            ).all()
            assert len(domains) == 30
            assert all(address.endswith("@load.uni.edu") for address in domains)
    finally:
        await engine.dispose()


async def test_reseed_survives_batch_written_risk_rows(tmp_path: object) -> None:
    """Nightly batch rows share (student, offering) with the seed's rows.

    The batch upserts per (student, offering, semester, computed_day), so
    after any batch run the seed's pair-only lookup multi-matches and the
    re-seed crashed with MultipleResultsFound.
    """

    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from features.analytics.model import StudentRiskScore

    url = f"sqlite+aiosqlite:///{Path(str(tmp_path)) / 'batched.db'}"
    await _fresh_db(url)
    await seed("small", database_url=url)

    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as db:
            seeded = (
                await db.scalars(
                    select(StudentRiskScore).where(
                        StudentRiskScore.computed_day == date(2026, 7, 9)
                    )
                )
            ).all()
            assert len(seeded) == 9

            first = seeded[0]
            pair = (
                first.student_id,
                first.offering_id,
                first.semester,
            )
            db.add(
                StudentRiskScore(
                    student_id=pair[0],
                    offering_id=pair[1],
                    semester=pair[2],
                    risk_probability=Decimal("0.10"),
                    risk_level="low",
                    features={},
                    computed_at=datetime.now(timezone.utc),
                    computed_day=date.today(),
                )
            )
            await db.commit()

        result = await seed("small", database_url=url)

        async with async_sessionmaker(engine)() as db:
            rows = (
                await db.scalars(
                    select(StudentRiskScore).where(
                        StudentRiskScore.student_id == pair[0],
                        StudentRiskScore.offering_id == pair[1],
                    )
                )
            ).all()
            assert len(rows) == 2
    finally:
        await engine.dispose()

    assert result["students"] == 0
