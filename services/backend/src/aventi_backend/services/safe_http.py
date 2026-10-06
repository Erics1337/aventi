from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


class UnsafeUrlError(ValueError):
    pass


class ResponseTooLargeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SafeHttpResponse:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return self.content.decode(encoding, errors="replace")

    def json(self):
        import json

        return json.loads(self.content)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(self.status_code, request=request, content=self.content)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code} while fetching {self.url}",
                request=request,
                response=response,
            )


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return bool(ip.is_global)


async def _resolve_public_target(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only HTTP and HTTPS URLs are allowed")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL must contain a hostname and no credentials")
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise UnsafeUrlError("Only ports 80 and 443 are allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeUrlError("Local network hosts are forbidden")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise UnsafeUrlError("Hostname could not be resolved") from exc
        addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafeUrlError("URL resolves to a non-public address")
    return url, addresses[0]


async def validate_public_url(url: str) -> str:
    validated, _ = await _resolve_public_target(url)
    return validated


def _pinned_url(url: str, address: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port
    ip_literal = f"[{address}]" if ":" in address else address
    netloc = f"{ip_literal}:{port}" if port is not None else ip_literal
    host_header = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, "")), host_header


async def safe_fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
    max_bytes: int = 1024 * 1024,
    allowed_content_types: Iterable[str] | None = None,
    max_redirects: int = 4,
    client: httpx.AsyncClient | None = None,
) -> SafeHttpResponse:
    """Fetch a bounded public URL, validating DNS again on every redirect."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    owns_client = client is None
    http_client = client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
    current_url = url
    request_headers = dict(headers or {})
    try:
        for redirect_count in range(max_redirects + 1):
            _, address = await _resolve_public_target(current_url)
            request_url, host_header = _pinned_url(current_url, address)
            pinned_headers = {**request_headers, "Host": host_header, "Connection": "close"}
            original_host = urlsplit(current_url).hostname or ""
            async with http_client.stream(
                "GET",
                request_url,
                headers=pinned_headers,
                timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0)),
                follow_redirects=False,
                extensions={"sni_hostname": original_host},
            ) as response:
                if response.is_redirect:
                    if redirect_count >= max_redirects:
                        raise UnsafeUrlError("Too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeUrlError("Redirect is missing a location")
                    next_url = urljoin(current_url, location)
                    current_origin = urlsplit(current_url)
                    next_origin = urlsplit(next_url)
                    if (
                        next_origin.scheme,
                        next_origin.hostname,
                        next_origin.port,
                    ) != (
                        current_origin.scheme,
                        current_origin.hostname,
                        current_origin.port,
                    ):
                        request_headers = {
                            key: value
                            for key, value in request_headers.items()
                            if key.lower() not in {"authorization", "proxy-authorization", "apikey"}
                        }
                    current_url = next_url
                    continue
                content_type = response.headers.get("content-type", "").lower()
                if allowed_content_types and content_type:
                    if not any(
                        content_type.startswith(item.lower()) for item in allowed_content_types
                    ):
                        raise UnsafeUrlError(f"Unexpected content type: {content_type}")
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        declared_size = int(declared)
                    except ValueError:
                        declared_size = 0
                    if declared_size > max_bytes:
                        raise ResponseTooLargeError(f"Response exceeds {max_bytes} bytes")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ResponseTooLargeError(f"Response exceeds {max_bytes} bytes")
                    chunks.append(chunk)
                return SafeHttpResponse(
                    url=current_url,
                    status_code=response.status_code,
                    headers=response.headers,
                    content=b"".join(chunks),
                )
        raise UnsafeUrlError("Too many redirects")
    finally:
        if owns_client:
            await http_client.aclose()
