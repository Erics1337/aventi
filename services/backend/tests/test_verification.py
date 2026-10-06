from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import aventi_backend.services.verification as verification_module
from aventi_backend.services.gemini import GeminiVerifier
from aventi_backend.services.safe_http import SafeHttpResponse, UnsafeUrlError
from aventi_backend.services.verification import VerificationService
from aventi_backend.worker.handlers import _description_supports_admission


class _Verifier:
    async def verify_booking_url(self, url: str) -> bool | None:
        return True


class _Budget:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reserve(self, provider: str, *, operation: str, units: int = 1) -> None:
        assert units == 1
        self.calls.append((provider, operation))


class _Models:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.payload))


def _client(payload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(models=_Models(payload))


def _page(text: str) -> SafeHttpResponse:
    return SafeHttpResponse(
        url="https://tickets.example/events/jazz",
        status_code=200,
        headers=httpx.Headers({"content-type": "text/html; charset=utf-8"}),
        content=f"<html><script>ignore me</script><body>{text}</body></html>".encode(),
    )


def test_production_never_falls_back_to_mock(monkeypatch) -> None:
    monkeypatch.setattr(
        verification_module,
        "get_settings",
        lambda: SimpleNamespace(env="production", google_api_key=None),
    )
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        VerificationService(object())  # type: ignore[arg-type]


def test_explicit_verifier_remains_injectable_for_tests(monkeypatch) -> None:
    monkeypatch.setattr(
        verification_module,
        "get_settings",
        lambda: SimpleNamespace(env="production", google_api_key=None),
    )
    verifier = _Verifier()
    service = VerificationService(object(), verifier=verifier)  # type: ignore[arg-type]
    assert service.verifier is verifier


def test_admission_requires_textual_source_evidence() -> None:
    assert _description_supports_admission("Doors at 8. This show is 21+.", "21+")
    assert not _description_supports_admission("Doors at 8. Tickets on sale.", "21+")


async def test_gemini_verifier_requires_quote_from_safely_fetched_document() -> None:
    budget = _Budget()
    client = _client(
        {
            "isValid": True,
            "supportingQuote": "Tickets are on sale for October 12, 2026.",
            "reason": "The page is selling tickets for an upcoming date.",
        }
    )

    async def fetcher(url: str, **kwargs) -> SafeHttpResponse:
        assert url == "https://tickets.example/events/jazz"
        assert kwargs["max_bytes"] == 512 * 1024
        return _page("Tickets are on sale for October 12, 2026.")

    verifier = GeminiVerifier(budget, client=client, fetcher=fetcher)
    assert await verifier.verify_booking_url("https://tickets.example/events/jazz") is True
    assert budget.calls == [("gemini", "booking-verification")]
    assert verifier.last_evidence == {
        "sourceUrl": "https://tickets.example/events/jazz",
        "supportingQuote": "Tickets are on sale for October 12, 2026.",
        "providerReason": "The page is selling tickets for an upcoming date.",
        "httpStatus": 200,
    }
    call = client.models.calls[0]
    assert "Tickets are on sale for October 12, 2026." in str(call["contents"])
    assert call["config"].tools is None


async def test_gemini_verifier_rejects_model_quote_absent_from_document() -> None:
    budget = _Budget()
    client = _client(
        {
            "isValid": False,
            "supportingQuote": "This event was cancelled.",
            "reason": "Cancelled",
        }
    )

    async def fetcher(url: str, **kwargs) -> SafeHttpResponse:
        return _page("Tickets are on sale for October 12, 2026.")

    verifier = GeminiVerifier(budget, client=client, fetcher=fetcher)
    assert await verifier.verify_booking_url("https://tickets.example/events/jazz") is None
    assert verifier.last_evidence is None


async def test_gemini_verifier_does_not_spend_budget_when_safe_fetch_fails() -> None:
    budget = _Budget()
    client = _client({"isValid": True, "supportingQuote": "Available"})

    async def fetcher(url: str, **kwargs) -> SafeHttpResponse:
        raise UnsafeUrlError("private address")

    verifier = GeminiVerifier(budget, client=client, fetcher=fetcher)
    assert await verifier.verify_booking_url("https://tickets.example/events/jazz") is None
    assert budget.calls == []
    assert client.models.calls == []


async def test_verification_run_persists_source_quote_evidence() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "id": "event",
        "booking_url": "https://tickets.example/events/jazz",
        "hidden": False,
        "verification_status": "pending",
        "verification_fail_count": 0,
        "last_verified_at": None,
        "last_verified_active": None,
    }
    session.execute.return_value = result
    verifier = _Verifier()
    verifier.last_evidence = {  # type: ignore[attr-defined]
        "sourceUrl": "https://tickets.example/events/jazz",
        "supportingQuote": "Tickets are on sale.",
        "providerReason": "On sale",
        "httpStatus": 200,
    }

    await VerificationService(session, verifier=verifier).verify_event("event")

    insert_call = next(
        call
        for call in session.execute.call_args_list
        if "insert into public.verification_runs" in str(call.args[0]).lower()
    )
    details = json.loads(insert_call.args[1]["details_json"])
    assert details["sourceUrl"] == "https://tickets.example/events/jazz"
    assert details["supportingQuote"] == "Tickets are on sale."


def test_production_discovery_rejects_mock(monkeypatch):
    from types import SimpleNamespace

    from aventi_backend.services.providers import build_market_scan_scraper

    monkeypatch.setattr(
        "aventi_backend.core.settings.get_settings", lambda: SimpleNamespace(env="production")
    )
    with pytest.raises(ValueError, match="real discovery provider"):
        build_market_scan_scraper({"sourceType": "mock"})


def test_unknown_event_dates_and_venues_are_not_invented():
    from datetime import UTC, datetime, timedelta

    from aventi_backend.services.market_inventory import _build_manual_events
    from aventi_backend.services.providers import DiscoveryCandidate

    candidates = [
        DiscoveryCandidate(
            city="New York",
            source="test",
            title="Undated",
            booking_url="https://example.com/one",
            venue_name="Venue",
        ),
        DiscoveryCandidate(
            city="New York",
            source="test",
            title="No venue",
            booking_url="https://example.com/two",
            starts_at=datetime.now(UTC) + timedelta(days=1),
        ),
        DiscoveryCandidate(
            city="New York",
            source="test",
            title="Known",
            booking_url="https://example.com/three",
            venue_name="Venue",
            starts_at=datetime.now(UTC) + timedelta(days=1),
        ),
    ]
    rows = _build_manual_events(
        candidates=candidates, city="New York", angle="events", source_name="test", job_id=None
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "Known"
    assert rows[0]["endsAt"] is None


def test_future_travel_query_and_filter_use_destination_calendar():
    from datetime import UTC, datetime

    from aventi_backend.services.providers import (
        DiscoveryCandidate,
        _build_serpapi_query,
        _filter_by_date_window,
    )

    window = {"startDate": "2026-11-01", "endDate": "2026-11-01"}
    assert "2026-11-01" in _build_serpapi_query("New York", "events", {"dateWindow": window})
    # 01:00 UTC next day is still Nov 1 in New York after the DST change.
    candidate = DiscoveryCandidate(
        city="New York",
        source="test",
        title="Late show",
        booking_url="https://example.com",
        starts_at=datetime(2026, 11, 2, 1, tzinfo=UTC),
        timezone="America/New_York",
    )
    assert _filter_by_date_window([candidate], window) == [candidate]
