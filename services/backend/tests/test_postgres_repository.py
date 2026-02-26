from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.core.settings import Settings
from aventi_backend.db.repository import PostgresAventiRepository, _canonical_user_uuid
from aventi_backend.models.schemas import FeedImpressionPayload, SwipePayload

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


def _feed_kwargs(*, user_id: str, settings: Settings, cursor: str | None = None, limit: int = 10) -> dict:
    return {
        'user_id': user_id,
        'settings': settings,
        'date': 'week',
        'latitude': 30.2672,
        'longitude': -97.7431,
        'limit': limit,
        'time_of_day': None,
        'price': 'any',
        'radius_miles': 25,
        'cursor': cursor,
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


@pytest.mark.asyncio
async def test_postgres_repo_feed_pagination_and_recent_pass_dedupe(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())

    first_page = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=repo_settings, limit=2))
    assert len(first_page['items']) == 2
    assert first_page['nextCursor'] is not None

    second_page = await repo.get_feed(
        **_feed_kwargs(
            user_id=user_id,
            settings=repo_settings,
            cursor=first_page['nextCursor'],
            limit=2,
        )
    )
    assert len(second_page['items']) >= 1
    assert {item['id'] for item in first_page['items']}.isdisjoint(
        {item['id'] for item in second_page['items']}
    )

    passed_event = first_page['items'][0]
    await repo.record_swipe(
        user_id=user_id,
        email=f'{user_id}@aventi.test',
        payload=_swipe_payload(passed_event['id'], 'pass', passed_event['vibes']),
        settings=repo_settings,
    )

    refreshed = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=repo_settings, limit=10))
    refreshed_ids = [item['id'] for item in refreshed['items']]
    assert passed_event['id'] not in refreshed_ids


@pytest.mark.asyncio
async def test_postgres_repo_persists_vibe_weights_and_reorders_feed(
    pg_session: AsyncSession, repo_settings: Settings
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    email = f'{user_id}@aventi.test'
    target_event_id = '10000000-0000-0000-0000-000000000002'  # chill + wellness

    baseline = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=repo_settings, limit=10))
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

    ranked = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=repo_settings, limit=10))
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
async def test_postgres_repo_excludes_stale_unverified_events_until_recent_verification(
    pg_session: AsyncSession,
) -> None:
    repo = PostgresAventiRepository(pg_session)
    user_id = str(uuid4())
    target_event_id = '10000000-0000-0000-0000-000000000001'
    strict_settings = Settings()
    strict_settings.env = 'test'
    strict_settings.free_swipe_limit = 10
    strict_settings.feed_verification_max_age_hours = 2
    strict_settings.feed_unverified_grace_hours = 1

    await pg_session.execute(
        text(
            """
            delete from public.verification_runs
            where event_id = :event_id
            """
        ),
        {'event_id': target_event_id},
    )
    await pg_session.execute(
        text(
            """
            update public.events
            set hidden = false,
                created_at = now() - interval '7 days',
                updated_at = now()
            where id = :event_id
            """
        ),
        {'event_id': target_event_id},
    )
    await pg_session.commit()

    no_verification = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=strict_settings, limit=20))
    assert target_event_id not in [item['id'] for item in no_verification['items']]

    await pg_session.execute(
        text(
            """
            insert into public.verification_runs (event_id, status, verified_at, active, details)
            values (:event_id, 'active', :verified_at, true, '{}'::jsonb)
            """
        ),
        {'event_id': target_event_id, 'verified_at': datetime.now(tz=UTC) - timedelta(hours=4)},
    )
    await pg_session.commit()

    stale_verification = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=strict_settings, limit=20))
    assert target_event_id not in [item['id'] for item in stale_verification['items']]

    await pg_session.execute(
        text(
            """
            insert into public.verification_runs (event_id, status, verified_at, active, details)
            values (:event_id, 'active', :verified_at, true, '{}'::jsonb)
            """
        ),
        {'event_id': target_event_id, 'verified_at': datetime.now(tz=UTC)},
    )
    await pg_session.commit()

    fresh_verification = await repo.get_feed(**_feed_kwargs(user_id=user_id, settings=strict_settings, limit=20))
    assert target_event_id in [item['id'] for item in fresh_verification['items']]


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
