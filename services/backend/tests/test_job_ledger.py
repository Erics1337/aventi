from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from aventi_backend.services import jobs
from aventi_backend.services.jobs import JobQueueRepository, JobType


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[dict[str, Any]] = []
        self.commits = 0

    async def execute(self, statement: Any, params: dict[str, Any]) -> None:
        self.statements.append({"sql": str(statement), "params": params})

    async def commit(self) -> None:
        self.commits += 1


def _ledger_session_factory(ledger_session: FakeSession):
    @asynccontextmanager
    async def _session() -> AsyncIterator[FakeSession]:
        yield ledger_session

    return _session


@dataclass
class FakeSettings:
    sqs_worker_queue_url: str = "https://sqs.test/123/worker"
    aws_endpoint_url: str | None = None


class FakeSqsClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.messages: list[dict[str, Any]] = []

    def send_message(self, **kwargs: Any) -> dict[str, str]:
        if self.should_fail:
            raise RuntimeError("sqs down")
        self.messages.append(kwargs)
        return {"MessageId": "message-123"}


@pytest.mark.asyncio
async def test_enqueue_job_inserts_and_marks_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    caller_session = FakeSession()
    ledger_session = FakeSession()
    client = FakeSqsClient()
    monkeypatch.setattr(jobs, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(jobs.boto3, "client", lambda *args, **kwargs: client)

    record = await JobQueueRepository(
        caller_session,
        ledger_session_factory=_ledger_session_factory(ledger_session),
    ).enqueue_job(
        JobType.MARKET_SCAN,
        {"marketKey": "denver-co-us", "marketCity": "Denver", "angle": "tonight"},
        max_attempts=3,
        scheduler_run_id="11111111-1111-1111-1111-111111111111",
    )

    assert record.id.startswith("job-")
    assert record.scheduler_run_id == "11111111-1111-1111-1111-111111111111"
    assert client.messages[0]["QueueUrl"] == "https://sqs.test/123/worker"
    assert '"scheduler_run_id": "11111111-1111-1111-1111-111111111111"' in client.messages[0][
        "MessageBody"
    ]
    assert len(ledger_session.statements) == 2
    assert ledger_session.statements[0]["params"]["market_key"] == "denver-co-us"
    assert ledger_session.statements[0]["params"]["max_attempts"] == 3
    assert (
        ledger_session.statements[0]["params"]["scheduler_run_id"]
        == "11111111-1111-1111-1111-111111111111"
    )
    assert ledger_session.statements[1]["params"]["sqs_message_id"] == "message-123"
    assert ledger_session.commits == 2
    assert caller_session.commits == 0
    assert caller_session.statements == []


@pytest.mark.asyncio
async def test_enqueue_job_marks_failed_when_sqs_send_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_session = FakeSession()
    ledger_session = FakeSession()
    monkeypatch.setattr(jobs, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(
        jobs.boto3,
        "client",
        lambda *args, **kwargs: FakeSqsClient(should_fail=True),
    )

    with pytest.raises(RuntimeError, match="sqs down"):
        await JobQueueRepository(
            caller_session,
            ledger_session_factory=_ledger_session_factory(ledger_session),
        ).enqueue_job(JobType.VERIFY_EVENT, {"eventId": "event-1"})

    assert len(ledger_session.statements) == 2
    assert ledger_session.statements[1]["params"]["status"] == "failed"
    assert ledger_session.statements[1]["params"]["error"] == "sqs down"
    assert ledger_session.commits == 2
    assert caller_session.commits == 0
