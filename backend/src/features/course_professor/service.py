from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from features.course_professor.exceptions import OverlappingAssignmentException
from features.course_professor.model import CourseProfessor


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
        """Return existing assignments overlapping [effective_from, effective_to]."""
        stmt: Select[tuple[CourseProfessor]] = select(CourseProfessor).where(
            CourseProfessor.offering_id == offering_id,
            CourseProfessor.professor_id == professor_id,
        )

        existing: Sequence[CourseProfessor] = (await self._session.scalars(stmt)).all()
        overlap: list[CourseProfessor] = [
            e
            for e in existing
            if e is not exclude
            and (effective_from < (e.effective_to or date.max))
            and ((e.effective_from) < (effective_to or date.max))
        ]

        return overlap

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

        record = CourseProfessor(**values)
        self._session.add(record)
        await self._session.flush()
        return record
