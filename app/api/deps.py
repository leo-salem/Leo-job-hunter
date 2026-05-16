from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope


async def db() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


SessionDep = Depends(db)
