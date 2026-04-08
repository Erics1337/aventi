from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.verification import VerificationService
from aventi_backend.worker.handlers import process_job

TEST_DB_URL = os.getenv(
    'AVENTI_TEST_DATABASE_URL',
    'postgresql+asyncpg://postgres:postgres@127.0.0.1:54332/postgres',
)


@pytest_asyncio.fixture
async def pg_session_jobs() -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.connect() as conn:
            await conn.execute(text('select 1'))
            count = await conn.scalar(text('select count(*) from public.events'))
            if not count or int(count) < 1:
                pytest.skip('Local Supabase schema/seed missing. Run `supabase db reset`.')
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f'Local Supabase not available for job/ingest tests: {exc}')

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_job_queue_lifecycle_persists_claim_and_run_status(pg_session_jobs: AsyncSession) -> None:
    repo = JobQueueRepository(pg_session_jobs)
    test_id = str(uuid4())
    stale_run_at = datetime.now(tz=UTC) - timedelta(days=30)

    queued_ok = await repo.enqueue_job(
        JobType.CITY_SCAN,
        {"testRunId": test_id, "city": "Austin"},
        run_at=stale_run_at,
    )
    queued_fail = await repo.enqueue_job(
        JobType.VERIFY_EVENT,
        {"testRunId": test_id, "eventId": '10000000-0000-0000-0000-000000000001'},
        max_attempts=1,
        run_at=stale_run_at,
    )

    claimed = await repo.claim_due_jobs(worker_name='pytest-worker', limit=500)
    ours = [job for job in claimed if job.payload.get('testRunId') == test_id]
    assert len(ours) == 2
    for job in ours:
        assert job.run_id is not None
        assert job.attempts == 1
        assert job.locked_by == 'pytest-worker'

    complete_job = next(job for job in ours if job.id == queued_ok.id)
    failed_job = next(job for job in ours if job.id == queued_fail.id)

    await repo.mark_complete(complete_job.id, run_id=complete_job.run_id)
    await repo.mark_failed(failed_job.id, 'intentional test failure', run_id=failed_job.run_id)

    queue_rows = await pg_session_jobs.execute(
        text(
            """
            select id::text as id, status, attempts, last_error
            from public.job_queue
            where id in (:job_a, :job_b)
            order by id
            """
        ),
        {"job_a": queued_ok.id, "job_b": queued_fail.id},
    )
    queue_by_id = {str(row[0]): {"status": row[1], "attempts": int(row[2]), "last_error": row[3]} for row in queue_rows.all()}
    assert queue_by_id[queued_ok.id]["status"] == 'done'
    assert queue_by_id[queued_fail.id]["status"] == 'failed'
    assert 'intentional test failure' in (queue_by_id[queued_fail.id]["last_error"] or '')

    run_rows = await pg_session_jobs.execute(
        text(
            """
            select id::text as id, status
            from public.job_runs
            where id in (:run_a, :run_b)
            """
        ),
        {"run_a": complete_job.run_id, "run_b": failed_job.run_id},
    )
    run_status = {str(row[0]): str(row[1]) for row in run_rows.all()}
    assert run_status[str(complete_job.run_id)] == 'completed'
    assert run_status[str(failed_job.run_id)] == 'failed'


class AlwaysInactiveVerifier:
    async def verify_booking_url(self, url: str) -> bool | None:
        _ = url
        return False


class IndeterminateVerifier:
    async def verify_booking_url(self, url: str) -> bool | None:
        _ = url
        return None


