import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import Settings
from aventi_backend.services.budgets import BudgetError, BudgetManager
from aventi_backend.services.jobs import JobQueueRepository, JobType

URL = os.environ.get("AVENTI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires disposable migrated database")


@pytest.fixture
async def sessions():
    engine = create_async_engine(URL, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_provider_cap_is_atomic(sessions):
    async with sessions() as s:
        await s.execute(
            text("delete from provider_daily_usage where provider in ('images','pollinations')")
        )
        await s.execute(text("delete from provider_monthly_usage"))
        await s.commit()
    settings = Settings(
        _env_file=None,
        AVENTI_ENV="test",
        AVENTI_PAID_DISCOVERY_ENABLED=True,
        AVENTI_PROVIDER_DAILY_BUDGETS={"images": 20, "pollinations": 20},
        AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD=14,
        AVENTI_PROVIDER_MAX_COST_MICROUSD={"images": 2, "pollinations": 2},
    )

    async def reserve(provider):
        async with sessions() as s:
            try:
                await BudgetManager(s, settings=settings).reserve(provider)
                return True
            except BudgetError:
                return False

    results = await asyncio.gather(
        *[reserve("images" if index % 2 else "pollinations") for index in range(20)]
    )
    assert sum(results) == 7


async def test_outbox_is_not_visible_before_commit_and_duplicate_claim_is_busy(sessions):
    async with sessions() as writer:
        repo = JobQueueRepository(writer)
        job = await repo.enqueue_job(JobType.VERIFY_EVENT, {"eventId": str(uuid4())})
        async with sessions() as reader:
            assert (
                await reader.scalar(
                    text("select count(*) from job_outbox where job_id=:id"), {"id": job.id}
                )
                == 0
            )
        await writer.commit()
        async with sessions() as reader:
            assert (
                await reader.scalar(
                    text("select count(*) from job_outbox where job_id=:id"), {"id": job.id}
                )
                == 1
            )
            claim = await JobQueueRepository(reader).claim_job(job.id, worker_id="one")
            assert claim.outcome == "claimed"
        async with sessions() as reader:
            assert (
                await JobQueueRepository(reader).claim_job(job.id, worker_id="two")
            ).outcome == "busy"


async def test_market_admission_caps_new_jobs_and_cooldown_replays(sessions, monkeypatch):
    from aventi_backend.services.market_inventory import (
        MarketWarmupService,
        build_market_descriptor,
    )

    async with sessions() as session:
        await session.execute(text("delete from provider_daily_usage"))
        await session.execute(text("delete from provider_monthly_usage"))
        await session.commit()

    settings = Settings(
        _env_file=None,
        AVENTI_ENV="test",
        AVENTI_PAID_DISCOVERY_ENABLED=True,
        AVENTI_PROVIDER_DAILY_BUDGETS={"serpapi": 100},
        AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD=100,
        AVENTI_PROVIDER_MAX_COST_MICROUSD={"serpapi": 1},
    )
    monkeypatch.setattr("aventi_backend.services.budgets.get_settings", lambda: settings)
    identity = f"quota-test:{uuid4()}"
    markets = [
        build_market_descriptor(
            city=f"Test {uuid4()}",
            state="NY",
            country="US",
            center_latitude=40.7,
            center_longitude=-74,
        )
        for _ in range(8)
    ]
    outcomes = []
    for market in markets:
        async with sessions() as session:
            outcome = await MarketWarmupService(session).request_warmup(
                market, visible_count=0, admission_limits=[(identity, 6)]
            )
            await session.commit()
            outcomes.append(outcome)
    assert sum(outcome[2] for outcome in outcomes) == 6
    assert [outcome[1] for outcome in outcomes[-2:]] == ["unavailable", "unavailable"]
    async with sessions() as session:
        outcome = await MarketWarmupService(session).request_warmup(
            markets[0], visible_count=0, force_refresh=True, admission_limits=[(identity, 6)]
        )
        assert outcome[2] is False
        assert outcome[1] == "warming"


async def test_final_attempt_crash_terminalizes_and_releases_dedup(sessions):
    async with sessions() as session:
        repo = JobQueueRepository(session)
        payload = {"eventId": str(uuid4())}
        job = await repo.enqueue_job(JobType.VERIFY_EVENT, payload, max_attempts=1)
        await session.commit()
        assert (await repo.claim_job(job.id, worker_id="crashed")).outcome == "claimed"
        # A live final attempt is not killed by duplicate delivery.
        assert (await repo.claim_job(job.id, worker_id="duplicate")).outcome == "exhausted"
        assert (
            await session.scalar(text("select status from jobs where id=:id"), {"id": job.id})
            == "processing"
        )
        await session.execute(
            text("update jobs set lease_expires_at=now()-interval '1 second' where id=:id"),
            {"id": job.id},
        )
        await session.commit()
        assert (await repo.claim_job(job.id, worker_id="retry")).outcome == "exhausted"
        row = (
            (
                await session.execute(
                    text(
                        "select status, dedup_key, locked_by, completed_at from jobs where id=:id"
                    ),
                    {"id": job.id},
                )
            )
            .mappings()
            .one()
        )
        assert row["status"] == "dead" and row["dedup_key"] is None and row["locked_by"] is None
        assert row["completed_at"] is not None
        replacement = await repo.enqueue_job(JobType.VERIFY_EVENT, payload)
        assert replacement.id != job.id
        await session.commit()
