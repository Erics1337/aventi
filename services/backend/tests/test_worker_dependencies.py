from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.worker.handlers import JobDependencies, process_job


def _job(job_id: str, job_type: JobType, payload: dict[str, Any]) -> JobRecord:
    return JobRecord(
        id=job_id,
        type=job_type,
        payload=payload,
        run_at=datetime.now(tz=UTC),
    )


class FakeVerifyService:
    def __init__(self, session: Any) -> None:
        self.session = session

    async def verify_event(self, event_id: str) -> dict[str, Any]:
        return {"eventId": event_id, "status": "inactive"}


class FakeEnricher:
    async def enrich_event(self, *, description: str, context: str) -> dict[str, Any]:
        return {}


class FakeGenerator:
    api_key = "fake-key"

    async def generate_event_image(self, prompt: str) -> str:
        return "https://images.example/generated.jpg"


class FailingStorage:
    async def ensure_bucket_exists(self) -> None:
        return None

    async def upload_image_from_url(self, url: str, event_id: str, *, api_key: str | None) -> None:
        return None


class FakeMappings:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def first(self) -> dict[str, Any] | None:
        return self.row


class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.row)


class FakeSession:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    async def execute(self, *args: Any, **kwargs: Any) -> FakeResult:
        return FakeResult(self.row)

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_verify_event_uses_injected_service_factory() -> None:
    result = await process_job(
        _job("job-1", JobType.VERIFY_EVENT, {"eventId": "event-1"}),
        FakeSession(),  # type: ignore[arg-type]
        dependencies=JobDependencies(
            verification_service_factory=lambda session: FakeVerifyService(session),
        ),
    )

    assert result == {
        "jobId": "job-1",
        "jobType": "VERIFY_EVENT",
        "eventId": "event-1",
        "status": "inactive",
    }


@pytest.mark.asyncio
async def test_enrich_event_handles_bad_json_no_metadata_without_network() -> None:
    result = await process_job(
        _job("job-2", JobType.ENRICH_EVENT, {"eventId": "event-2"}),
        FakeSession(
            {
                "id": "event-2",
                "title": "Quiet Gallery Opening",
                "description": "A thoughtful art event with music and drinks.",
                "category": None,
                "vibes": [],
                "tags": [],
                "metadata": {},
                "city": "Denver",
            }
        ),  # type: ignore[arg-type]
        dependencies=JobDependencies(event_enricher_factory=FakeEnricher),
    )

    assert result == {"skipped": True, "reason": "no-metadata-extracted", "eventId": "event-2"}


@pytest.mark.asyncio
async def test_generate_image_storage_failure_is_typed_runtime_error_without_network() -> None:
    with pytest.raises(RuntimeError, match="persisted to Supabase Storage"):
        await process_job(
            _job("job-3", JobType.GENERATE_IMAGE, {"eventId": "event-3"}),
            FakeSession(
                {
                    "id": "event-3",
                    "title": "Rooftop Jazz",
                    "description": "Music above the city.",
                    "category": "concerts",
                    "booking_url": "https://tickets.example/event",
                    "metadata": {},
                    "city": "Denver",
                    "vibes": ["social"],
                }
            ),  # type: ignore[arg-type]
            dependencies=JobDependencies(
                settings_factory=lambda: SimpleNamespace(pollinations_api_key="fake-key"),
                image_generator_factory=lambda settings: FakeGenerator(),
                storage_factory=FailingStorage,
            ),
        )


@pytest.mark.asyncio
async def test_market_scan_uses_injected_executor_without_network() -> None:
    async def execute_scan(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"skipped": False, "ingest": {"discovered": 1}}

    result = await process_job(
        _job("job-4", JobType.MARKET_SCAN, {"city": "Denver", "angle": "events"}),
        FakeSession(),  # type: ignore[arg-type]
        dependencies=JobDependencies(market_scan_executor=execute_scan),
    )

    assert result == {
        "jobId": "job-4",
        "jobType": "MARKET_SCAN",
        "skipped": False,
        "ingest": {"discovered": 1},
    }
