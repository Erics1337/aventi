"""Run against a disposable migrated database, never an application database."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import Settings
from aventi_backend.db.repository import PostgresAventiRepository
from aventi_backend.models.schemas import SwipePayload

URL = os.environ.get("AVENTI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="AVENTI_TEST_DATABASE_URL requires disposable migrated database"
)


@pytest.fixture
async def database():
    engine = create_async_engine(URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def populate(factory, count=12):
    user = str(uuid4())
    venue = str(uuid4())
    events = []
    async with factory() as s:
        await PostgresAventiRepository(s).bootstrap_user(user, None)
        await s.execute(
            text(
                "update profiles set latitude=40.7128,longitude=-74.006,timezone='America/New_York' where id=:id"
            ),
            {"id": user},
        )
        await s.execute(
            text(
                "insert into venues(id,name,city,state,country,latitude,longitude) values (:id,'Test Venue','New York','NY','US',40.7128,-74.006)"
            ),
            {"id": venue},
        )
        for i in range(count):
            eid = str(uuid4())
            events.append(eid)
            await s.execute(
                text(
                    "insert into events(id,venue_id,title,category,booking_url,verification_status,last_verified_at,last_verified_active) values (:id,:venue,:title,'concerts',:url,'verified',now(),true)"
                ),
                {
                    "id": eid,
                    "venue": venue,
                    "title": f"Test {eid}",
                    "url": f"https://example.com/{eid}",
                },
            )
            await s.execute(
                text(
                    "insert into event_occurrences(event_id,starts_at,timezone) values (:id,:starts,'America/New_York')"
                ),
                {"id": eid, "starts": datetime.now(UTC) + timedelta(hours=4, minutes=i)},
            )
        await s.commit()
    return user, events


async def feed(factory, user, **kwargs):
    async with factory() as s:
        return await PostgresAventiRepository(s).get_feed(
            user_id=user,
            settings=Settings(_env_file=None, AVENTI_ENV="test"),
            date="week",
            latitude=40.7128,
            longitude=-74.006,
            limit=2,
            time_of_day=None,
            price=None,
            radius_miles=10,
            selected_vibes=[],
            categories=[],
            cursor=kwargs.get("cursor"),
            market_city="New York",
            market_state="NY",
            market_country="US",
        )


async def test_database_roles_cannot_read_or_write_domain_tables(database):
    async with database() as s:
        for role in ["anon", "authenticated"]:
            assert not await s.scalar(
                text("select has_table_privilege(:role,'public.events','INSERT')"), {"role": role}
            )
            assert not await s.scalar(
                text("select has_table_privilege(:role,'public.feed_impressions','SELECT')"),
                {"role": role},
            )
            assert not await s.scalar(
                text("select has_table_privilege(:role,'public.swipe_actions','DELETE')"),
                {"role": role},
            )


async def test_concurrent_allowance_and_idempotency(database):
    user, events = await populate(database)
    action = SwipePayload(
        actionId=uuid4(),
        eventId=events[0],
        action="like",
        surfacedAt=datetime.now(UTC),
        position=0,
        vibes=[],
    )

    async def swipe(payload):
        async with database() as s:
            try:
                return await PostgresAventiRepository(s).record_swipe(
                    user_id=user,
                    email=None,
                    payload=payload,
                    settings=Settings(_env_file=None, AVENTI_ENV="test"),
                )
            except PermissionError:
                return None

    results = await asyncio.gather(*[swipe(action) for _ in range(4)])
    assert all(r == results[0] for r in results)
    more = await asyncio.gather(
        *[
            swipe(
                SwipePayload(
                    actionId=uuid4(),
                    eventId=e,
                    action="pass",
                    surfacedAt=datetime.now(UTC),
                    position=0,
                    vibes=[],
                )
            )
            for e in events[1:]
        ]
    )
    assert sum(r is not None for r in more) == 9
    async with database() as s:
        assert (
            await s.scalar(
                text("select count(*) from swipe_actions where user_id=:id"), {"id": user}
            )
            == 10
        )
        assert (
            await s.scalar(text("select count(*) from favorites where user_id=:id"), {"id": user})
            == 1
        )


async def test_location_filter_precedes_candidate_limit_and_snapshot_is_user_bound(database):
    user, events = await populate(database, 4)
    async with database() as s:
        venue = str(uuid4())
        await s.execute(
            text(
                "insert into venues(id,name,city,country,latitude,longitude) values (:id,'Distant','Los Angeles','US',34.05,-118.24)"
            ),
            {"id": venue},
        )
        for _ in range(105):
            eid = str(uuid4())
            await s.execute(
                text(
                    "insert into events(id,venue_id,title,category,booking_url,verification_status,last_verified_at,last_verified_active) values (:id,:venue,:title,'concerts',:url,'verified',now(),true)"
                ),
                {"id": eid, "venue": venue, "title": eid, "url": f"https://example.com/{eid}"},
            )
            await s.execute(
                text(
                    "insert into event_occurrences(event_id,starts_at,timezone) values (:id,now()+interval '1 hour','America/Los_Angeles')"
                ),
                {"id": eid},
            )
        await s.commit()
    first = await feed(database, user)
    assert len(first["items"]) == 2
    assert all(item["city"] == "New York" for item in first["items"])
    second = await feed(database, user, cursor=first["nextCursor"])
    assert not ({e["id"] for e in first["items"]} & {e["id"] for e in second["items"]})
    other, _ = await populate(database, 1)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        await feed(database, other, cursor=first["nextCursor"])
    assert err.value.status_code == 410


async def test_swipe_failure_rolls_back_allowance_and_favorite(database, monkeypatch):
    user, events = await populate(database, 1)
    async with database() as s:
        await s.execute(
            text("insert into event_tags(event_id,tag,tag_type) values (:id,'social','vibe')"),
            {"id": events[0]},
        )
        await s.commit()

    def fail_personalization(*args):
        raise RuntimeError("Injected personalization failure")

    monkeypatch.setattr("aventi_backend.db.repository.apply_vibe_update", fail_personalization)
    with pytest.raises(RuntimeError, match="Injected"):
        async with database() as s:
            await PostgresAventiRepository(s).record_swipe(
                user_id=user,
                email=None,
                settings=Settings(_env_file=None, AVENTI_ENV="test"),
                payload=SwipePayload(
                    actionId=uuid4(),
                    eventId=events[0],
                    action="like",
                    surfacedAt=datetime.now(UTC),
                    position=0,
                    vibes=[],
                ),
            )
    async with database() as s:
        assert (
            await s.scalar(
                text("select count(*) from swipe_actions where user_id=:id"), {"id": user}
            )
            == 0
        )
        assert (
            await s.scalar(text("select count(*) from favorites where user_id=:id"), {"id": user})
            == 0
        )


async def test_budget_pause_keeps_cached_feed_and_reset_time(database):
    user, _ = await populate(database, 1)
    result = await feed(database, user)
    assert result["items"]
    assert result["inventoryStatus"] == "budget_paused"
    # Paid processing is disabled in this fixture, so no time-based reset can
    # make the unconfigured providers available.
    assert result["retryAt"] is None
    assert result["warmupTriggered"] is False


async def test_unknown_verification_is_excluded_and_free_premium_request_rejected(database):
    user, events = await populate(database, 1)
    async with database() as s:
        await s.execute(
            text("update events set last_verified_active=null where id=:id"), {"id": events[0]}
        )
        await s.commit()
    from fastapi import HTTPException

    async with database() as s:
        with pytest.raises(HTTPException) as error:
            await PostgresAventiRepository(s).record_swipe(
                user_id=user,
                email=None,
                settings=Settings(_env_file=None, AVENTI_ENV="test"),
                payload=SwipePayload(
                    actionId=uuid4(),
                    eventId=events[0],
                    action="like",
                    surfacedAt=datetime.now(UTC),
                    position=0,
                    vibes=[],
                ),
            )
        assert error.value.status_code == 409
    async with database() as s:
        with pytest.raises(HTTPException) as error:
            await PostgresAventiRepository(s).get_feed(
                user_id=user,
                settings=Settings(_env_file=None, AVENTI_ENV="test"),
                date="week",
                latitude=40.7,
                longitude=-74,
                limit=2,
                time_of_day=None,
                price=None,
                radius_miles=25,
                selected_vibes=[],
                categories=[],
                cursor=None,
                market_city="New York",
                market_state="NY",
                market_country="US",
            )
        assert error.value.status_code == 403


async def test_all_domain_tables_are_backend_only(database):
    async with database() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "select c.oid,c.relname,c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r'"
                    )
                )
            )
            .mappings()
            .all()
        )
        for table in rows:
            assert table["relrowsecurity"], table["relname"]
            for role in ["anon", "authenticated"]:
                assert not await session.scalar(
                    text(
                        "select has_table_privilege(:role,cast(:oid as oid),'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"
                    ),
                    {"role": role, "oid": table["oid"]},
                ), (role, table["relname"])


async def test_parallel_legacy_favorite_saves_charge_once(database):
    user, events = await populate(database, 1)

    async def save():
        async with database() as session:
            return await PostgresAventiRepository(session).save_favorite(user, events[0])

    results = await asyncio.gather(*[save() for _ in range(4)])
    assert all(result["favorite"] for result in results)
    async with database() as session:
        assert (
            await session.scalar(
                text("select count(*) from swipe_actions where user_id=:id"), {"id": user}
            )
            == 1
        )
