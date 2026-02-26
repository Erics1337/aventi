from __future__ import annotations

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

    queued_ok = await repo.enqueue_job(JobType.CITY_SCAN, {"testRunId": test_id, "city": "Austin"})
    queued_fail = await repo.enqueue_job(
        JobType.VERIFY_EVENT,
        {"testRunId": test_id, "eventId": '10000000-0000-0000-0000-000000000001'},
        max_attempts=1,
    )

    claimed = await repo.claim_due_jobs(worker_name='pytest-worker', limit=20)
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
    async def verify_booking_url(self, url: str) -> bool:
        _ = url
        return False


@pytest.mark.asyncio
async def test_manual_ingest_is_idempotent_and_verification_hides_inactive_event(
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
    verify_result = await verification.verify_event(event_id)
    assert verify_result['active'] is False
    assert verify_result['status'] == 'inactive'

    hidden_flag = await pg_session_jobs.scalar(
        text('select hidden from public.events where id = :event_id'),
        {'event_id': event_id},
    )
    verification_runs = await pg_session_jobs.scalar(
        text('select count(*) from public.verification_runs where event_id = :event_id and active = false'),
        {'event_id': event_id},
    )
    assert bool(hidden_flag) is True
    assert int(verification_runs or 0) >= 1


@pytest.mark.asyncio
async def test_worker_city_scan_json_adapter_enqueues_and_processes_verification(
    pg_session_jobs: AsyncSession,
) -> None:
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
    assert verify_result['status'] == 'inactive'

    hidden_flag = await pg_session_jobs.scalar(
        text('select hidden from public.events where id = :event_id'),
        {'event_id': event_id},
    )
    verify_count = await pg_session_jobs.scalar(
        text('select count(*) from public.verification_runs where event_id = :event_id'),
        {'event_id': event_id},
    )
    assert bool(hidden_flag) is True
    assert int(verify_count or 0) >= 1
