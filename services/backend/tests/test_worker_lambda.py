import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from aventi_backend.services.jobs import JobRecord
from aventi_backend.worker import lambda_handler


class FakeSession:
    pass


def _session_factory(sessions: list[FakeSession]):
    @asynccontextmanager
    async def _session():
        session = FakeSession()
        sessions.append(session)
        yield session

    return _session


def _record(
    message_id: str,
    body: dict[str, Any] | str,
    *,
    receive_count: str = "1",
) -> dict[str, Any]:
    return {
        "messageId": message_id,
        "body": json.dumps(body) if isinstance(body, dict) else body,
        "attributes": {"ApproximateReceiveCount": receive_count},
    }


def test_handler_returns_noop_for_empty_event() -> None:
    result = lambda_handler.handler({"Records": []}, context=None)

    assert result == {"status": "ok", "message": "No records to process"}


@pytest.mark.asyncio
async def test_process_records_accepts_valid_sqs_batch() -> None:
    seen_jobs: list[JobRecord] = []
    sessions: list[FakeSession] = []

    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        seen_jobs.append(job)
        assert session in sessions
        return {"ok": True}

    result = await lambda_handler._process_records(
        [
            _record(
                "message-1",
                {
                    "job_id": "job-1",
                    "job_type": "MARKET_SCAN",
                    "payload": {"city": "Denver"},
                    "max_attempts": 3,
                },
                receive_count="2",
            )
        ],
        session_factory=_session_factory(sessions),
        job_processor=process,
    )

    assert result == {"status": "ok", "processed": 1, "batchItemFailures": []}
    assert seen_jobs[0].id == "job-1"
    assert seen_jobs[0].attempts == 2
    assert seen_jobs[0].max_attempts == 3
    assert seen_jobs[0].run_id == "message-1"


@pytest.mark.asyncio
async def test_process_records_marks_malformed_json_failed() -> None:
    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        raise AssertionError("malformed JSON should not dispatch a job")

    result = await lambda_handler._process_records(
        [_record("bad-json", "{")],
        session_factory=_session_factory([]),
        job_processor=process,
    )

    assert result == {
        "status": "ok",
        "processed": 0,
        "batchItemFailures": [{"itemIdentifier": "bad-json"}],
    }


@pytest.mark.asyncio
async def test_process_records_marks_unsupported_job_type_failed() -> None:
    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        raise AssertionError("unsupported job types should fail before dispatch")

    result = await lambda_handler._process_records(
        [_record("bad-type", {"job_type": "NOT_A_JOB", "payload": {}})],
        session_factory=_session_factory([]),
        job_processor=process,
    )

    assert result == {
        "status": "ok",
        "processed": 0,
        "batchItemFailures": [{"itemIdentifier": "bad-type"}],
    }


@pytest.mark.asyncio
async def test_process_records_returns_partial_batch_failures() -> None:
    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        if job.id == "job-fail":
            raise RuntimeError("boom")
        return {"ok": True}

    result = await lambda_handler._process_records(
        [
            _record(
                "message-ok",
                {
                    "job_id": "job-ok",
                    "job_type": "VERIFY_EVENT",
                    "payload": {"eventId": "event-1"},
                },
            ),
            _record(
                "message-fail",
                {
                    "job_id": "job-fail",
                    "job_type": "VERIFY_EVENT",
                    "payload": {"eventId": "event-2"},
                },
            ),
        ],
        session_factory=_session_factory([]),
        job_processor=process,
    )

    assert result == {
        "status": "ok",
        "processed": 1,
        "batchItemFailures": [{"itemIdentifier": "message-fail"}],
    }
