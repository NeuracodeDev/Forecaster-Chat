from __future__ import annotations

import os
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DATABASE_URL = "postgresql+asyncpg://forecaster:forecaster@db:5432/forecaster"

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        _engine = create_async_engine(database_url, echo=False, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async_session = get_session_factory()
    async with async_session() as session:
        yield session


__all__ = ["get_engine", "get_session_factory", "get_session", "DEFAULT_DATABASE_URL"]

