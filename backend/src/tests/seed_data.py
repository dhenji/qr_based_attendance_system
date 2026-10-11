"""Seed script for development, demos, and load tests.

Run from ``backend/``::

    cd backend && PYTHONPATH=src python -m tests.seed_data --scale small
    cd backend && python test_seed_data.py --scale small   # same, via the shim

Scales: ``small`` (spec base: 42 students, ~600 attendance rows),
``medium`` (500 students), ``large`` (10_000), ``xl`` (50_000).
``--reset`` deletes previously seeded rows first.

Programs and year levels are created when missing, so the script works on a
fresh database after ``alembic upgrade head``. Everything else is looked up
by its unique column and skipped when already present, making re-runs safe.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

UTC = timezone.utc

SCALE_COUNTS = {"small": 42, "medium": 500, "large": 10_000, "xl": 50_000}

COURSES = [
    ("GE101", "Understanding the Self", 3, 1.5),
    ("CS101", "Intro to Computing", 3, 1.5),
    ("CS201", "Data Structures", 4, 2.0),
    ("CS301", "Operating Systems", 3, 1.5),
    ("IT101", "Web Dev Foundations", 3, 1.5),
    ("IT201", "Network Administration", 3, 1.5),
    ("ECE101", "Circuit Theory 1", 4, 2.0),
]

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

GE101_DATES = [
    date(2026, 6, 1),
    date(2026, 6, 3),
    date(2026, 6, 8),
    date(2026, 6, 10),
    date(2026, 6, 15),
    date(2026, 6, 17),
    date(2026, 6, 22),
    date(2026, 6, 24),
    date(2026, 6, 29),
    date(2026, 7, 1),
    date(2026, 7, 6),
    date(2026, 7, 8),
]

EXTRA_SESSION_DATES = [
    date(2026, 6, 2),
    date(2026, 6, 4),
    date(2026, 6, 5),
    date(2026, 6, 9),
    date(2026, 6, 11),
    date(2026, 6, 12),
]

BASE_STUDENTS = [
    ("24-0001", "Jose", "Rizal", "A"),
    ("24-0002", "Andres", "Bonifacio", "A"),
    ("24-0003", "Emilio", "Aguinaldo", "A"),
    ("24-0004", "Apolinario", "Mabini", "A"),
    ("24-0005", "Antonio", "Luna", "A"),
    ("24-0006", "Marcelo", "del Pilar", "A"),
    ("24-0007", "Gregorio", "del Pilar", "A"),
    ("24-0008", "Sultan", "Kudarat", "B"),
    ("24-0009", "Tandang", "Sora", "B"),
    ("24-0010", "Gabriela", "Silang", "B"),
    ("24-0011", "Diego", "Silang", "B"),
    ("24-0012", "Francisco", "Dagohoy", "B"),
    ("24-0013", "Macario", "Sakay", "B"),
    ("24-0014", "Vicente", "Sotto", "B"),
    ("24-1001", "Manny", "Pacquiao", "A"),
    ("24-1002", "Nonito", "Donaire", "A"),
    ("24-1003", "Carlos", "Yulo", "A"),
    ("24-1004", "Hidilyn", "Diaz", "A"),
    ("24-1005", "Nesthy", "Petecio", "A"),
    ("24-1006", "Eumir", "Marcial", "A"),
    ("24-1007", "Tokyo", "Olympics", "A"),
    ("24-1008", "Niels", "Bohr", "B"),
    ("24-1009", "Alan", "Turing", "B"),
    ("24-1010", "Grace", "Hopper", "B"),
    ("24-1011", "Ada", "Lovelace", "B"),
    ("24-1012", "Linus", "Torvalds", "B"),
    ("24-1013", "Dennis", "Ritchie", "B"),
    ("24-1014", "Bjarne", "Stroustrup", "B"),
    ("24-2001", "Thomas", "Edison", "A"),
    ("24-2002", "Nikola", "Tesla", "A"),
    ("24-2003", "Alexander", "Graham Bell", "A"),
    ("24-2004", "Guglielmo", "Marconi", "A"),
    ("24-2005", "Robert", "Noyce", "A"),
    ("24-2006", "Jack", "Kilby", "A"),
    ("24-2007", "Lee de", "Forest", "A"),
    ("24-2008", "Philo", "Farnsworth", "A"),
    ("24-2009", "John", "Bardeen", "A"),
    ("24-2010", "William", "Shockley", "A"),
    ("24-2011", "Walter", "Brattain", "A"),
    ("24-2012", "Claude", "Shannon", "A"),
    ("24-2013", "Kurt", "Godel", "A"),
    ("24-2014", "Alan", "Kay", "A"),
]

BASE_PROGRAM_OF = {
    "24-0": "BSCS",
    "24-1": "BSIT",
    "24-2": "BSECE",
}

ABSENT_SESSIONS = {
    "24-0003": {11},
    "24-0004": {9, 11},
    "24-0005": {2, 5, 8, 11},
    "24-0006": {1, 4, 5, 8, 11},
    "24-0007": {7, 9, 11},
    "24-0008": {3, 8},
    "24-0009": {0, 2, 4, 6, 8},
    "24-0012": {1, 5, 10},
    "24-0013": {7},
    "24-0014": {4, 9},
}

RISK_SEED = [
    ("24-0001", "0.02", "low"),
    ("24-0002", "0.03", "low"),
    ("24-0005", "0.45", "high"),
    ("24-0006", "0.72", "high"),
    ("24-0007", "0.55", "high"),
    ("24-0008", "0.35", "medium"),
    ("24-0009", "0.68", "high"),
    ("24-0012", "0.28", "medium"),
    ("24-0014", "0.35", "medium"),
]

LIVENESS = {
    "blink_detected": True,
    "head_turn_left": True,
    "head_turn_right": True,
    "ear_samples": [0.18, 0.31, 0.29, 0.33],
    "pnp_evidence": {"yaw": 12.5},
}


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/attendance_sys",
    )


async def _get_or_create(session, model, defaults: dict, **lookup):
    from sqlalchemy import select

    row = (
        await session.scalars(select(model).filter_by(**lookup).limit(1))
    ).one_or_none()
    if row is not None:
        return row, False
    row = model(**{**lookup, **defaults})
    session.add(row)
    await session.flush()
    return row, True


async def seed(
    scale: str = "small",
    reset: bool = False,
    load_sessions: int = 0,
    database_url: str | None = None,
) -> dict[str, int]:
    from sqlalchemy import delete, select

    from core.database import Base
    from features.analytics.model import StudentRiskScore
    from features.attendance.model import Attendance
    from features.auth.model import User
    from features.course.model import Course, CourseOffering
    from features.course_professor.model import CourseProfessor
    from features.enrollment.model import Enrollment
    from features.excuse.model import ExcuseRequest
    from features.professor.model import Professor
    from features.program.model import Program, YearLevel
    from features.session.model import Session
    from features.student.model import Student
    from features.sync.model import SyncQueue
    from features.system.model import BackupLog
    from shared.enums import UserRole
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    counts = {
        k: 0 for k in ("courses", "students", "sessions", "records",
                       "load_sessions")
    }
    engine = create_async_engine(database_url or _database_url())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db:
            if reset:
                for model in (
                    SyncQueue,
                    BackupLog,
                    StudentRiskScore,
                    ExcuseRequest,
                    Attendance,
                    Session,
                    Enrollment,
                    CourseProfessor,
                    CourseOffering,
                    Student,
                    Professor,
                    Course,
                    User,
                ):
                    await db.execute(delete(model))
                await db.commit()

            programs: dict[str, Program] = {}
            for code, name, years in PROGRAMS:
                program, _ = await _get_or_create(
                    db, Program, {"name": name, "total_years": years}, code=code
                )
                programs[code] = program
                for n in range(1, years + 1):
                    terms = YEAR_TERMS[n]
                    await _get_or_create(
                        db,
                        YearLevel,
                        {
                            "label": f"{n} Year" if False else ordinal(n),
                            "term_structure": {
                                "terms": [
                                    {"code": t, "label": label(t)} for t in terms
                                ]
                            },
                            "sort_order": n,
                        },
                        program_id=program.id,
                        year_number=n,
                    )
            await db.commit()

            courses: dict[str, Course] = {}
            for code, name, units, hours in COURSES:
                course, made = await _get_or_create(
                    db,
                    Course,
                    {"course_name": name, "units": units,
                     "session_duration_hours": hours},
                    course_code=code,
                )
                courses[code] = course
                counts["courses"] += made
            await db.commit()

            year_of = {}
            for program in programs.values():
                rows = (
                    await db.scalars(
                        select(YearLevel).where(
                            YearLevel.program_id == program.id
                        )
                    )
                ).all()
                year_of[program.code] = {r.year_number: r for r in rows}

            offering_specs = [
                ("GE101", "BSCS", 1, "MW", time(7, 0), time(8, 30)),
                ("GE101", "BSIT", 1, "MW", time(7, 0), time(8, 30)),
                ("GE101", "BSECE", 1, "MW", time(7, 0), time(8, 30)),
                ("CS101", "BSCS", 1, "MWF", time(9, 0), time(10, 30)),
                ("CS201", "BSCS", 2, "MWF", time(10, 30), time(12, 30)),
                ("CS301", "BSCS", 3, "TF", time(13, 0), time(14, 30)),
                ("IT101", "BSIT", 1, "MWF", time(13, 0), time(14, 30)),
                ("IT201", "BSIT", 2, "MW", time(10, 0), time(11, 30)),
                ("ECE101", "BSECE", 1, "MWF", time(8, 0), time(10, 0)),
            ]
            offerings: dict[tuple[str, str, int], CourseOffering] = {}
            for code, prog, year_no, days, start, end in offering_specs:
                offering, _ = await _get_or_create(
                    db,
                    CourseOffering,
                    {
                        "year_level_id": year_of[prog][year_no].id,
                        "semester": "1st_sem",
                        "academic_year": "2026-2027",
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
                offerings[(code, prog, year_no)] = offering
            await db.commit()

            admin, _ = await _get_or_create(
                db,
                User,
                {
                    "password_hash": "seed-not-for-login",
                    "role": UserRole.ADMIN.value,
                },
                email="admin.seed@uni.edu",
            )
            await db.commit()

            prof_rows = [
                ("prof.delacruz@uni.edu", "Maria", "Dela Cruz", "Computer Science"),
                ("prof.santos@uni.edu", "Juan", "Santos", "Computer Science"),
                ("prof.reyes@uni.edu", "Ana", "Reyes", "Information Technology"),
                ("prof.garcia@uni.edu", "Luis", "Garcia", "Electronics Engineering"),
            ]
            profs: dict[str, Professor] = {}
            for email, first, last, dept in prof_rows:
                user, _ = await _get_or_create(
                    db,
                    User,
                    {
                        "password_hash": "seed-not-for-login",
                        "role": UserRole.PROFESSOR.value,
                    },
                    email=f"account.{email}",
                )
                professor, _ = await _get_or_create(
                    db,
                    Professor,
                    {
                        "user_id": user.id,
                        "first_name": first,
                        "last_name": last,
                        "department": dept,
                    },
                    email=email,
                )
                profs[email] = professor
            await db.commit()

            assignments = [
                ("prof.delacruz@uni.edu", ("GE101", "BSCS", 1), True,
                 date(2026, 6, 1), None),
                ("prof.delacruz@uni.edu", ("CS101", "BSCS", 1), True,
                 date(2026, 6, 1), None),
                ("prof.delacruz@uni.edu", ("CS201", "BSCS", 2), True,
                 date(2026, 6, 1), None),
                ("prof.delacruz@uni.edu", ("CS301", "BSCS", 3), True,
                 date(2026, 6, 1), date(2026, 6, 20)),
                ("prof.santos@uni.edu", ("CS301", "BSCS", 3), True,
                 date(2026, 6, 22), None),
                ("prof.santos@uni.edu", ("GE101", "BSCS", 1), False,
                 date(2026, 6, 1), None),
                ("prof.reyes@uni.edu", ("IT101", "BSIT", 1), True,
                 date(2026, 6, 1), None),
                ("prof.reyes@uni.edu", ("IT201", "BSIT", 2), True,
                 date(2026, 6, 1), None),
                ("prof.reyes@uni.edu", ("GE101", "BSIT", 1), True,
                 date(2026, 6, 1), None),
                ("prof.garcia@uni.edu", ("ECE101", "BSECE", 1), True,
                 date(2026, 6, 1), None),
                ("prof.garcia@uni.edu", ("GE101", "BSECE", 1), True,
                 date(2026, 6, 1), None),
            ]
            for email, key, primary, start, end in assignments:
                offering = offerings[key]
                existing = (
                    await db.scalars(
                        select(CourseProfessor).where(
                            CourseProfessor.offering_id == offering.id,
                            CourseProfessor.professor_id == profs[email].id,
                            CourseProfessor.effective_from == start,
                        )
                    )
                ).one_or_none()
                if existing is None:
                    db.add(
                        CourseProfessor(
                            offering_id=offering.id,
                            professor_id=profs[email].id,
                            effective_from=start,
                            is_primary=primary,
                            effective_to=end,
                            semester="1st_sem",
                            assigned_by=admin.id,
                        )
                    )
            await db.commit()

            total = SCALE_COUNTS[scale]
            roster = list(BASE_STUDENTS)
            program_cycle = ["BSCS", "BSIT", "BSECE"]
            i = len(roster)
            while len(roster) < total:
                prog = program_cycle[i % 3]
                prefix = {"BSCS": "24-0", "BSIT": "24-1", "BSECE": "24-2"}[prog]
                roster.append(
                    (f"{prefix}{9000 + i}", f"Seed{i}", f"Student{i}",
                     "A" if i % 2 == 0 else "B")
                )
                i += 1

            spec_of = {}
            for sid, first, last, section in roster:
                spec_of[sid] = BASE_PROGRAM_OF.get(sid[:4], program_cycle[
                    (len(spec_of)) % 3
                ])

            students: dict[str, Student] = {}
            for idx, (sid, first, last, section) in enumerate(roster):
                prog = spec_of[sid]
                year = year_of[prog][1]
                student, made = await _get_or_create(
                    db,
                    Student,
                    {
                        "email": f"{sid.lower().replace(' ', '')}@students.uni.edu",
                        "first_name": first,
                        "last_name": last,
                        "year_level_id": year.id,
                        "section": section,
                    },
                    student_id=sid,
                )
                students[sid] = student
                counts["students"] += made
                if idx % 500 == 499:
                    await db.commit()
            await db.commit()

            from core.security import hash_password as _hash_password

            for idx, (sid, _first, _last, _section) in enumerate(roster[:30], 1):
                slot = f"loadtest{idx:02d}"
                # Deliverable domain: the login contract validates mailboxes
                # with EmailStr, which rejects reserved TLDs such as `.test`.
                email = f"{slot}@load.uni.edu"
                row = (
                    await db.scalars(select(User).where(User.email == email))
                ).one_or_none()
                if row is None:
                    # Databases seeded before the reserved-TLD domain was
                    # replaced still hold the `.test` address for the same
                    # slot; migrate it rather than minting a second user.
                    legacy = f"{slot}@load.test"
                    row = (
                        await db.scalars(
                            select(User).where(User.email == legacy)
                        )
                    ).one_or_none()
                    if row is not None:
                        row.email = email
                        await db.flush()
                if row is None:
                    row = User(
                        email=email,
                        password_hash=_hash_password("Loadtest1!"),
                        role=UserRole.STUDENT.value,
                    )
                    db.add(row)
                    await db.flush()
                if students[sid].user_id is None:
                    students[sid].user_id = row.id
            await db.commit()

            if scale == "small":
                for sid, student in students.items():
                    prog = spec_of[sid]
                    await _get_or_create(
                        db,
                        Enrollment,
                        {"semester": "1st_sem", "academic_year": "2026-2027"},
                        student_id=student.id,
                        offering_id=offerings[("GE101", prog, 1)].id,
                        academic_year="2026-2027",
                    )
                    specific = {
                        "BSCS": ("CS101", "BSCS", 1),
                        "BSIT": ("IT101", "BSIT", 1),
                        "BSECE": ("ECE101", "BSECE", 1),
                    }[prog]
                    await _get_or_create(
                        db,
                        Enrollment,
                        {"semester": "1st_sem", "academic_year": "2026-2027"},
                        student_id=student.id,
                        offering_id=offerings[specific].id,
                        academic_year="2026-2027",
                    )
            else:
                for sid, student in students.items():
                    prog = spec_of[sid]
                    for key in (("GE101", prog, 1),):
                        await _get_or_create(
                            db,
                            Enrollment,
                            {"semester": "1st_sem",
                             "academic_year": "2026-2027"},
                            student_id=student.id,
                            offering_id=offerings[key].id,
                            academic_year="2026-2027",
                        )
            await db.commit()

            ge_sessions: dict[str, list[Session]] = {}
            for prog in ("BSCS", "BSIT", "BSECE"):
                if scale == "small" and prog != "BSCS":
                    continue
                offering = offerings[("GE101", prog, 1)]
                owner = profs[
                    {"BSCS": "prof.delacruz@uni.edu",
                     "BSIT": "prof.reyes@uni.edu",
                     "BSECE": "prof.garcia@uni.edu"}[prog]
                ]
                rows = []
                for idx, day in enumerate(GE101_DATES):
                    code = f"SEED-GE101-{prog}-{idx:02d}"
                    start = datetime.combine(day, time(7, 0), tzinfo=UTC)
                    end = datetime.combine(day, time(8, 30), tzinfo=UTC)
                    existing = (
                        await db.scalars(
                            select(Session).where(Session.session_code == code)
                        )
                    ).one_or_none()
                    if existing is None:
                        existing = Session(
                            offering_id=offering.id,
                            professor_id=owner.id,
                            session_code=code,
                            duration_minutes=90,
                            present_window_minutes=5,
                            late_window_minutes=10,
                            scheduled_start_time=start,
                            scheduled_end_time=end,
                            expires_at=end,
                            classroom_name="Room 301",
                            classroom_lat=14.5995,
                            classroom_lng=120.9842,
                        )
                        db.add(existing)
                        await db.flush()
                        counts["sessions"] += 1
                    rows.append(existing)
                ge_sessions[prog] = rows
            await db.commit()

            extra_specs = [
                (("CS101", "BSCS", 1), "prof.delacruz@uni.edu", time(9, 0),
                 time(10, 30)),
                (("IT101", "BSIT", 1), "prof.reyes@uni.edu", time(13, 0),
                 time(14, 30)),
            ]
            if scale == "small":
                for key, email, start_t, end_t in extra_specs:
                    offering = offerings[key]
                    for idx, day in enumerate(EXTRA_SESSION_DATES):
                        code = f"SEED-{key[0]}-{idx:02d}"
                        start = datetime.combine(day, start_t, tzinfo=UTC)
                        end = datetime.combine(day, end_t, tzinfo=UTC)
                        existing = (
                            await db.scalars(
                                select(Session).where(Session.session_code == code)
                            )
                        ).one_or_none()
                        if existing is None:
                            db.add(
                                Session(
                                    offering_id=offering.id,
                                    professor_id=profs[email].id,
                                    session_code=code,
                                    duration_minutes=90,
                                    present_window_minutes=5,
                                    late_window_minutes=10,
                                    scheduled_start_time=start,
                                    scheduled_end_time=end,
                                    expires_at=end,
                                    classroom_name="Room 301",
                                    classroom_lat=14.5995,
                                    classroom_lng=120.9842,
                                )
                            )
                            counts["sessions"] += 1
                await db.commit()

            for sid, student in students.items():
                prog = spec_of[sid]
                sessions = ge_sessions.get(prog, ge_sessions["BSCS"])
                absent = ABSENT_SESSIONS.get(sid, set())
                for idx, sess in enumerate(sessions):
                    existing = (
                        await db.scalars(
                            select(Attendance).where(
                                Attendance.student_id == student.id,
                                Attendance.session_id == sess.id,
                            )
                        )
                    ).one_or_none()
                    if existing is not None:
                        continue
                    if scale != "small" and sid not in ABSENT_SESSIONS:
                        status = "absent" if idx % 12 == 11 else (
                            "late" if idx % 5 == 4 else "present"
                        )
                    else:
                        status = "absent" if idx in absent else (
                            "late" if (idx * 7 + len(sid)) % 9 == 0 else "present"
                        )
                    db.add(
                        Attendance(
                            student_id=student.id,
                            session_id=sess.id,
                            timestamp=sess.scheduled_start_time + timedelta(
                                minutes=3 if status == "present" else 8
                            ),
                            gps_lat=14.5995,
                            gps_lng=120.9842,
                            validation_status=status,
                            sync_status="synced",
                            liveness_evidence=dict(LIVENESS),
                            face_match_score=Decimal("0.82"),
                            scanned_via="qr_camera",
                        )
                    )
                    counts["records"] += 1
            await db.commit()

            if scale == "small":
                excuses = [
                    ("24-0006", 4, "professor", "quick",
                     "Family emergency reported", "approved", None),
                    ("24-0007", 6, "professor", "prof_with_evidence",
                     "Hospitalized — attached medical cert", "approved",
                     ["https://files.test/medical_cert.pdf"]),
                    ("24-0009", 8, "student", "request",
                     "Sick leave — attached BRGY certificate", "pending",
                     ["https://files.test/brgy_cert.pdf"]),
                ]
                for sid, sess_idx, by, via, reason, status, urls in excuses:
                    student = students[sid]
                    exc_session = ge_sessions["BSCS"][sess_idx]
                    existing = (
                        await db.scalars(
                            select(ExcuseRequest).where(
                                ExcuseRequest.student_id == student.id,
                                ExcuseRequest.session_id == exc_session.id,
                                ExcuseRequest.initiated_by == by,
                            )
                        )
                    ).one_or_none()
                    if existing is None:
                        existing = ExcuseRequest(
                            student_id=student.id,
                            session_id=exc_session.id,
                            initiated_by=by,
                            initiated_via=via,
                            reason=reason,
                            attachment_urls=urls,
                            status=status,
                        )
                        db.add(existing)
                        await db.flush()
                    record = (
                        await db.scalars(
                            select(Attendance).where(
                                Attendance.student_id == student.id,
                                Attendance.session_id == exc_session.id,
                            )
                        )
                    ).one()
                    record.excuse_request_id = existing.id
                    if status == "approved":
                        record.original_status = record.original_status or "absent"
                        record.validation_status = "excused"
                        record.excuse_reason = reason
                        record.excuse_type = via
                await db.commit()

                enrolled_ids = {
                    "24-0001", "24-0002", "24-0003", "24-0004", "24-0005",
                    "24-0006", "24-0007", "24-0008", "24-0009", "24-0010",
                    "24-0011", "24-0012", "24-0013", "24-0014",
                    "24-1001", "24-1002", "24-1003", "24-1004", "24-1005",
                    "24-1006", "24-1007",
                }
                for sid, student in students.items():
                    if sid in enrolled_ids:
                        student.face_embedding = b"seed-embedding-v1"
                        student.face_enrolled_at = datetime(
                            2026, 6, 10, tzinfo=UTC
                        )
                        student.face_embedding_version = 1
                await db.commit()

                pending = (
                    await db.scalars(
                        select(SyncQueue).where(
                            SyncQueue.status == "pending"
                        ).limit(1)
                    )
                ).one_or_none()
                if pending is None:
                    student = students["24-0008"]
                    for sess_idx in (4, 6, 8):
                        sess = ge_sessions["BSCS"][sess_idx]
                        db.add(
                            SyncQueue(
                                record_data={
                                    "student_id": student.id,
                                    "session_id": sess.id,
                                    "scanned_at": (
                                        sess.scheduled_start_time + timedelta(
                                            minutes=10
                                        )
                                    ).isoformat(),
                                    "gps_lat": 14.5995,
                                    "gps_lng": 120.9842,
                                    "face_match_score": 0.81,
                                },
                                status="pending",
                            )
                        )
                    await db.commit()

                for sid, prob, level in RISK_SEED:
                    student = students[sid]
                    offering = offerings[("GE101", spec_of[sid], 1)]
                    existing = (
                        await db.scalars(
                            select(StudentRiskScore).where(
                                StudentRiskScore.student_id == student.id,
                                StudentRiskScore.offering_id == offering.id,
                                StudentRiskScore.semester == "1st_sem",
                                StudentRiskScore.computed_day
                                == date(2026, 7, 9),
                            )
                        )
                    ).one_or_none()
                    if existing is None:
                        db.add(
                            StudentRiskScore(
                                student_id=student.id,
                                offering_id=offering.id,
                                semester="1st_sem",
                                risk_probability=Decimal(prob),
                                risk_level=level,
                                features={"absence_rate": float(prob)},
                                computed_at=datetime(2026, 7, 9, 2, 0,
                                                     tzinfo=UTC),
                                computed_day=date(2026, 7, 9),
                            )
                        )
                await db.commit()

                logged = (
                    await db.scalars(select(BackupLog).limit(1))
                ).one_or_none()
                if logged is None:
                    db.add(
                        BackupLog(
                            filename="backup_20260708_020000.sql.gz.enc",
                            kind="full",
                            size_bytes=5242880,
                            sha256="baf1770718fda5f6d1cee88285ec19d4a9273e00080f"
                            "0f6b147abf7b4b4a",
                            storage_backend="local",
                            encryption_key_version=1,
                            started_at=datetime(2026, 7, 8, 2, 0, tzinfo=UTC),
                            finished_at=datetime(2026, 7, 8, 2, 4, tzinfo=UTC),
                            status="completed",
                        )
                    )
                    await db.commit()

            if load_sessions > 0:
                now = datetime.now(UTC)
                offering = offerings[("GE101", "BSCS", 1)]
                owner = profs["prof.delacruz@uni.edu"]
                for sid, _first, _last, _section in roster[:30]:
                    await _get_or_create(
                        db,
                        Enrollment,
                        {"semester": "1st_sem", "academic_year": "2026-2027"},
                        student_id=students[sid].id,
                        offering_id=offering.id,
                        academic_year="2026-2027",
                    )
                for idx in range(load_sessions):
                    code = f"SEED-LOAD-{idx:03d}"
                    existing = (
                        await db.scalars(
                            select(Session).where(Session.session_code == code)
                        )
                    ).one_or_none()
                    if existing is None:
                        db.add(
                            Session(
                                offering_id=offering.id,
                                professor_id=owner.id,
                                session_code=code,
                                duration_minutes=180,
                                present_window_minutes=5,
                                late_window_minutes=10,
                                scheduled_start_time=now - timedelta(minutes=5),
                                scheduled_end_time=now + timedelta(hours=3),
                                expires_at=now + timedelta(hours=3),
                                classroom_name="Room 301",
                                classroom_lat=14.5995,
                                classroom_lng=120.9842,
                            )
                        )
                        counts["load_sessions"] += 1
                await db.commit()
    finally:
        await engine.dispose()
    return counts


def ordinal(n: int) -> str:
    return {1: "1st Year", 2: "2nd Year", 3: "3rd Year"}.get(n, f"{n}th Year")


def label(term: str) -> str:
    return {"1st_sem": "1st Semester", "2nd_sem": "2nd Semester",
            "midyear": "Midyear", "summer": "Summer"}.get(term, term)


def main(argv: list[str] | None = None) -> dict[str, int]:
    parser = argparse.ArgumentParser(description="Seed the attendance database.")
    parser.add_argument(
        "--scale", choices=sorted(SCALE_COUNTS), default="small",
        help="Seed volume (default: small)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete previously seeded rows before seeding",
    )
    parser.add_argument(
        "--load-fixtures", type=int, default=0, metavar="N",
        help="Create N active load sessions (SEED-LOAD-###) anchored at now "
        "and enroll the load-test students in GE101-BSCS for the run",
    )
    args = parser.parse_args(argv)
    result = asyncio.run(
        seed(scale=args.scale, reset=args.reset,
             load_sessions=args.load_fixtures)
    )
    print(f"seeded scale={args.scale}: {result}")
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
