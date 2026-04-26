from __future__ import annotations

import re
from typing import Any


MANAGED_IMAGE_SOURCES = frozenset({"opengraph", "pollinations", "supabase_storage"})
REPLACEABLE_DISCOVERY_SOURCES = frozenset({"serpapi", "google-events"})


def infer_image_source(image_url: str | None, discovery_source_type: str | None = None) -> str | None:
    if image_url:
        lowered = image_url.lower()
        if "image.pollinations.ai/" in lowered:
            return "pollinations"
        if "/storage/v1/object/public/event-images/" in lowered:
            return "supabase_storage"

    normalized_source = (discovery_source_type or "").strip().lower()
    if normalized_source in REPLACEABLE_DISCOVERY_SOURCES:
        return normalized_source
    if normalized_source:
        return normalized_source
    return None


def should_generate_main_image(
    image_url: str | None,
    metadata: dict[str, Any] | None,
    *,
    incoming_source_type: str | None = None,
) -> bool:
    metadata = metadata if isinstance(metadata, dict) else {}
    image_source = str(metadata.get("imageSource") or "").strip().lower()
    discovery_source = str(
        metadata.get("sourceType") or incoming_source_type or ""
    ).strip().lower()

    if image_source in MANAGED_IMAGE_SOURCES:
        return False
    if is_managed_event_image_url(image_url):
        return False
    if not image_url:
        return True
    if is_low_quality_image(image_url):
        return True
    return discovery_source in REPLACEABLE_DISCOVERY_SOURCES


def is_managed_event_image_url(image_url: str | None) -> bool:
    if not image_url:
        return False
    lowered = image_url.lower()
    return (
        "image.pollinations.ai/" in lowered
        or "/storage/v1/object/public/event-images/" in lowered
    )


def is_low_quality_image(url: str) -> bool:
    if not url:
        return True

    low_quality_patterns = [
        r"thumbnail",
        r"thumb",
        r"small",
        r"lowres",
        r"low-quality",
        r"\.jpg\?.*w=\d{1,3}",
        r"\.png\?.*w=\d{1,3}",
        r"eventbrite.*\d+x\d+",
        r"facebook.*\d+x\d+",
    ]

    url_lower = url.lower()
    for pattern in low_quality_patterns:
        if re.search(pattern, url_lower):
            return True

    low_quality_domains = [
        "fbcdn.net",
        "platform-lookaside.fbsbx.com",
    ]

    return any(domain in url_lower for domain in low_quality_domains)
