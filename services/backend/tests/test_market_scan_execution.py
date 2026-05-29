from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from aventi_backend.services.market_descriptors import MarketDescriptor
from aventi_backend.services.market_scan_execution import MarketScanExecutionService
from aventi_backend.services.providers import DiscoveryCandidate, ProviderConfigurationError


class FakeInventoryState:
    def __init__(self) -> None:
        self.refreshes: list[str] = []

    async def refresh_market_inventory_state(self, market: MarketDescriptor) -> int:
        self.refreshes.append(market.key)
        return 0


class FakeScraper:
    def __init__(
        self,
        candidates: list[DiscoveryCandidate] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.candidates = candidates or []
        self.error = error
        self.last_meta = {"pagesFetched": 1}

    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        if self.error:
            raise self.error
        return self.candidates


@dataclass
class FakeIngestSummary:
    event_ids: list[str]
    discovered: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "source": "serpapi",
            "city": "Denver",
            "discovered": self.discovered,
            "insertedEvents": len(self.event_ids),
            "updatedEvents": 0,
            "insertedOccurrences": len(self.event_ids),
            "eventIds": self.event_ids,
        }


class FakeIngestService:
    calls: list[dict[str, Any]] = []

    def __init__(self, session: object) -> None:
        self.session = session

    async def ingest_manual(
        self,
        source_name: str,
        city: str,
        events: list[dict[str, Any]],
        scan_meta: dict[str, Any] | None = None,
    ) -> FakeIngestSummary:
        self.calls.append(
            {
                "source_name": source_name,
                "city": city,
                "events": events,
                "scan_meta": scan_meta,
            }
        )
        return FakeIngestSummary(event_ids=["event-1"], discovered=len(events))


class FakeVerificationService:
    calls: list[dict[str, Any]] = []

    def __init__(self, session: object) -> None:
        self.session = session

    async def enqueue_verification_jobs(
        self,
        limit: int = 20,
        *,
        event_ids: list[str] | None = None,
    ) -> int:
        self.calls.append({"limit": limit, "event_ids": event_ids})
        return len(event_ids or [])


def _market() -> MarketDescriptor:
    return MarketDescriptor(key="denver|co|us", city="Denver", state="CO", country="US")


def _candidate(**overrides: Any) -> DiscoveryCandidate:
    values = {
        "title": "Rooftop Jazz",
        "booking_url": "https://tickets.example/rooftop",
        "city": "Denver",
        "source": "serpapi",
        "category": "concerts",
        "starts_at": datetime.now(tz=UTC) + timedelta(days=1),
        "vibes": ["social"],
        "tags": ["jazz"],
    }
    values.update(overrides)
    return DiscoveryCandidate(**values)


@pytest.fixture(autouse=True)
def reset_fakes() -> None:
    FakeIngestService.calls = []
    FakeVerificationService.calls = []


@pytest.mark.asyncio
async def test_provider_configuration_error_returns_skipped_scan() -> None:
    inventory_state = FakeInventoryState()
    service = MarketScanExecutionService(
        object(),  # type: ignore[arg-type]
        inventory_state=inventory_state,  # type: ignore[arg-type]
        settings_provider=lambda: SimpleNamespace(enable_verification=True),
        scraper_factory=lambda payload, settings: FakeScraper(
            error=ProviderConfigurationError("SERPAPI_API_KEY is not configured")
        ),
        ingest_factory=FakeIngestService,  # type: ignore[arg-type]
        verification_factory=FakeVerificationService,  # type: ignore[arg-type]
    )

    result = await service.execute(
        market=_market(),
        angle="events",
        source_name="serpapi",
        source_type="serpapi",
    )

    assert result["skipped"] is True
    assert result["reason"] == "provider_configuration"
    assert result["scanMeta"]["providerError"] == "SERPAPI_API_KEY is not configured"
    assert result["ingest"]["discovered"] == 0
    assert inventory_state.refreshes == ["denver|co|us"]
    assert FakeIngestService.calls == []


@pytest.mark.asyncio
async def test_no_candidates_refreshes_inventory_without_ingest() -> None:
    inventory_state = FakeInventoryState()
    service = MarketScanExecutionService(
        object(),  # type: ignore[arg-type]
        inventory_state=inventory_state,  # type: ignore[arg-type]
        settings_provider=lambda: SimpleNamespace(enable_verification=True),
        scraper_factory=lambda payload, settings: FakeScraper([]),
        ingest_factory=FakeIngestService,  # type: ignore[arg-type]
        verification_factory=FakeVerificationService,  # type: ignore[arg-type]
    )

    result = await service.execute(market=_market(), angle="events", source_name="serpapi")

    assert result["ingest"]["eventIds"] == []
    assert inventory_state.refreshes == ["denver|co|us"]
    assert FakeIngestService.calls == []


@pytest.mark.asyncio
async def test_filter_exclusion_avoids_ingest() -> None:
    inventory_state = FakeInventoryState()
    service = MarketScanExecutionService(
        object(),  # type: ignore[arg-type]
        inventory_state=inventory_state,  # type: ignore[arg-type]
        settings_provider=lambda: SimpleNamespace(enable_verification=True),
        scraper_factory=lambda payload, settings: FakeScraper(
            [_candidate(category="wellness")]
        ),
        ingest_factory=FakeIngestService,  # type: ignore[arg-type]
        verification_factory=FakeVerificationService,  # type: ignore[arg-type]
    )

    result = await service.execute(
        market=_market(),
        angle="events",
        source_name="serpapi",
        feed_filters={"categories": ["concerts"], "date": "week"},
        latitude=39.7392,
        longitude=-104.9903,
    )

    assert result["ingest"]["discovered"] == 0
    assert inventory_state.refreshes == ["denver|co|us"]
    assert FakeIngestService.calls == []


@pytest.mark.asyncio
async def test_ingest_success_enqueues_verification_when_enabled() -> None:
    inventory_state = FakeInventoryState()
    service = MarketScanExecutionService(
        object(),  # type: ignore[arg-type]
        inventory_state=inventory_state,  # type: ignore[arg-type]
        settings_provider=lambda: SimpleNamespace(enable_verification=True),
        scraper_factory=lambda payload, settings: FakeScraper([_candidate()]),
        ingest_factory=FakeIngestService,  # type: ignore[arg-type]
        verification_factory=FakeVerificationService,  # type: ignore[arg-type]
    )

    result = await service.execute(
        market=_market(),
        angle="events",
        source_name="serpapi",
        job_id="job-1",
        extra_meta={"scanType": "weekly"},
    )

    assert result["ingest"]["eventIds"] == ["event-1"]
    assert result["scanMeta"]["pagesFetched"] == 1
    assert result["scanMeta"]["scanType"] == "weekly"
    assert FakeIngestService.calls[0]["events"][0]["metadata"]["discoveredByJobId"] == "job-1"
    assert FakeVerificationService.calls == [{"limit": 1, "event_ids": ["event-1"]}]
    assert result["verificationJobsEnqueued"] == 1
    assert inventory_state.refreshes == ["denver|co|us"]