@pytest.mark.asyncio
async def test_manual_ingest_is_idempotent_and_verification_soft_gates_inactive_event(
    pg_session_jobs: AsyncSession,
) -> None:
    ingest = ManualIngestService(pg_session_jobs)
    unique = str(uuid4())
    booking_url = f'https://example.com/real-data-smoke/{unique}'
    starts_at = (datetime.now(tz=UTC) + timedelta(days=1)).isoformat()

    payload = {
        'title': f'Aventi Test Event {unique[:8]}',
        'description': 'Manual ingest test payload',
        'category': 'experiences',
        'bookingUrl': booking_url,
        'startsAt': starts_at,
        'venue': {
            'name': f'Aventi Test Venue {unique[:8]}',
            'address': '123 Test St',
            'city': 'Austin',
            'state': 'TX',
            'latitude': 30.2672,
            'longitude': -97.7431,
        },
        'vibes': ['social', 'energetic'],
        'tags': ['manual-test', unique[:8]],
    }

    first = await ingest.ingest_manual(
        source_name=f'pytest-manual-{unique[:8]}',
        city='Austin',
        events=[payload],
    )
    second = await ingest.ingest_manual(
        source_name=f'pytest-manual-{unique[:8]}',
        city='Austin',
        events=[payload],
    )

    assert first.inserted_events == 1
    assert second.inserted_events == 0
    assert second.updated_events == 1
    assert len(first.event_ids) == 1
    event_id = first.event_ids[0]

    event_count = await pg_session_jobs.scalar(
        text('select count(*) from public.events where booking_url = :booking_url'),
        {'booking_url': booking_url},
    )
    occurrence_count = await pg_session_jobs.scalar(
        text('select count(*) from public.event_occurrences where event_id = :event_id'),
        {'event_id': event_id},
    )
    vibe_tag_count = await pg_session_jobs.scalar(
        text(
            """
            select count(*) from public.event_tags
            where event_id = :event_id and tag_type = 'vibe' and tag in ('social', 'energetic')
            """
        ),
        {'event_id': event_id},
    )
    assert int(event_count or 0) == 1
    assert int(occurrence_count or 0) == 1
    assert int(vibe_tag_count or 0) >= 2

    verification = VerificationService(pg_session_jobs, verifier=AlwaysInactiveVerifier())
    first_verify = await verification.verify_event(event_id)
    assert first_verify['active'] is False
    assert first_verify['status'] == 'suspect'

    first_state = await pg_session_jobs.execute(
        text(
            """
            select hidden, verification_status, verification_fail_count
            from public.events
            where id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    first_row = first_state.mappings().one()
    assert bool(first_row['hidden']) is False
    assert first_row['verification_status'] == 'suspect'
    assert int(first_row['verification_fail_count']) == 1

    second_verify = await verification.verify_event(event_id)
    assert second_verify['active'] is False
    assert second_verify['status'] == 'inactive'

    second_state = await pg_session_jobs.execute(
        text(
            """
            select hidden, verification_status, verification_fail_count
            from public.events
            where id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    second_row = second_state.mappings().one()
    assert bool(second_row['hidden']) is False
    assert second_row['verification_status'] == 'inactive'
    assert int(second_row['verification_fail_count']) == 2

    verification_runs = await pg_session_jobs.scalar(
        text('select count(*) from public.verification_runs where event_id = :event_id and active = false'),
        {'event_id': event_id},
    )
    assert int(verification_runs or 0) >= 1


@pytest.mark.asyncio
async def test_indeterminate_verification_does_not_downgrade_event(
    pg_session_jobs: AsyncSession,
) -> None:
    ingest = ManualIngestService(pg_session_jobs)
    unique = str(uuid4())
    booking_url = f'https://example.com/indeterminate-verification/{unique}'
    starts_at = (datetime.now(tz=UTC) + timedelta(days=1)).isoformat()

    summary = await ingest.ingest_manual(
        source_name=f'pytest-indeterminate-{unique[:8]}',
        city='Austin',
        events=[
            {
                'title': f'Indeterminate Event {unique[:8]}',
                'description': 'Verification should not downgrade on parser failure.',
                'category': 'experiences',
                'bookingUrl': booking_url,
                'startsAt': starts_at,
                'venue': {
                    'name': f'Indeterminate Venue {unique[:8]}',
                    'city': 'Austin',
                    'state': 'TX',
                    'latitude': 30.2672,
                    'longitude': -97.7431,
                },
                'vibes': ['social'],
                'tags': ['indeterminate-test'],
            }
        ],
    )
    event_id = summary.event_ids[0]

    verification = VerificationService(pg_session_jobs, verifier=IndeterminateVerifier())
    verify_result = await verification.verify_event(event_id)

    assert verify_result['eventId'] == event_id
    assert verify_result['active'] is None
    assert verify_result['status'] == 'pending'
    assert verify_result['skipped'] is True

    event_state = await pg_session_jobs.execute(
        text(
            """
            select verification_status, verification_fail_count, last_verified_at, last_verified_active
            from public.events
            where id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    state_row = event_state.mappings().one()
    assert state_row['verification_status'] == 'pending'
    assert int(state_row['verification_fail_count']) == 0
    assert state_row['last_verified_at'] is not None
    assert state_row['last_verified_active'] is None

    verification_run = await pg_session_jobs.execute(
        text(
            """
            select status, active
            from public.verification_runs
            where event_id = :event_id
            order by verified_at desc
            limit 1
            """
        ),
        {'event_id': event_id},
    )
    run_row = verification_run.mappings().one()
    assert run_row['status'] == 'indeterminate'
    assert run_row['active'] is None


from unittest.mock import patch

@patch('aventi_backend.services.verification.get_settings')
@pytest.mark.asyncio
async def test_worker_city_scan_json_adapter_enqueues_and_processes_verification(
    mock_get_settings,
    pg_session_jobs: AsyncSession,
) -> None:
    class MockSettings:
        google_api_key = None
    mock_get_settings.return_value = MockSettings()
    repo = JobQueueRepository(pg_session_jobs)
    unique = str(uuid4())
    booking_url = f'http://example.com/city-scan-test/{unique}'
    source_name = f'pytest-city-scan-json-{unique[:8]}'

    city_job = await repo.enqueue_job(
        JobType.CITY_SCAN,
        {
            'city': 'Austin',
            'angle': 'late night',
            'sourceType': 'json',
            'sourceName': source_name,
            'sourceData': {
                'events': [
                    {
                        'title': f'City Scan Test {unique[:8]}',
                        'bookingUrl': booking_url,
                        'startsAt': (datetime.now(tz=UTC) + timedelta(days=2)).isoformat(),
                        'category': 'nightlife',
                        'vibes': ['social', 'late-night'],
                        'tags': ['worker-test', unique[:8]],
                        'venue': {
                            'name': f'Worker Venue {unique[:8]}',
                            'city': 'Austin',
                            'state': 'TX',
                            'latitude': 30.2672,
                            'longitude': -97.7431,
                        },
                        'metadata': {'fixture': 'worker-city-scan-chain'},
                    }
                ]
            },
        },
    )

    claimed_city_jobs = await repo.claim_due_jobs(worker_name='pytest-city-scan', limit=10)
    claimed_city = next(job for job in claimed_city_jobs if job.id == city_job.id)

    city_result = await process_job(claimed_city, pg_session_jobs)
    await repo.mark_complete(claimed_city.id, run_id=claimed_city.run_id)

    assert city_result is not None
    ingest_info = city_result['ingest']
    assert ingest_info['source'] == source_name
    assert ingest_info['discovered'] == 1
    assert int(city_result['verificationJobsEnqueued']) >= 1
    event_id = ingest_info['eventIds'][0]

    event_row = await pg_session_jobs.execute(
        text(
            """
            select e.id::text as id, e.booking_url, e.category, v.city
            from public.events e
            left join public.venues v on v.id = e.venue_id
            where e.id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    event_data = event_row.mappings().one()
    assert event_data['booking_url'] == booking_url
    assert event_data['category'] == 'nightlife'
    assert event_data['city'] == 'Austin'

    claimed_verify_jobs = await repo.claim_due_jobs(worker_name='pytest-verify', limit=20)
    verify_job = next(
        job
        for job in claimed_verify_jobs
        if job.type == JobType.VERIFY_EVENT and job.payload.get('eventId') == event_id
    )

    verify_result = await process_job(verify_job, pg_session_jobs)
    await repo.mark_complete(verify_job.id, run_id=verify_job.run_id)

    assert verify_result is not None
    assert verify_result['eventId'] == event_id
    # MockVerifier marks non-https booking URLs inactive.
    assert verify_result['active'] is False
    assert verify_result['status'] == 'suspect'

    event_state = await pg_session_jobs.execute(
        text(
            """
            select hidden, verification_status, verification_fail_count
            from public.events
            where id = :event_id
            """
        ),
        {'event_id': event_id},
    )
    state_row = event_state.mappings().one()
    verify_count = await pg_session_jobs.scalar(
        text('select count(*) from public.verification_runs where event_id = :event_id'),
        {'event_id': event_id},
    )
    assert bool(state_row['hidden']) is False
    assert state_row['verification_status'] == 'suspect'
    assert int(state_row['verification_fail_count']) == 1
    assert int(verify_count or 0) >= 1


@pytest.mark.asyncio
async def test_market_warmup_runs_structured_sources_before_gemini(
    pg_session_jobs: AsyncSession,
) -> None:
    repo = JobQueueRepository(pg_session_jobs)
    unique = str(uuid4())
    market_city = f'Pytest Warm Market {unique[:8]}'
    market_key = f'{market_city.lower()}||us'
    source_name = f'pytest-market-json-{unique[:8]}'
    events = []
    for index in range(20):
        events.append(
            {
                'title': f'Market Warmup Event {unique[:8]} {index}',
                'bookingUrl': f'https://example.com/market-warmup/{unique}/{index}',
                'startsAt': (datetime.now(tz=UTC) + timedelta(days=1, hours=index)).isoformat(),
                'category': 'concerts',
                'vibes': ['social'],
                'tags': ['structured-source', unique[:8]],
                'venue': {
                    'name': f'Market Venue {unique[:8]} {index}',
                    'city': market_city,
                    'state': '',
                    'latitude': 37.7749,
                    'longitude': -122.4194,
                },
            }
        )

    source_row = await pg_session_jobs.execute(
        text(
            """
            insert into public.ingest_sources (name, source_type, enabled, config, created_at, updated_at)
            values (:name, 'json', true, cast(:config_json as jsonb), now(), now())
            returning id::text as id
            """
        ),
        {'name': source_name, 'config_json': json.dumps({'sourceData': {'events': events}})},
    )
    source_id = source_row.mappings().one()['id']
    await pg_session_jobs.execute(
        text(
            """
            insert into public.market_ingest_sources (market_key, source_id, priority, enabled)
            values (:market_key, :source_id, 10, true)
            on conflict (market_key, source_id) do update
            set priority = excluded.priority,
                enabled = excluded.enabled,
                updated_at = now()
            """
        ),
        {'market_key': market_key, 'source_id': source_id},
    )
    await pg_session_jobs.commit()

    warmup_job = await repo.enqueue_job(
        JobType.MARKET_WARMUP,
        {
            'marketKey': market_key,
            'marketCity': market_city,
            'marketCountry': 'US',
            'centerLatitude': 37.7749,
            'centerLongitude': -122.4194,
        },
    )

    claimed_jobs = await repo.claim_due_jobs(worker_name='pytest-market-warmup', limit=10)
    claimed_job = next(job for job in claimed_jobs if job.id == warmup_job.id)
    result = await process_job(claimed_job, pg_session_jobs)
    await repo.mark_complete(claimed_job.id, run_id=claimed_job.run_id)

    assert result is not None
    assert result['marketKey'] == market_key
    assert result['structuredSourcesRun'] == 1
    assert result['geminiJobsEnqueued'] == 0
    assert int(result['visibleEventCount7d']) >= 20

    gemini_jobs = await pg_session_jobs.scalar(
        text(
            """
            select count(*)
            from public.job_queue
            where job_type = 'CITY_SCAN'
              and payload ->> 'marketKey' = :market_key
              and payload ->> 'sourceName' = 'gemini'
            """
        ),
        {'market_key': market_key},
    )
    assert int(gemini_jobs or 0) == 0
