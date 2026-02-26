from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from xml.etree import ElementTree

import httpx


@dataclass(slots=True)
class DiscoveryCandidate:
    title: str
    booking_url: str
    city: str
    source: str
    description: str | None = None
    category: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_state: str | None = None
    venue_latitude: float | None = None
    venue_longitude: float | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    image_url: str | None = None
    price_label: str | None = None
    is_free: bool | None = None
    vibes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchGroundedScraper(Protocol):
    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]: ...


class VerificationProvider(Protocol):
    async def verify_booking_url(self, url: str) -> bool: ...


class ImageGenerationProvider(Protocol):
    async def generate_event_image(self, prompt: str) -> str: ...


class MockScraper:
    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        return [
            DiscoveryCandidate(
                title=f"Mock {angle.title()} Event",
                booking_url="https://example.com/mock-event",
                city=city,
                source="mock",
                tags=[angle.replace(" ", "-")],
                vibes=["social"],
            )
        ]


class StructuredJsonFeedScraper:
    def __init__(
        self,
        *,
        source_url: str | None = None,
        source_data: Any = None,
        source_name: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.source_url = source_url
        self.source_data = source_data
        self.source_name = source_name or "json"
        self.timeout_seconds = timeout_seconds

    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        payload = self.source_data
        if payload is None:
            if not self.source_url:
                raise ValueError("StructuredJsonFeedScraper requires `source_url` or `source_data`")
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.source_url)
                response.raise_for_status()
                payload = response.json()

        raw_events = _extract_structured_events(payload)
        candidates: list[DiscoveryCandidate] = []
        for raw in raw_events:
            if not isinstance(raw, dict):
                continue
            candidate = _candidate_from_json_event(
                raw,
                default_city=city,
                angle=angle,
                source=self.source_name,
            )
            if candidate:
                candidates.append(candidate)
        return candidates


class RssFeedScraper:
    def __init__(
        self,
        *,
        source_url: str | None = None,
        rss_xml: str | None = None,
        source_name: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.source_url = source_url
        self.rss_xml = rss_xml
        self.source_name = source_name or "rss"
        self.timeout_seconds = timeout_seconds

    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        xml_text = self.rss_xml
        if xml_text is None:
            if not self.source_url:
                raise ValueError("RssFeedScraper requires `source_url` or `rss_xml`")
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.source_url)
                response.raise_for_status()
                xml_text = response.text

        root = ElementTree.fromstring(xml_text)
        items = list(root.findall(".//item"))
        candidates: list[DiscoveryCandidate] = []
        for item in items:
            title = _xml_text(item, "title")
            link = _xml_text(item, "link")
            if not title or not link:
                continue
            pub_date = _xml_text(item, "pubDate")
            starts_at = _parse_datetime(pub_date)
            description = _xml_text(item, "description")
            tags = [angle.replace(" ", "-"), "rss"]
            category = None
            category_node = _find_any_xml(item, ["category"])
            if category_node is not None and category_node.text:
                category = category_node.text.strip().lower()
            candidates.append(
                DiscoveryCandidate(
                    title=title.strip(),
                    booking_url=link.strip(),
                    city=city,
                    source=self.source_name,
                    description=description.strip() if description else None,
                    category=category,
                    starts_at=starts_at,
                    tags=tags,
                    metadata={"feedType": "rss"},
                )
            )
        return candidates


def build_city_scan_scraper(payload: dict[str, Any]) -> SearchGroundedScraper:
    source_type = str(payload.get("sourceType") or "mock").strip().lower()
    source_name = str(payload.get("sourceName") or source_type or "city-scan")
    source_url = payload.get("sourceUrl")
    source_data = payload.get("sourceData")

    if source_type in {"json", "structured-json", "json-feed"}:
        return StructuredJsonFeedScraper(
            source_url=str(source_url) if isinstance(source_url, str) else None,
            source_data=source_data,
            source_name=source_name,
        )
    if source_type in {"rss", "rss-feed"}:
        return RssFeedScraper(
            source_url=str(source_url) if isinstance(source_url, str) else None,
            rss_xml=str(source_data) if isinstance(source_data, str) else None,
            source_name=source_name,
        )
    return MockScraper()


