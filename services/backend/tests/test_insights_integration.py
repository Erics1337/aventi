import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import Settings
from aventi_backend.db.repository import PostgresAventiRepository
from aventi_backend.services.insights import InsightsService

pytestmark = pytest.mark.skipif(
    not os.environ.get("AVENTI_TEST_DATABASE_URL"), reason="Disposable database required"
)


class Selector:
    async def select(self, *, facts, compatible_events, preferences):
        return {
            "factIds": ["admission", "invented"],
            "compatibleEventIds": [item["eventId"] for item in compatible_events] + ["not-real"],
        }


async def test_insights_filter_pairings_and_revalidate_cached_cancellations():
    engine = create_async_engine(os.environ["AVENTI_TEST_DATABASE_URL"], poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        AVENTI_ENV="test",
        AVENTI_PAID_DISCOVERY_ENABLED=True,
        AVENTI_PROVIDER_DAILY_BUDGETS={"pollinations": 100},
        AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD=100,
        AVENTI_PROVIDER_MAX_COST_MICROUSD={"pollinations": 1},
    )
    user, venue = str(uuid4()), str(uuid4())
    events = [str(uuid4()) for _ in range(5)]
    start = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    try:
        async with factory() as session:
            await session.execute(text("delete from provider_daily_usage"))
            await session.execute(text("delete from provider_monthly_usage"))
            await PostgresAventiRepository(session).bootstrap_user(user, None)
            await session.execute(
                text(
                    "update profiles set latitude=40.7,longitude=-74,timezone='America/New_York' where id=:id"
                ),
                {"id": user},
            )
            await session.execute(
                text(
                    "update premium_entitlements set is_premium=true,valid_until=now()+interval '1 day' where user_id=:id"
                ),
                {"id": user},
            )
            await session.execute(
                text(
                    "insert into venues(id,name,city,state,country,latitude,longitude) values (:id,'Insight venue','New York','NY','US',40.7,-74)"
                ),
                {"id": venue},
            )
            for index, event in enumerate(events):
                await session.execute(
                    text("""insert into events(id,venue_id,title,category,booking_url,verification_status,last_verified_active,last_verified_at,admission_restriction,admission_source_url)
                    values (:id,:venue,:title,'concerts',:url,'verified',true,:verified,:age,:url)"""),
                    {
                        "id": event,
                        "venue": venue,
                        "title": f"Insight {event}",
                        "url": f"https://example.com/{event}",
                        "verified": datetime.now(UTC) - timedelta(hours=80 if index == 3 else 1),
                        "age": "18+" if index == 2 else "21+",
                    },
                )
                when = start + timedelta(hours=2 if index else 0)
                await session.execute(
                    text(
                        "insert into event_occurrences(event_id,starts_at,ends_at,timezone,cancelled) values (:id,:start,:end,'America/New_York',:cancelled)"
                    ),
                    {
                        "id": event,
                        "start": when,
                        "end": when + timedelta(hours=1),
                        "cancelled": index == 4,
                    },
                )
            await session.commit()
            service = InsightsService(session, settings=settings, selector=Selector())
            filters = {"radiusMiles": 10, "ageRestriction": "21+"}
            result = await service.get_or_enqueue(user_id=user, event_id=events[0], filters=filters)
            assert result["status"] == "pending"
            job = (
                await session.execute(
                    text("select payload from jobs where id=:id"), {"id": result["jobId"]}
                )
            ).scalar_one()
            payload = await service.generate_and_cache(
                events[0], context_hash=job["contextHash"], context=job["context"]
            )
            assert [item["eventId"] for item in payload["compatibleEvents"]] == [events[1]]
            assert payload["insiderTips"] == ["Listed admission restriction: 21+."]
            await session.execute(
                text("update event_occurrences set cancelled=true where event_id=:id"),
                {"id": events[1]},
            )
            await session.commit()
            cached = await service.get_or_enqueue(user_id=user, event_id=events[0], filters=filters)
            assert cached["status"] == "ready"
            assert cached["insight"]["compatibleEvents"] == []
    finally:
        await engine.dispose()
