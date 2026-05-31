import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from aventi_backend.services.jobs import JobRecord
from aventi_backend.worker import lambda_handler


class FakeSession:
    pass


class FakeLedger:
    processing: list[JobRecord] = []
    succeeded: list[tuple[str, dict[str, Any] | None]] = []
    failed: list[tuple[str, str, int, int | None]] = []

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def mark_processing(
        self,
        job: JobRecord,
        *,
        run_id: str | None = None,
        sqs_message_id: str | None = None,
    ) -> None:
        self.processing.append(job)

    async def mark_succeeded(self, job_id: str, *, result: dict[str, Any] | None) -> None:
        self.succeeded.append((job_id, result))

    async def mark_failed(
        self,
        job_id: str,
        *,
        error: str,
        attempts: int,
        max_attempts: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        self.failed.append((job_id, error, attempts, max_attempts))


def _session_factory(sessions: list[FakeSession]):
    @asynccontextmanager
    async def _session():
        session = FakeSession()
        sessions.append(session)
        yield session

    return _session


def _ledger_factory(calls: type[FakeLedger] = FakeLedger):
    calls.processing = []
    calls.succeeded = []
    calls.failed = []
    return calls


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
        ledger_factory=_ledger_factory(),
    )

    assert result == {"status": "ok", "processed": 1, "batchItemFailures": []}
    assert seen_jobs[0].id == "job-1"
    assert seen_jobs[0].attempts == 2
    assert seen_jobs[0].max_attempts == 3
    assert seen_jobs[0].run_id == "message-1"
    assert FakeLedger.processing[0].id == "job-1"
    assert FakeLedger.succeeded == [("job-1", {"ok": True})]


@pytest.mark.asyncio
async def test_process_records_marks_malformed_json_failed() -> None:
    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        raise AssertionError("malformed JSON should not dispatch a job")

    result = await lambda_handler._process_records(
        [_record("bad-json", "{")],
        session_factory=_session_factory([]),
        job_processor=process,
        ledger_factory=_ledger_factory(),
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
        ledger_factory=_ledger_factory(),
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
        ledger_factory=_ledger_factory(),
    )

    assert result == {
        "status": "ok",
        "processed": 1,
        "batchItemFailures": [{"itemIdentifier": "message-fail"}],
    }
    assert FakeLedger.failed == [("job-fail", "boom", 1, 5)]


@pytest.mark.asyncio
async def test_process_records_marks_max_attempts_dead() -> None:
    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        raise RuntimeError("final boom")

    result = await lambda_handler._process_records(
        [
            _record(
                "message-dead",
                {
                    "job_id": "job-dead",
                    "job_type": "VERIFY_EVENT",
                    "payload": {"eventId": "event-2"},
                    "max_attempts": 3,
                },
                receive_count="3",
            )
        ],
        session_factory=_session_factory([]),
        job_processor=process,
        ledger_factory=_ledger_factory(),
    )

    assert result == {
        "status": "ok",
        "processed": 0,
        "batchItemFailures": [{"itemIdentifier": "message-dead"}],
    }
    assert FakeLedger.failed == [("job-dead", "final boom", 3, 3)]


@pytest.mark.asyncio
async def test_process_records_skips_jobs_past_max_attempts() -> None:
    seen_jobs: list[JobRecord] = []

    async def process(job: JobRecord, session: FakeSession) -> dict[str, Any]:
        seen_jobs.append(job)
        raise AssertionError("dead jobs should not dispatch")

    result = await lambda_handler._process_records(
        [
            _record(
                "message-too-late",
                {
                    "job_id": "job-too-late",
                    "job_type": "VERIFY_EVENT",
                    "payload": {"eventId": "event-3"},
                    "max_attempts": 3,
                },
                receive_count="4",
            )
        ],
        session_factory=_session_factory([]),
        job_processor=process,
        ledger_factory=_ledger_factory(),
    )

    assert result == {"status": "ok", "processed": 0, "batchItemFailures": []}
    assert seen_jobs == []
    assert FakeLedger.failed == [
        ("job-too-late", "maximum attempts exceeded (4/3)", 4, 3)
    ]