class MockVerifier:
    async def verify_booking_url(self, url: str) -> bool:
        return url.startswith("https://")


class MockImageGenerator:
    async def generate_event_image(self, prompt: str) -> str:
        _ = prompt
        return "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?auto=format&fit=crop&w=900&q=80"


def _extract_structured_events(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    raise ValueError("Structured JSON source payload must be an object or array")


def _candidate_from_json_event(
    raw: dict[str, Any],
    *,
    default_city: str,
    angle: str,
    source: str,
) -> DiscoveryCandidate | None:
    title = _pick(raw, "title", "name")
    booking_url = _pick(raw, "bookingUrl", "booking_url", "url", "link")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(booking_url, str) or not booking_url.strip():
        return None

    venue_obj = raw.get("venue") if isinstance(raw.get("venue"), dict) else {}
    city = _coerce_str(_pick(raw, "city"), default=default_city) or _coerce_str(
        _pick(venue_obj, "city"), default=default_city
    )

    vibes = _coerce_str_list(_pick(raw, "vibes", default=[]))
    tags = _coerce_str_list(_pick(raw, "tags", default=[]))
    if not tags:
        tags = [angle.replace(" ", "-")]

    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    metadata = {
        **metadata,
        "sourceType": "json",
    }

    return DiscoveryCandidate(
        title=title.strip(),
        booking_url=booking_url.strip(),
        city=city or default_city,
        source=source,
        description=_coerce_str(_pick(raw, "description", "summary")),
        category=_coerce_str(_pick(raw, "category"), default="experiences"),
        venue_name=_coerce_str(_pick(raw, "venueName")) or _coerce_str(_pick(venue_obj, "name")),
        venue_address=_coerce_str(_pick(raw, "venueAddress"))
        or _coerce_str(_pick(venue_obj, "address")),
        venue_state=_coerce_str(_pick(raw, "state")) or _coerce_str(_pick(venue_obj, "state")),
        venue_latitude=_coerce_float(_pick(raw, "venueLatitude"))
        or _coerce_float(_pick(venue_obj, "latitude")),
        venue_longitude=_coerce_float(_pick(raw, "venueLongitude"))
        or _coerce_float(_pick(venue_obj, "longitude")),
        starts_at=_parse_datetime(_pick(raw, "startsAt", "starts_at", "startTime", "start_time")),
        ends_at=_parse_datetime(_pick(raw, "endsAt", "ends_at", "endTime", "end_time")),
        image_url=_coerce_str(_pick(raw, "imageUrl", "image_url")),
        price_label=_coerce_str(_pick(raw, "priceLabel", "price_label")),
        is_free=_coerce_bool(_pick(raw, "isFree", "is_free")),
        vibes=vibes,
        tags=tags,
        metadata=metadata,
    )


def _pick(payload: Any, *keys: str, default: Any = None) -> Any:
    if not isinstance(payload, dict):
        return default
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _coerce_str(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or default
    return str(value)


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "free"}:
            return True
        if lowered in {"0", "false", "no", "n", "paid"}:
            return False
    return None


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        delimiter = "|" if "|" in value else ","
        return [part.strip() for part in value.split(delimiter) if part.strip()]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                return None
    return None


def _find_any_xml(node: ElementTree.Element, local_names: list[str]) -> ElementTree.Element | None:
    for child in list(node):
        tag = child.tag
        local = tag.rsplit("}", 1)[-1] if "}" in tag else tag
        if local in local_names:
            return child
    return None


def _xml_text(node: ElementTree.Element, name: str) -> str | None:
    child = _find_any_xml(node, [name])
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None

