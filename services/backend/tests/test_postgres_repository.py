from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import Settings
from aventi_backend.db.repository import PostgresAventiRepository, _canonical_user_uuid
from aventi_backend.models.schemas import FeedImpressionPayload, ProfileLocationPayload, SwipePayload
from aventi_backend.services.ingest import ManualIngestService

TEST_DB_URL = os.getenv(
    'AVENTI_TEST_DATABASE_URL',
    'postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres',
)


@pytest_asyncio.fixture
async def pg_session() -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.connect() as conn:
            count = await conn.scalar(text('select count(*) from public.events'))
            if not count or int(count) < 5:
                pytest.skip('Local Supabase seed data missing. Run `supabase db reset`.')
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f'Local Supabase not available for Postgres repository tests: {exc}')

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def repo_settings() -> Settings:
    settings = Settings()
    settings.env = 'test'
    settings.free_swipe_limit = 10
    return settings


def _feed_kwargs(
    *,
    user_id: str,
    settings: Settings,
    cursor: str | None = None,
    limit: int = 10,
    latitude: float = 30.2672,
    longitude: float = -97.7431,
    radius_miles: float = 25,
    market_city: str | None = 'Austin',
    market_state: str | None = None,
    market_country: str | None = 'US',
) -> dict:
    return {
        'user_id': user_id,
        'settings': settings,
        'date': 'week',
        'latitude': latitude,
        'longitude': longitude,
        'limit': limit,
        'time_of_day': None,
        'price': 'any',
        'radius_miles': radius_miles,
        'cursor': cursor,
        'market_city': market_city,
        'market_state': market_state,
        'market_country': market_country,
    }


def _swipe_payload(event_id: str, action: str, vibes: list[str]) -> SwipePayload:
    return SwipePayload.model_validate(
        {
            'eventId': event_id,
            'action': action,
            'surfacedAt': datetime.now(tz=timezone.utc).isoformat(),
            'position': 0,
            'vibes': vibes,
        }
    )


