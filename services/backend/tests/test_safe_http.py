from __future__ import annotations

import httpx
import pytest

import aventi_backend.services.safe_http as safe_http
from aventi_backend.services.safe_http import (
    ResponseTooLargeError,
    UnsafeUrlError,
    safe_fetch,
    validate_public_url,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/private",
        "file:///etc/passwd",
        "http://user:secret@example.com/",
    ],
)
async def test_private_and_credentialed_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_public_url(url)


@pytest.mark.asyncio
async def test_redirect_target_is_validated(monkeypatch) -> None:
    async def public_only(url: str) -> tuple[str, str]:
        if "127.0.0.1" in url:
            raise UnsafeUrlError("private")
        return url, "93.184.216.34"

    monkeypatch.setattr(safe_http, "_resolve_public_target", public_only)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            302, headers={"location": "http://127.0.0.1/secret"}, request=request
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("https://example.com/start", client=client)


@pytest.mark.asyncio
async def test_streaming_response_size_is_enforced(monkeypatch) -> None:
    async def allow(url: str) -> tuple[str, str]:
        return url, "93.184.216.34"

    monkeypatch.setattr(safe_http, "_resolve_public_target", allow)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 20, request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ResponseTooLargeError):
            await safe_fetch("https://example.com/large", max_bytes=10, client=client)


@pytest.mark.asyncio
async def test_cross_origin_redirect_strips_authorization(monkeypatch) -> None:
    async def allow(url: str) -> tuple[str, str]:
        return url, "93.184.216.34"

    monkeypatch.setattr(safe_http, "_resolve_public_target", allow)
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                302, headers={"location": "http://example.com/final"}, request=request
            )
        return httpx.Response(200, content=b"ok", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        response = await safe_fetch(
            "https://example.com/start",
            headers={"Authorization": "secret"},
            client=client,
        )
    assert response.content == b"ok"
    assert seen[0].headers.get("authorization") == "secret"
    assert "authorization" not in seen[1].headers
    assert seen[1].headers["host"] == "example.com"
