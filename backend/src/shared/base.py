from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase


class BaseCRUD[T: DeclarativeBase]:
    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def create(self, **values: Any) -> T:
        obj: T = self.model(**values)
        self.session.add(obj)
        await self.session.flush()

        return obj

    async def get(self, id: int) -> T | None:
        return await self.session.get(self.model, id)

    async def get_by(self, **filters: Any) -> T | None:
        stmt: Select[tuple[T]] = select(self.model)
        stmt = self._map_filters(stmt, **filters)

        return (await self.session.scalars(stmt)).one_or_none()

    async def list(
        self, offset: int = 0, limit: int = 50, **filters: Any
    ) -> Sequence[T]:
        stmt: Select[tuple[T]] = (
            select(self.model).order_by(self.model.id).offset(offset).limit(limit)
        )
        stmt = self._map_filters(stmt, **filters)

        return (await self.session.scalars(stmt)).all()

    async def count(self, **filters: Any) -> int:
        stmt: Select[tuple[int]] = select(func.count()).select_from(self.model)
        stmt = self._map_filters(stmt, **filters)

        return (await self.session.scalars(stmt)).one()

    async def update(self, id: int, **values: Any) -> T | None:
        obj: T | None = await self.get(id)

        if obj is None:
            return None

        for key, value in values.items():
            setattr(obj, key, value)

        await self.session.flush()
        return obj

    async def delete(self, id: int) -> bool:
        obj: T | None = await self.get(id)

        if obj is None:
            return False

        await self.session.delete(obj)
        await self.session.flush()

        return True

    def _map_filters(self, stmt: Select[Any], **filters: Any) -> Select[Any]:
        if not filters:
            return stmt

        return stmt.where(
            *[getattr(self.model, key) == value for key, value in filters.items()]
        )
