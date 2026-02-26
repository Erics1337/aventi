from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import get_settings

_settings = get_settings()
_engine = (
    create_async_engine(_settings.database_url, pool_pre_ping=True, poolclass=NullPool)
    if _settings.database_url
    else None
)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False) if _engine is not None else None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("AVENTI_DATABASE_URL is not configured")
    async with _session_factory() as session:
        yield session


async def get_optional_db_session() -> AsyncIterator[AsyncSession | None]:
    if _session_factory is None:
        yield None
        return
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def open_db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("AVENTI_DATABASE_URL is not configured")
    async with _session_factory() as session:
        yield session
