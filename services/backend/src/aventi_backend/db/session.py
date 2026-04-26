from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import get_settings

_settings = get_settings()

# Supabase's transaction-mode pooler (port 6543) multiplexes connections via
# pgbouncer, which does NOT support prepared statements. asyncpg caches them
# by default, which produces DuplicatePreparedStatementError on reused
# connections. Disable the caches to stay compatible with the pooler while
# still using asyncpg for speed.
_asyncpg_kwargs: dict = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
}

_engine = (
    create_async_engine(
        _settings.database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=_asyncpg_kwargs,
    )
    if _settings.database_url
    else None
)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False) if _engine is not None else None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("AVENTI_DATABASE_URL is not configured")
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def open_db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("AVENTI_DATABASE_URL is not configured")
    async with _session_factory() as session:
        yield session
