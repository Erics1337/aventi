"""Lightweight OpenGraph / Twitter card image scraper.

Used to recover a high-quality hero image from an event's booking_url before
falling back to AI image generation. Pure-stdlib regex parsing (no bs4) and
httpx for async HTTP.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

__all__ = ["OGImage", "fetch_og_image"]

# Browser-ish UA so CDNs (Eventbrite, Ticketmaster, Facebook, Instagram, etc.)
# don't serve us a 403 or an empty shell.
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15"
)
_DEFAULT_HEADERS = {
    "User-Agent": _DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Only read the first N KB — OG tags live in <head> and pages can be huge.
_MAX_READ_BYTES = 256 * 1024

# Ranked list of meta properties we'll accept as the hero image.
_IMAGE_PROPERTIES: tuple[str, ...] = (
    "og:image:secure_url",
    "og:image:url",
    "og:image",
    "twitter:image:src",
    "twitter:image",
)

# Matches <meta property="..." content="..."> and <meta name="..." content="...">
# in either attribute order, single- or double-quoted.
_META_RE = re.compile(
    r"""<meta\s+[^>]*?(?:property|name)\s*=\s*['"](?P<key>[^'"]+)['"][^>]*?content\s*=\s*['"](?P<val>[^'"]*)['"]"""
    r"""|<meta\s+[^>]*?content\s*=\s*['"](?P<val2>[^'"]*)['"][^>]*?(?:property|name)\s*=\s*['"](?P<key2>[^'"]+)['"]""",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class OGImage:
    url: str
    width: int | None = None
    height: int | None = None

    @property
    def is_likely_high_quality(self) -> bool:
        # If we have dimensions, require at least a 600px long edge.
        if self.width is not None and self.height is not None:
            return max(self.width, self.height) >= 600
        # No dimensions reported: accept by default and let downstream filters decide.
        return True


def _parse_meta_tags(html_snippet: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _META_RE.finditer(html_snippet):
        key = (match.group("key") or match.group("key2") or "").strip().lower()
        val = match.group("val") if match.group("val") is not None else match.group("val2")
        if not key or val is None:
            continue
        # Keep the first occurrence; OG tags appear near the top of <head>.
        out.setdefault(key, html.unescape(val.strip()))
    return out


def _extract_image(metas: dict[str, str], base_url: str) -> OGImage | None:
    for prop in _IMAGE_PROPERTIES:
        raw = metas.get(prop)
        if not raw:
            continue
        absolute = urljoin(base_url, raw)
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        width = _safe_int(metas.get("og:image:width"))
        height = _safe_int(metas.get("og:image:height"))
        return OGImage(url=absolute, width=width, height=height)
    return None


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


async def fetch_og_image(
    url: str,
    *,
    timeout_seconds: float = 6.0,
    client: httpx.AsyncClient | None = None,
) -> OGImage | None:
    """Return the OpenGraph/Twitter hero image for a URL, or None on failure.

    Silently returns None on network errors, non-HTML responses, or missing tags
    — callers should treat this as a best-effort hint, not a required signal.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return None

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        follow_redirects=True,
        headers=_DEFAULT_HEADERS,
    )
    try:
        response = await http_client.get(url, timeout=timeout_seconds)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "")
        if content_type and "html" not in content_type.lower() and "xml" not in content_type.lower():
            return None
        # response.text decodes via apparent encoding; slice after decode.
        body = response.text[:_MAX_READ_BYTES * 2]
        metas = _parse_meta_tags(body)
        return _extract_image(metas, base_url=str(response.url))
    except (httpx.HTTPError, UnicodeDecodeError):
        return None
    finally:
        if owns_client:
            await http_client.aclose()
