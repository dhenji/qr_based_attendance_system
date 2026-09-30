"""Regression cover for `_persist_scan`'s `expires_at` source.

`_persist_scan` used to build the response's `expires_at` from
`row.session.expires_at`, where `row` is the `Attendance` it had just
constructed and flushed. `Attendance.session` declares no `lazy=`, so that
is an implicit lazy load, which raises `MissingGreenlet` in async
(coding-standards §1.6). It resolved before only because the same request
had incidentally put that `Session` in the identity map.

The method now takes the already-loaded `db_session` and reads
`expires_at` off it directly, issuing no query at all.

`_persist_scan` is exercised directly rather than through `submit_scan`
because the property under test is precisely "this method issues no
queries" — the preceding scan flow is irrelevant to it. The fake session
raises on every query entry point, so a reintroduced lazy load fails the
test instead of silently passing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from features.attendance.schema import GPSInput, LivenessEvidence, ScanRequest
from features.attendance.service import AttendanceService
from features.session.model import Session
from shared.enums import ScannedVia

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
SESSION_EXPIRES_AT = NOW + timedelta(hours=2)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _FakeSessionRow(Session):
    """Stand-in for the already-loaded Session model instance.

    Subclasses the real model so the `db_session: Session` annotation holds;
    only the two attributes `_persist_scan` reads are set.
    """

    def __init__(self) -> None:
        super().__init__(id=77, expires_at=SESSION_EXPIRES_AT)


class _QueryTrapSession:
    """Accepts writes, fails loudly on any read.

    `_persist_scan` needs only `add()` and `flush()`. SQLAlchemy routes a
    lazy relationship load back through the session's query methods, so
    making all of them raise is what proves no implicit load happens.
    """

    def __init__(self) -> None:
        self.added: list[Any] = []
        self._next_id = 1000

    async def scalars(self, stmt: Any) -> Any:
        raise AssertionError("unexpected scalars() — implicit lazy load?")

    async def execute(self, stmt: Any) -> Any:
        raise AssertionError("unexpected execute() — implicit lazy load?")

    async def scalar(self, stmt: Any) -> Any:
        raise AssertionError("unexpected scalar() — implicit lazy load?")

    async def get(self, model: Any, ident: Any) -> Any:
        raise AssertionError("unexpected get() — implicit lazy load?")

    async def flush(self) -> None:
        # A real flush assigns the generated primary key; the response
        # builder reads `row.id`, so the fake has to stand in for that.
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _payload(face_match_score: float = 0.95) -> ScanRequest:
    return ScanRequest(
        session_id=77,
        student_number="24-0001",
        gps=GPSInput(lat=14.6, lng=121.0, accuracy=5.0),
        liveness_evidence=LivenessEvidence(
            blink_detected=True,
            head_turn_left=True,
            head_turn_right=True,
            ear_samples=[0.4, 0.6],
        ),
        face_match_score=face_match_score,
        scanned_at=NOW,
        scanned_via=ScannedVia.QR_CAMERA,
    )


def test_expires_at_comes_from_the_passed_session() -> None:
    """The fix: `expires_at` is read off db_session, not row.session."""
    fake = _QueryTrapSession()
    service = AttendanceService(fake)

    response = _run(
        service._persist_scan(
            _payload(),
            student_id=5,
            db_session=_FakeSessionRow(),
            scanned_at=NOW,
            status="present",
            review=False,
            original=None,
            now=NOW,
            cache_key=None,
            idempotency_key=None,
        )
    )

    assert response.expires_at == SESSION_EXPIRES_AT


def test_persisting_issues_no_queries() -> None:
    """`_persist_scan` must not round-trip to the database at all.

    The trap session raises on every query entry point, so reaching the
    response at all proves no lazy load was attempted.
    """
    fake = _QueryTrapSession()
    service = AttendanceService(fake)

    _run(
        service._persist_scan(
            _payload(),
            student_id=5,
            db_session=_FakeSessionRow(),
            scanned_at=NOW,
            status="present",
            review=False,
            original=None,
            now=NOW,
            cache_key=None,
            idempotency_key=None,
        )
    )

    assert len(fake.added) == 1


def test_session_id_is_written_from_the_passed_session() -> None:
    """The attendance row's session_id still comes from db_session.id."""
    fake = _QueryTrapSession()
    service = AttendanceService(fake)

    _run(
        service._persist_scan(
            _payload(),
            student_id=5,
            db_session=_FakeSessionRow(),
            scanned_at=NOW,
            status="present",
            review=False,
            original=None,
            now=NOW,
            cache_key=None,
            idempotency_key=None,
        )
    )

    row = fake.added[0]
    assert row.session_id == 77
    assert row.student_id == 5
    assert row.timestamp == NOW