async def _ingest_visible_event(
    session: AsyncSession,
    *,
    city: str,
    title: str,
    booking_url: str,
    category: str,
    starts_at: str,
    vibes: list[str],
    tags: list[str],
    latitude: float,
    longitude: float,
) -> str:
    summary = await ManualIngestService(session).ingest_manual(
        source_name=f'pytest-feed-{uuid4().hex[:8]}',
        city=city,
        events=[
            {
                'title': title,
                'description': f'Test event for {title}',
                'category': category,
                'bookingUrl': booking_url,
                'startsAt': starts_at,
                'venue': {
                    'name': f'{city} Test Venue {uuid4().hex[:6]}',
                    'city': city,
                    'state': '',
                    'latitude': latitude,
                    'longitude': longitude,
                },
                'vibes': vibes,
                'tags': tags,
            }
        ],
    )
    event_id = summary.event_ids[0]
    await session.execute(
        text(
            """
            update public.events
            set hidden = false,
                verification_status = 'verified',
                verification_fail_count = 0,
                last_verified_at = now(),
                last_verified_active = true,
                updated_at = now()
            where id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    await session.commit()
    return event_id


@pytest.mark.asyncio
async def test_postgres_repo_feed_pagination_and_recent_pass_dedupe(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    market_city = f'Pytest Feed {uuid4().hex[:8]}'
    latitude = -20.6062  # Unique coordinates for this test
    longitude = -12.3321
    event_ids = [
        await _ingest_visible_event(
            pg_session,
            city=market_city,
            title=f'Pagination Event {index}',
            booking_url=f'https://example.com/pagination/{uuid4()}',
            category='experiences',
            starts_at=(datetime.now(tz=timezone.utc) + timedelta(hours=2 + index)).isoformat(),
            vibes=['social'],
            tags=[f'pagination-{index}'],
            latitude=latitude,
            longitude=longitude,
        )
        for index in range(3)
    ]

    first_page = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=2,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    assert len(first_page['items']) == 2
    assert first_page['nextCursor'] is not None
    assert first_page['marketKey'] == f'{market_city.lower()}||us'
    assert first_page['inventoryStatus'] == 'warming'
    assert {item['id'] for item in first_page['items']}.issubset(set(event_ids))

    second_page = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            cursor=first_page['nextCursor'],
            limit=2,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    assert len(second_page['items']) >= 1
    assert {item['id'] for item in first_page['items']}.isdisjoint(
        {item['id'] for item in second_page['items']}
    )
    assert {item['id'] for item in second_page['items']}.issubset(set(event_ids))

    passed_event = first_page['items'][0]
    await repo.record_swipe(
        user_id=user_id,
        email=f'{user_id}@aventi.test',
        payload=_swipe_payload(passed_event['id'], 'pass', passed_event['vibes']),
        settings=repo_settings,
    )

    refreshed = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=10,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    refreshed_ids = [item['id'] for item in refreshed['items']]
    assert passed_event['id'] not in refreshed_ids


@pytest.mark.asyncio
async def test_postgres_repo_persists_vibe_weights_and_reorders_feed(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    email = f'{user_id}@aventi.test'
    market_city = f'Pytest Weights {uuid4().hex[:8]}'
    latitude = 45.5152
    longitude = -122.6784
    target_event_id = await _ingest_visible_event(
        pg_session,
        city=market_city,
        title='Weight Target Event',
        booking_url=f'https://example.com/weights/{uuid4()}',
        category='wellness',
        starts_at=(datetime.now(tz=timezone.utc) + timedelta(hours=2)).isoformat(),
        vibes=['chill', 'wellness'],
        tags=['weight-target'],
        latitude=latitude,
        longitude=longitude,
    )
    await _ingest_visible_event(
        pg_session,
        city=market_city,
        title='Weight Baseline Event',
        booking_url=f'https://example.com/weights/{uuid4()}',
        category='concerts',
        starts_at=(datetime.now(tz=timezone.utc) + timedelta(hours=3)).isoformat(),
        vibes=['social'],
        tags=['weight-baseline'],
        latitude=latitude,
        longitude=longitude,
    )

    baseline = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=10,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    baseline_ids = [item['id'] for item in baseline['items']]
    assert target_event_id in baseline_ids
    baseline_index = baseline_ids.index(target_event_id)

    for _ in range(3):
        await repo.record_swipe(
            user_id=user_id,
            email=email,
            payload=_swipe_payload(target_event_id, 'like', ['chill', 'wellness']),
            settings=repo_settings,
        )

    ranked = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=10,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    ranked_ids = [item['id'] for item in ranked['items']]
    assert target_event_id in ranked_ids
    ranked_index = ranked_ids.index(target_event_id)
    assert ranked_index <= baseline_index

    db_user_id = _canonical_user_uuid(user_id)
    weights_result = await pg_session.execute(
        text(
            """
            select vibe, weight
            from public.user_vibe_weights
            where user_id = :user_id and vibe in ('chill', 'wellness')
            order by vibe
            """
        ),
        {'user_id': db_user_id},
    )
    weights = {str(row[0]): float(row[1]) for row in weights_result.all()}
    assert weights['chill'] > 1.0
    assert weights['wellness'] > 1.0


@pytest.mark.asyncio
async def test_postgres_repo_uses_requested_market_for_warmup(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    email = f'{user_id}@aventi.test'
    market_city = f'Pytest Warmup {uuid4().hex[:8]}'
    market_key = f'{market_city.lower()}||us'

    await repo.update_profile_location(
        user_id,
        email,
        ProfileLocationPayload.model_validate(
            {
                'city': 'Austin',
                'timezone': 'America/Chicago',
                'latitude': 30.2672,
                'longitude': -97.7431,
            }
        ),
    )

    response = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=10,
            market_city=market_city,
            market_country='US',
        )
    )
    assert response['marketKey'] == market_key
    assert response['inventoryStatus'] == 'warming'
    assert response['warmupTriggered'] is True

    queued_job = await pg_session.execute(
        text(
            """
            select payload ->> 'marketCity' as market_city, payload ->> 'marketKey' as market_key
            from public.job_queue
            where job_type = 'MARKET_WARMUP'
              and status in ('queued', 'running')
              and payload ->> 'marketKey' = :market_key
            order by created_at desc
            limit 1
            """
        ),
        {'market_key': market_key},
    )
    row = queued_job.mappings().one()
    assert row['market_city'] == market_city
    assert row['market_key'] == market_key


@pytest.mark.asyncio
async def test_postgres_repo_soft_verification_status_controls_feed_eligibility(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    market_city = f'Pytest Verify {uuid4().hex[:8]}'
    latitude = 39.7392
    longitude = -104.9903
    target_event_id = await _ingest_visible_event(
        pg_session,
        city=market_city,
        title='Verification Lifecycle Event',
        booking_url=f'https://example.com/verification/{uuid4()}',
        category='experiences',
        starts_at=(datetime.now(tz=timezone.utc) + timedelta(hours=2)).isoformat(),
        vibes=['social'],
        tags=['verification-test'],
        latitude=latitude,
        longitude=longitude,
    )

    await pg_session.execute(
        text(
            """
            update public.events
            set hidden = false,
                verification_status = 'suspect',
                verification_fail_count = 1,
                last_verified_at = now(),
                last_verified_active = false,
                updated_at = now()
            where id = :event_id
            """
        ),
        {'event_id': target_event_id},
    )
    await pg_session.commit()

    suspect_feed = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=20,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    assert target_event_id in [item['id'] for item in suspect_feed['items']]

    await pg_session.execute(
        text(
            """
            update public.events
            set verification_status = 'inactive',
                verification_fail_count = 2,
                last_verified_at = now(),
                last_verified_active = false,
                updated_at = now()
            where id = :event_id
            """
        ),
        {'event_id': target_event_id},
    )
    await pg_session.commit()

    inactive_feed = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            limit=20,
            latitude=latitude,
            longitude=longitude,
            radius_miles=5,
            market_city=market_city,
        )
    )
    assert target_event_id not in [item['id'] for item in inactive_feed['items']]


@pytest.mark.asyncio
async def test_postgres_repo_records_feed_impression(pg_session: AsyncSession) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    email = f'{user_id}@aventi.test'
    event_id = '10000000-0000-0000-0000-000000000001'

    await repo.record_feed_impression(
        user_id=user_id,
        email=email,
        payload=FeedImpressionPayload.model_validate(
            {
                'eventId': event_id,
                'servedAt': datetime.now(tz=timezone.utc).isoformat(),
                'position': 3,
                'filters': {'date': 'week', 'price': 'any'},
            }
        ),
    )

    db_user_id = _canonical_user_uuid(user_id)
    count = await pg_session.scalar(
        text(
            """
            select count(*)
            from public.feed_impressions
            where user_id = :user_id and event_id = :event_id
            """
        ),
        {'user_id': db_user_id, 'event_id': event_id},
    )
    assert int(count or 0) >= 1
