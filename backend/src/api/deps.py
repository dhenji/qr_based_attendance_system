from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import database


async def get_db() -> AsyncIterator[AsyncSession]:
    async with database.get_session() as session:
        yield session
