from __future__ import annotations

from typing import Any

import pytest

from aventi_backend.services import verification
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.verification import VerificationService


class FakeResult:
    def all(self) -> list[tuple[str]]:
        return [("event-1",), ("event-2",)]


class FakeSession:
    async def execute(self, *args: Any, **kwargs: Any) -> FakeResult:
        return FakeResult()

    async def scalar(self, *args: Any, **kwargs: Any) -> None:
        return None


class FakeJobQueueRepository:
    calls: list[dict[str, Any]] = []

    def __init__(self, session: Any) -> None:
        self.session = session

    async def enqueue_job(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        *,
        scheduler_run_id: str | None = None,
        **kwargs: Any,
    ) -> JobRecord:
        self.calls.append(
            {
                "job_type": job_type,
                "payload": payload or {},
                "scheduler_run_id": scheduler_run_id,
            }
        )
        return JobRecord(
            id=f"job-{len(self.calls)}",
            type=job_type,
            payload=payload or {},
            run_at=verification.datetime.now(tz=verification.UTC),
            scheduler_run_id=scheduler_run_id,
        )


@pytest.mark.asyncio
async def test_verification_smoke_links_jobs_to_scheduler_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeJobQueueRepository.calls = []
    monkeypatch.setattr(verification, "JobQueueRepository", FakeJobQueueRepository)

    count = await VerificationService(FakeSession()).enqueue_verification_jobs(
        limit=2,
        scheduler_run_id="11111111-1111-1111-1111-111111111111",
    )

    assert count == 2
    assert [call["scheduler_run_id"] for call in FakeJobQueueRepository.calls] == [
        "11111111-1111-1111-1111-111111111111",
        "11111111-1111-1111-1111-111111111111",
    ]
