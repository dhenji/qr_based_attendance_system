from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course_professor.exceptions import (
    OverlappingAssignmentException,
    PrimaryAssignmentConflictException,
)
from features.course_professor.model import CourseProfessor


def _overlaps(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
) -> bool:
    """Inclusive interval overlap; a NULL end means ongoing."""
    return start_a <= (end_b or date.max) and start_b <= (end_a or date.max)


class CourseProfessorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_overlap(
        self,
        offering_id: int,
        professor_id: int,
        effective_from: date,
        effective_to: date | None,
        exclude: CourseProfessor | None = None,
    ) -> list[CourseProfessor]:
        """Return existing assignments overlapping [effective_from, effective_to].

        `effective_to` is inclusive: an assignment ending today is still active
        today, matching the `effective_to >= today` checks used by the session,
        attendance, and professor-course queries.
        """
        stmt: Select[tuple[CourseProfessor]] = select(CourseProfessor).where(
            CourseProfessor.offering_id == offering_id,
            CourseProfessor.professor_id == professor_id,
        )

        existing: Sequence[CourseProfessor] = (await self._session.scalars(stmt)).all()
        overlap: list[CourseProfessor] = [
            e
            for e in existing
            if e is not exclude
            and _overlaps(
                effective_from,
                effective_to,
                e.effective_from,
                e.effective_to,
            )
        ]

        return overlap

    async def check_primary_conflict(
        self,
        offering_id: int,
        effective_from: date,
        effective_to: date | None,
        exclude: CourseProfessor | None = None,
    ) -> list[CourseProfessor]:
        """Return primary assignments overlapping the requested interval.

        At most one primary assignment may cover an offering on any date.
        Assistants may overlap freely, and primary successions are allowed
        when the effective ranges are disjoint (for example, one ends today
        and the next starts tomorrow).
        """
        stmt: Select[tuple[CourseProfessor]] = select(CourseProfessor).where(
            CourseProfessor.offering_id == offering_id,
            CourseProfessor.is_primary.is_(True),
        )

        existing: Sequence[CourseProfessor] = (await self._session.scalars(stmt)).all()
        return [
            e
            for e in existing
            if e is not exclude
            and _overlaps(
                effective_from,
                effective_to,
                e.effective_from,
                e.effective_to,
            )
        ]

    async def ensure_primary_available(
        self,
        offering_id: int,
        effective_from: date,
        effective_to: date | None,
        exclude: CourseProfessor | None = None,
    ) -> None:
        """Raise 409 when another primary assignment overlaps the interval."""
        conflicts: list[CourseProfessor] = await self.check_primary_conflict(
            offering_id,
            effective_from,
            effective_to,
            exclude=exclude,
        )
        if conflicts:
            existing: CourseProfessor = conflicts[0]
            raise PrimaryAssignmentConflictException(
                offering_id,
                effective_from,
                effective_to,
                existing.effective_from,
                existing.effective_to,
            )

    async def create(self, **values) -> CourseProfessor:
        offering_id: int = values["offering_id"]
        professor_id: int = values["professor_id"]
        effective_from: date = values["effective_from"]
        effective_to: date | None = values.get("effective_to")

        if overlap := await self.check_overlap(
            offering_id, professor_id, effective_from, effective_to
        ):
            existing: CourseProfessor = overlap[0]

            raise OverlappingAssignmentException(
                offering_id,
                professor_id,
                effective_from,
                effective_to,
                existing.effective_from,
                existing.effective_to,
            )

        if values.get("is_primary"):
            await self.ensure_primary_available(
                offering_id,
                effective_from,
                effective_to,
            )

        record = CourseProfessor(**values)
        self._session.add(record)
        await self._session.flush()
        return record
