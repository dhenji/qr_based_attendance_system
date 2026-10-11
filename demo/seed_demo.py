"""Seed a super_admin and demo academic structure for presentations.

Run from the ``backend/`` directory with its venv active::

   cd backend && source .venv/bin/activate
    PYTHONPATH=src python ../demo/seed_demo.py

Or against a specific database::

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys \
        PYTHONPATH=src python ../demo/seed_demo.py

The script is idempotent: existing rows are reused, missing ones are created.
It seeds: one super_admin user, programs + year levels, courses, and two
course offerings to target with the bulk-enrollment CSV.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def _ensure_backend_venv() -> None:
    """Re-exec under backend/.venv so deps (sqlalchemy, asyncpg) resolve."""
    venv_dir = REPO_ROOT / "backend" / ".venv"
    if sys.executable.startswith(str(venv_dir)):
        return
    if os.environ.get("_SEED_DEMO_REEXEC"):
        return
    if not VENV_PYTHON.exists():
        sys.exit(
            "backend/.venv not found. Create it first:\n"
            "  cd backend && python -m venv .venv && "
            ".venv/bin/pip install -r requirements.txt"
        )
    os.environ["_SEED_DEMO_REEXEC"] = "1"
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])


_ensure_backend_venv()

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "dev-only-secret-0123456789abcdef")

from shared.enums import UserRole  # noqa: E402

PROGRAMS = [
    ("BSCS", "Bachelor of Science in Computer Science", 4),
    ("BSIT", "Bachelor of Science in Information Technology", 4),
    ("BSECE", "Bachelor of Science in Electronics Engineering", 5),
]

YEAR_TERMS = {
    1: ["1st_sem", "2nd_sem"],
    2: ["1st_sem", "2nd_sem"],
    3: ["1st_sem", "2nd_sem", "midyear"],
    4: ["1st_sem", "2nd_sem"],
    5: ["1st_sem", "2nd_sem"],
}

COURSES = [
    ("GE101", "Understanding the Self", 3, 1.5),
    ("CS101", "Intro to Computing", 3, 1.5),
    ("CS201", "Data Structures", 4, 2.0),
    ("IT101", "Web Dev Foundations", 3, 1.5),
    ("ECE101", "Circuit Theory 1", 4, 2.0),
]

OFFERING_SPECS = [
    ("GE101", "BSCS", 1, "MWF", time(8, 0), time(9, 30)),
    ("CS101", "BSCS", 1, "TTH", time(10, 0), time(11, 30)),
    ("CS201", "BSCS", 2, "MWF", time(10, 30), time(12, 30)),
    ("IT101", "BSIT", 1, "TTH", time(13, 0), time(14, 30)),
    ("ECE101", "BSECE", 1, "MWF", time(8, 0), time(10, 0)),
]


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys",
    )


def ordinal(n: int) -> str:
    return {1: "1st Year", 2: "2nd Year", 3: "3rd Year"}.get(n, f"{n}th Year")


def label(term: str) -> str:
    return {"1st_sem": "1st Semester", "2nd_sem": "2nd Semester",
            "midyear": "Midyear", "summer": "Summer"}.get(term, term)


async def _get_or_create(session, model, defaults: dict, **lookup):
    from sqlalchemy import select

    row = (await session.scalars(select(model).filter_by(**lookup).limit(1))).one_or_none()
    if row is not None:
        return row, False
    row = model(**{**lookup, **defaults})
    session.add(row)
    await session.flush()
    return row, True


async def seed_demo(
    email: str,
    password: str,
    update_password: bool,
    database_url: str | None = None,
) -> dict[str, int]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from core.security import hash_password
    from features.auth.model import User
    from features.course.model import Course, CourseOffering
    from features.program.model import Program, YearLevel

    counts = {"programs": 0, "year_levels": 0, "courses": 0, "offerings": 0, "super_admin": 0}
    engine = create_async_engine(database_url or _database_url())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db:
            programs: dict[str, Program] = {}
            for code, name, years in PROGRAMS:
                program, created = await _get_or_create(
                    db, Program, {"name": name, "total_years": years}, code=code
                )
                programs[code] = program
                counts["programs"] += int(created)
                for n in range(1, years + 1):
                    terms = YEAR_TERMS[n]
                    _, created = await _get_or_create(
                        db,
                        YearLevel,
                        {
                            "label": ordinal(n),
                            "term_structure": {"terms": [{"code": t, "label": label(t)} for t in terms]},
                            "sort_order": n,
                        },
                        program_id=program.id,
                        year_number=n,
                    )
                    counts["year_levels"] += int(created)
            await db.commit()

            courses: dict[str, Course] = {}
            for code, name, units, hours in COURSES:
                course, created = await _get_or_create(
                    db,
                    Course,
                    {"course_name": name, "units": units, "session_duration_hours": hours},
                    course_code=code,
                )
                courses[code] = course
                counts["courses"] += int(created)
            await db.commit()

            year_of: dict[str, dict[int, YearLevel]] = {}
            for code, program in programs.items():
                rows = (
                    await db.execute(
                        select(YearLevel).where(YearLevel.program_id == program.id)
                    )
                ).scalars().all()
                year_of[code] = {y.year_number: y for y in rows}

            for code, prog, year_no, days, start, end in OFFERING_SPECS:
                _, created = await _get_or_create(
                    db,
                    CourseOffering,
                    {
                        "year_level_id": year_of[prog][year_no].id,
                        "sessions_per_week": 2,
                        "semester_weeks": 16,
                        "schedule_days": days,
                        "schedule_start_time": start,
                        "schedule_end_time": end,
                        "classroom_name": "Room 301",
                        "classroom_lat": 14.5995,
                        "classroom_lng": 120.9842,
                    },
                    course_id=courses[code].id,
                    program_id=programs[prog].id,
                    semester="1st_sem",
                    academic_year="2026-2027",
                )
                counts["offerings"] += int(created)
            await db.commit()

            existing = (
                await db.scalars(select(User).where(User.email == email).limit(1))
            ).one_or_none()
            if existing is None:
                db.add(
                    User(
                        email=email,
                        password_hash=hash_password(password),
                        role=UserRole.SUPER_ADMIN.value,
                        must_change_password=False,
                    )
                )
                counts["super_admin"] = 1
            else:
                if existing.role != UserRole.SUPER_ADMIN.value:
                    existing.role = UserRole.SUPER_ADMIN.value
                if update_password:
                    existing.password_hash = hash_password(password)
                existing.is_active = True
                existing.is_locked = False
                existing.failed_login_attempts = 0
            await db.commit()
    finally:
        await engine.dispose()
    return counts


def main(argv: list[str] | None = None) -> dict[str, int]:
    parser = argparse.ArgumentParser(description="Seed demo super_admin + academic structure.")
    parser.add_argument("--email", default="super@attendly.demo")
    parser.add_argument("--password", default=os.environ.get("DEMO_SUPER_ADMIN_PASSWORD", "Demo!1234"))
    parser.add_argument("--update-password", action="store_true",
                        help="Overwrite the password if the account already exists.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    counts = asyncio.run(
        seed_demo(
            email=args.email,
            password=args.password,
            update_password=args.update_password,
            database_url=args.database_url,
        )
    )
    print("Demo seed complete:")
    for key, value in counts.items():
        print(f"  {key}: {value} created")
    print(f"super_admin login -> email: {args.email}")
    return counts


if __name__ == "__main__":
    main()
