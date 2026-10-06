import json
from unittest.mock import AsyncMock

import httpx
import pytest

from aventi_backend.services.gemini import PollinationsImageGenerator
from aventi_backend.services.pollinations import (
    PollinationsGroundedSelector,
    PollinationsUnavailable,
)
from aventi_backend.services.storage import SupabaseStorageService


@pytest.mark.asyncio
async def test_selector_limits_output_and_rejects_invented_ids(monkeypatch):
    def handle(request):
        assert request.url == "https://gen.pollinations.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-5.4-nano"
        assert body["max_completion_tokens"] == 512
        assert "test-secret" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "factIds": ["fake", "a", "a"],
                                    "compatibleEventIds": ["invented", "b"],
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "aventi_backend.services.pollinations.httpx.AsyncClient", lambda **_: client
    )
    result = await PollinationsGroundedSelector("test-secret").select(
        facts=[{"id": "a", "text": "Supported fact"}],
        compatible_events=[{"eventId": "b"}],
        preferences={},
    )
    assert result == {"factIds": ["a"], "compatibleEventIds": ["b"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 402, 429, 500])
async def test_provider_errors_do_not_retry_or_follow_redirects(monkeypatch, status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://example.com"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=False)
    monkeypatch.setattr(
        "aventi_backend.services.pollinations.httpx.AsyncClient", lambda **_: client
    )
    with pytest.raises(PollinationsUnavailable):
        await PollinationsGroundedSelector("secret").select(
            facts=[],
            compatible_events=[],
            preferences={},
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_oversized_insight_input_does_not_call_provider(monkeypatch):
    def forbidden(**_):
        raise AssertionError("Provider must not be called")

    monkeypatch.setattr("aventi_backend.services.pollinations.httpx.AsyncClient", forbidden)
    with pytest.raises(PollinationsUnavailable):
        await PollinationsGroundedSelector("secret").select(
            facts=[],
            compatible_events=[],
            preferences={"bad": "x" * 17000},
        )


@pytest.mark.asyncio
async def test_image_generation_uses_authenticated_fixed_model_url():
    with pytest.raises(ValueError):
        PollinationsImageGenerator()
    generator = PollinationsImageGenerator("secret")
    url = await generator.generate_event_image("music / evening")
    assert url.startswith("https://gen.pollinations.ai/image/music%20%2F%20evening?")
    assert "model=black-forest-labs%2Fflux.1-schnell" in url
    assert "secret" not in url
    with pytest.raises(ValueError):
        await generator.generate_event_image("x" * 4097)


@pytest.mark.asyncio
async def test_image_fetch_is_single_attempt_with_bearer_and_no_redirects(monkeypatch):
    service = SupabaseStorageService()
    service.base_url = "https://storage.example.com"
    service.service_key = "storage-secret"
    fetch = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    monkeypatch.setattr("aventi_backend.services.storage.safe_fetch", fetch)
    assert (
        await service.upload_image_from_url(
            "https://gen.pollinations.ai/image/music", "event", api_key="provider-secret"
        )
        is None
    )
    assert fetch.await_count == 1
    assert fetch.call_args.kwargs["headers"] == {"Authorization": "Bearer provider-secret"}
    assert fetch.call_args.kwargs["max_redirects"] == 0
    fetch.reset_mock()
    assert (
        await service.upload_image_from_url(
            "https://evil.example/image/music", "event", api_key="provider-secret"
        )
        is None
    )
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"x" * 65537, b"not-json", b'{"choices": []}'])
async def test_malformed_or_oversized_response_is_unavailable(monkeypatch, body):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    monkeypatch.setattr(
        "aventi_backend.services.pollinations.httpx.AsyncClient", lambda **_: client
    )
    with pytest.raises(PollinationsUnavailable):
        await PollinationsGroundedSelector("secret").select(
            facts=[],
            compatible_events=[],
            preferences={},
        )
