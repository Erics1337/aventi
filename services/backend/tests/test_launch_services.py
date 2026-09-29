from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from aventi_backend.services.destinations import (
    DestinationPremiumRequiredError,
    DestinationService,
    GoogleDestinationClient,
    normalize_destination_query,
)
from aventi_backend.services.insights import InsightsService, _context_hash, _safe_source


class UnusedSession:
    pass


class StubGoogle:
    async def timezone(self, latitude: float, longitude: float) -> str:
        assert latitude == 40.7128
        assert longitude == -74.006
        return "America/New_York"


class FakeResult:
    def __init__(self, *, scalar=None, row=None):
        self.scalar = scalar
        self.row = row

    def scalar_one_or_none(self):
        return self.scalar

    def mappings(self):
        return self

    def first(self):
        return self.row


class CachedInsightSession:
    def __init__(self, *, verified=True):
        self.verified = verified
        self.queries = []

    async def execute(self, statement, _params=None):
        query = str(statement)
        self.queries.append(query)
        if "from public.premium_entitlements" in query:
            return FakeResult(scalar=True)
        if "select updated_at, last_verified_at" in query:
            row = (
                {"updated_at": datetime.now(tz=UTC), "last_verified_at": datetime.now(tz=UTC)}
                if self.verified
                else None
            )
            return FakeResult(row=row)
        if "from public.user_preferences" in query:
            return FakeResult(
                row={
                    "categories": ["concerts"],
                    "vibes": ["live-music"],
                    "radius_miles": 25,
                    "travel_mode_city": None,
                    "updated_at": datetime.now(tz=UTC),
                }
            )
        if "from public.profiles" in query:
            return FakeResult(row={"latitude":40.7,"longitude":-74,"timezone":"America/New_York"})
        if "select e.*, e.id::text" in query:
            return FakeResult(row={"ends_at": None})
        if "from public.event_insights" in query:
            return FakeResult(
                row={
                    "status": "ready",
                    "payload": {"grounded": True},
                    "job_id": "job-1",
                    "generated_at": datetime.now(tz=UTC),
                    "expires_at": datetime.now(tz=UTC) + timedelta(hours=1),
                    "updated_at": datetime.now(tz=UTC),
                }
            )
        return FakeResult()


def test_destination_query_normalization():
    assert normalize_destination_query("  New   York, NY ") == "new york, ny"


@pytest.mark.asyncio
async def test_destination_canonicalization_is_us_only_and_stable():
    service = DestinationService(
        UnusedSession(),
        settings=SimpleNamespace(
            google_geocoding_api_key=None,
            google_timezone_api_key=None,
        ),
        google=StubGoogle(),
    )
    service._reserve_budget = AsyncMock()
    raw = {
        "place_id": "ChIJOwg_06VPwokRYv534QaPC8g",
        "formatted_address": "New York, NY, USA",
        "address_components": [
            {"long_name": "New York", "short_name": "New York", "types": ["locality"]},
            {
                "long_name": "New York",
                "short_name": "NY",
                "types": ["administrative_area_level_1"],
            },
            {"long_name": "United States", "short_name": "US", "types": ["country"]},
        ],
        "geometry": {"location": {"lat": 40.7128, "lng": -74.006}},
    }
    first = await service._canonicalize(raw)
    second = await service._canonicalize(raw)
    assert first == second
    assert first["timezone"] == "America/New_York"
    assert first["country"] == "US"

    raw["address_components"][-1]["short_name"] = "CA"
    assert await service._canonicalize(raw) is None


@pytest.mark.asyncio
async def test_google_geocoder_always_applies_us_country_filter():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["components"] == "country:US"
        assert request.url.params["region"] == "us"
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        google = GoogleDestinationClient(
            geocoding_key="geocode-key", timezone_key="timezone-key", client=client
        )
        assert await google.geocode("Toronto") == []


def test_insight_sources_allow_only_http_urls():
    assert _safe_source("https://example.com/event", label="Official") == {
        "label": "Official",
        "url": "https://example.com/event",
    }
    assert _safe_source("javascript:alert(1)", label="Bad") is None
    assert _safe_source(None, label="Bad") is None


def test_insight_context_hash_changes_with_preferences_and_filters():
    base = {"preferences": {"vibes": ["chill"]}, "filters": {"radiusMiles": 10}}
    changed = {"preferences": {"vibes": ["social"]}, "filters": {"radiusMiles": 10}}
    assert _context_hash(base) != _context_hash(changed)


@pytest.mark.asyncio
async def test_cached_insight_is_served_only_after_current_event_verification():
    session = CachedInsightSession()
    service = InsightsService(
        session,
        settings=SimpleNamespace(google_api_key=None, insights_cache_hours=24),
    )
    result = await service.get_or_enqueue(
        user_id="00000000-0000-0000-0000-000000000001",
        event_id="00000000-0000-0000-0000-000000000002",
    )
    assert result["status"] == "ready"
    verification_index = next(
        index for index, query in enumerate(session.queries) if "last_verified_at" in query
    )
    cache_index = next(
        index for index, query in enumerate(session.queries) if "event_insights" in query
    )
    assert verification_index < cache_index


@pytest.mark.asyncio
async def test_destination_search_requires_premium_before_provider_use():
    class FreeSession:
        async def execute(self, _statement, _params=None):
            return FakeResult(scalar=False)

    service = DestinationService(
        FreeSession(),
        settings=SimpleNamespace(
            google_geocoding_api_key=None,
            google_timezone_api_key=None,
        ),
    )
    with pytest.raises(DestinationPremiumRequiredError):
        await service.require_premium("00000000-0000-0000-0000-000000000001")
