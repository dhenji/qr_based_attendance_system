from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

import features.analytics.model  # noqa: F401
import features.excuse.model  # noqa: F401
import features.sync.model  # noqa: F401
import features.system.model  # noqa: F401
import tests.conftest  # noqa: F401
from core.database import Base
from features.course.model import Course, CourseOffering
from features.enrollment.model import Enrollment
from features.program.model import Program
from features.session.model import Session
from tests.seed_data import seed


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
