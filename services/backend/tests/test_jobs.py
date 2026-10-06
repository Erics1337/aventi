from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aventi_backend.services.jobs import JobQueueRepository, JobType, default_dedup_key
from aventi_backend.worker.lambda_handler import _process_records


class _Mappings:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row

    def one(self):
        assert self.row is not None
        return self.row


class _Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return _Mappings(self.row)

    def first(self):
        return self.row


class _Session:
    def __init__(self):
        self.calls = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        if "insert into public.jobs" in str(statement):
            return _Result(
                {
                    "id": params["id"],
                    "job_type": params["job_type"],
                    "payload": params["payload"],
                    "status": "queued",
                    "run_at": params["run_at"],
                    "attempts": 0,
                    "max_attempts": params["max_attempts"],
                    "locked_by": None,
                }
            )
        return _Result(None)

    async def commit(self):
        self.commits += 1


def test_default_dedup_key_is_stable_across_payload_order() -> None:
    one = default_dedup_key(JobType.MARKET_SCAN, {"city": "Austin", "pages": 2})
    two = default_dedup_key(JobType.MARKET_SCAN, {"pages": 2, "city": "Austin"})
    assert one == two


@pytest.mark.asyncio
async def test_enqueue_writes_job_and_outbox_without_committing() -> None:
    session = _Session()
    repo = JobQueueRepository(session)  # type: ignore[arg-type]
    run_at = datetime.now(tz=UTC)

    job = await repo.enqueue_job(JobType.VERIFY_EVENT, {"eventId": "event-1"}, run_at=run_at)

    assert job.type is JobType.VERIFY_EVENT
    assert len(session.calls) == 2
    assert "insert into public.jobs" in session.calls[0][0]
    assert "insert into public.job_outbox" in session.calls[1][0]
    assert session.commits == 0


@pytest.mark.asyncio
async def test_completion_is_fenced_by_worker_identity() -> None:
    session = _Session()
    repo = JobQueueRepository(session)  # type: ignore[arg-type]
    completed = await repo.complete_job("job-1", worker_id="lambda-a", result={"ok": True})
    sql, params = session.calls[-1]
    assert "locked_by = :worker_id" in sql
    assert params["worker_id"] == "lambda-a"
    assert completed is False


def test_active_only_dedup_allows_a_new_run_after_completion() -> None:
    migration = (
        __import__("pathlib").Path(__file__).parents[3]
        / "supabase/migrations/0011_durable_jobs.sql"
    ).read_text()
    assert "status in ('queued', 'processing', 'retry')" in migration


@pytest.mark.asyncio
async def test_malformed_sqs_message_is_failed_for_dead_lettering() -> None:
    result = await _process_records([{"messageId": "message-1", "body": "not-json"}])
    assert result["batchItemFailures"] == [{"itemIdentifier": "message-1"}]
