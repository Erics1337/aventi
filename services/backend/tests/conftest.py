from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.services.jobs import JobQueueRepository, JobRecord, JobType

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres"


@pytest.fixture
def fake_job_queue(monkeypatch: pytest.MonkeyPatch) -> list[JobRecord]:
    jobs: list[JobRecord] = []

    async def enqueue_job(
        self: JobQueueRepository,
        job_type: JobType,
        payload: dict | None = None,
        *,
        run_at: datetime | None = None,
        max_attempts: int = 5,
        scheduler_run_id: str | None = None,
    ) -> JobRecord:
        job = JobRecord(
            id=f"fake-job-{len(jobs) + 1}",
            type=job_type,
            payload=payload or {},
            run_at=run_at or datetime.now(tz=UTC),
            max_attempts=max_attempts,
            scheduler_run_id=scheduler_run_id,
        )
        jobs.append(job)
        return job

    monkeypatch.setattr(JobQueueRepository, "enqueue_job", enqueue_job)
    return jobs


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    url = (
        os.environ.get("AVENTI_TEST_DATABASE_URL")
        or os.environ.get("AVENTI_DATABASE_URL")
        or TEST_DATABASE_URL
    )
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"local integration database is not available: {exc}")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
