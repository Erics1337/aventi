from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.market_descriptors import MarketDescriptor
from aventi_backend.services.market_inventory import (
    ELIGIBLE_VERIFICATION_STATUSES,
    HEAT_HOT_MIN_USERS_7D,
    HEAT_WARM_WINDOW,
    MARKET_ACTIVE_WINDOW,
    MarketWarmupService,
)
from aventi_backend.services.market_inventory_state import MarketInventoryStateStore


def _store(session: AsyncSession) -> MarketInventoryStateStore:
    return MarketInventoryStateStore(
        session,
        active_window=MARKET_ACTIVE_WINDOW,
        heat_warm_window=HEAT_WARM_WINDOW,
        hot_min_users_7d=HEAT_HOT_MIN_USERS_7D,
        eligible_verification_statuses=ELIGIBLE_VERIFICATION_STATUSES,
    )


def _market(suffix: str) -> MarketDescriptor:
    return MarketDescriptor(
        key=f"integration-state-{suffix}|co|us",
        city=f"Integration State {suffix}",
        state="CO",
        country="US",
        center_latitude=39.7392,
        center_longitude=-104.9903,
    )


@pytest.mark.integration
async def test_market_inventory_state_bootstrap_activity_lock_and_targeted_state(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex[:12]
    market = _market(suffix)
    store = _store(db_session)

    try:
        assert await store.bootstrap_market_if_new(market) is True
        assert await store.bootstrap_market_if_new(market) is False

        stored = await store.get_market_by_key(market.key)
        assert stored is not None
        assert stored.city == market.city
        assert stored.heat_tier == "warm"

        active_markets = await store.list_active_markets(limit=500)
        assert market.key in {active.key for active in active_markets}

        await store.upsert_market_state(
            market,
            scan_lock_until=datetime.now(tz=UTC) + timedelta(minutes=5),
        )
        locked_markets = await store.list_active_markets(limit=500)
        assert market.key not in {active.key for active in locked_markets}
        assert await store.has_active_discovery_jobs(market.key) is True

        await store.upsert_market_state(
            market,
            scan_lock_until=datetime.now(tz=UTC) - timedelta(minutes=1),
            last_targeted_filter_signature="sig-1",
            last_targeted_requested_at=datetime.now(tz=UTC),
            last_targeted_completed_at=None,
        )
        targeted = await store.targeted_mining_state(market.key)
        assert targeted is not None
        assert targeted["last_targeted_filter_signature"] == "sig-1"
        assert targeted["last_targeted_requested_at"] is not None
        assert targeted["last_targeted_completed_at"] is None

        await store.mark_user_active(market)
        row = (
            await db_session.execute(
                text(
                    """
                    select heat_tier, last_user_active_at
                    from public.market_inventory_state
                    where market_key = :market_key
                    """
                ),
                {"market_key": market.key},
            )
        ).mappings().one()
        assert row["heat_tier"] == "warm"
        assert row["last_user_active_at"] is not None
    finally:
        await db_session.execute(
            text("delete from public.market_inventory_state where market_key = :market_key"),
            {"market_key": market.key},
        )
        await db_session.commit()


@pytest.mark.integration
async def test_targeted_mining_warmup_path_dedupes_in_progress_and_recent_completion(
    db_session: AsyncSession,
    fake_job_queue: list[JobRecord],
) -> None:
    suffix = uuid4().hex[:12]
    market = _market(suffix)
    service = MarketWarmupService(db_session)

    try:
        status, triggered = await service.request_targeted_mining(
            market,
            filters={"date": "week", "categories": ["concerts"]},
            latitude=39.7392,
            longitude=-104.9903,
        )

        assert status == "targeted_warming"
        assert triggered is True
        assert len(fake_job_queue) == 1
        assert fake_job_queue[0].type is JobType.MARKET_SCAN
        signature = str(fake_job_queue[0].payload["filterSignature"])

        duplicate_status, duplicate_triggered = await service.request_targeted_mining(
            market,
            filters={"categories": ["concerts"], "date": "week"},
            latitude=39.7392,
            longitude=-104.9903,
        )

        assert duplicate_status == "targeted_warming"
        assert duplicate_triggered is False
        assert len(fake_job_queue) == 1

        await service.mark_targeted_mining_completed(
            market,
            filter_signature=signature,
        )
        completed_status, completed_triggered = await service.request_targeted_mining(
            market,
            filters={"date": "week", "categories": ["concerts"]},
            latitude=39.7392,
            longitude=-104.9903,
        )

        assert completed_status == "no_matches"
        assert completed_triggered is False
        assert len(fake_job_queue) == 1
    finally:
        await db_session.execute(
            text("delete from public.market_inventory_state where market_key = :market_key"),
            {"market_key": market.key},
        )
        await db_session.commit()
