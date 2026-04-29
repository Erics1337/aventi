from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx


@dataclass(slots=True)
class TicketOffer:
    url: str
    provider: str | None = None
    price_label: str | None = None
    is_free: bool | None = None


@dataclass(slots=True)
class EventOccurrence:
    starts_at: datetime
    ends_at: datetime | None = None
    timezone: str | None = None


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
    venue_rating: float | None = None
    venue_review_count: int | None = None
    timezone: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    occurrences: list[EventOccurrence] = field(default_factory=list)
    image_url: str | None = None
    price_label: str | None = None
    is_free: bool | None = None
    ticket_offers: list[TicketOffer] = field(default_factory=list)
    vibes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchGroundedScraper(Protocol):
    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]: ...


class VerificationProvider(Protocol):
    async def verify_booking_url(self, url: str) -> bool | None: ...


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


class SerpApiEventScraper:
    def __init__(
        self,
        *,
        source_name: str | None = None,
        source_data: Any = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.source_name = source_name or "serpapi"
        self.source_data = source_data
        self.timeout_seconds = timeout_seconds
        # Populated by discover(); read by execute_market_scan to forward into ingest_runs.metadata.
        self.last_meta: dict[str, Any] = {}

    async def discover(self, city: str, angle: str) -> list[DiscoveryCandidate]:
        from aventi_backend.core.settings import get_settings
        import time as _time

        api_key = get_settings().serpapi_api_key
        if not api_key:
            raise ValueError("SERPAPI_API_KEY is not configured")

        # Parse optional dateWindow + pages hints from source_data. Both are
        # supplied by the cron scheduler; manual callers get the default
        # single-page behaviour unchanged.
        date_window: dict[str, Any] | None = None
        pages_planned = 1
        if isinstance(self.source_data, dict):
            raw_window = self.source_data.get("dateWindow")
            if isinstance(raw_window, dict):
                date_window = raw_window
            raw_pages = self.source_data.get("pages")
            if isinstance(raw_pages, int) and raw_pages > 0:
                pages_planned = min(raw_pages, 10)  # hard cap: 10 pages = 100 events

        query = _build_serpapi_query(city=city, angle=angle, source_data=self.source_data)
        url = "https://serpapi.com/search.json"
        # Note: google_events does not accept image_size; `image` field in the
        # response is already the full-resolution hero when available, and
        # falls back to `thumbnail` otherwise.
        base_params = {
            "engine": "google_events",
            "q": query,
            "api_key": api_key,
            "num": "10",
        }
        # Server-side date filter (htichips). Best-effort; client-side filter below
        # enforces the real window because htichips only supports today/week/weekend/month.
        if date_window:
            duration = int(date_window.get("durationDays") or 0)
            if duration <= 1:
                base_params["htichips"] = "date:today"
            elif duration <= 3:
                base_params["htichips"] = "date:weekend"
            elif duration <= 7:
                base_params["htichips"] = "date:week"
            elif duration <= 31:
                base_params["htichips"] = "date:month"

        events_data: list[Any] = []
        pages_executed = 0
        window_exhausted = False
        serpapi_ms_total = 0

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for page_idx in range(pages_planned):
                params = dict(base_params)
                if page_idx > 0:
                    params["start"] = str(page_idx * 10)

                print(f"[SERPAPI] discover query={query!r} page={page_idx} start={params.get('start', 0)}")
                _page_start = _time.monotonic()
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                serpapi_ms_total += int((_time.monotonic() - _page_start) * 1000)
                pages_executed += 1

                page_events = data.get("events_results", []) or []
                events_data.extend(page_events)
                print(
                    f"[SERPAPI] page_response count={len(page_events)} city={city!r} angle={angle!r}"
                )
                # Short-circuit: if this page returned fewer than 10 results,
                # Google has no more events to serve for this query. Stop paying
                # for credits that will return empty/duplicate pages.
                if len(page_events) < 10:
                    window_exhausted = True
                    break

        print(f"[SERPAPI] response raw_count={len(events_data)} city={city!r} angle={angle!r}")
        candidates: list[DiscoveryCandidate] = []
        seen_booking_urls: set[str] = set()

        for raw in events_data:
            title = raw.get("title")
            link = raw.get("link")
            if not title or not link:
                continue
            # Dedup across pages: Google Events sometimes returns the same
            # event on multiple pages when pagination overlaps.
            link_norm = str(link).strip()
            if link_norm in seen_booking_urls:
                continue
            seen_booking_urls.add(link_norm)

            venue_obj = raw.get("venue", {}) or {}
            venue_name = venue_obj.get("name")
            venue_rating = _coerce_float(venue_obj.get("rating"))
            venue_review_count_raw = venue_obj.get("reviews")
            venue_review_count: int | None = None
            if venue_review_count_raw is not None:
                try:
                    venue_review_count = int(venue_review_count_raw)
                except (TypeError, ValueError):
                    pass

            address_raw = raw.get("address")
            venue_address: str | None = None
            venue_city_line: str | None = None
            if isinstance(address_raw, list) and address_raw:
                venue_address = str(address_raw[0]).strip() or None
                if len(address_raw) > 1:
                    venue_city_line = str(address_raw[1]).strip() or None
            elif isinstance(address_raw, str):
                venue_address = address_raw.strip() or None

            # Issue 3: extract lat/lon from event_location_map.link
            venue_latitude: float | None = None
            venue_longitude: float | None = None
            map_obj = raw.get("event_location_map") or {}
            map_link = map_obj.get("link") if isinstance(map_obj, dict) else None
            if isinstance(map_link, str):
                lat, lon = _extract_lat_lon_from_maps_url(map_link)
                venue_latitude = lat
                venue_longitude = lon

            image_url = raw.get("image") or raw.get("thumbnail")

            # Issues 1 & 2: parse starts_at AND ends_at from date.when
            starts_at: datetime | None = None
            ends_at: datetime | None = None
            occurrences: list[EventOccurrence] = []
            date_obj = raw.get("date", {}) or {}
            if isinstance(date_obj, dict):
                when_str = date_obj.get("when")
                start_date_str = date_obj.get("start_date")
                starts_at, ends_at = _parse_serpapi_when_range(when_str, start_date_str)

                # Issue 7: recurring events – iterate all date blocks
                all_dates = raw.get("date_list") or []
                if isinstance(all_dates, list) and len(all_dates) > 1:
                    for date_block in all_dates:
                        if not isinstance(date_block, dict):
                            continue
                        occ_start, occ_end = _parse_serpapi_when_range(
                            date_block.get("when"), date_block.get("start_date")
                        )
                        if occ_start is not None:
                            occurrences.append(EventOccurrence(
                                starts_at=occ_start,
                                ends_at=occ_end,
                            ))

            description = raw.get("description")
            ticket_info_raw = raw.get("ticket_info") or []

            # Issue 4: normalise ticket_info into TicketOffer objects
            ticket_offers: list[TicketOffer] = _normalise_ticket_info(ticket_info_raw)

            # Issue 5: timezone inference from city
            tz_name = _city_timezone(city)

            # Issue 6 / improved price: prefer structured ticket price, fall back to text
            price_label, is_free = _extract_price_from_ticket_offers(ticket_offers)
            if price_label is None:
                price_label, is_free = _extract_price_from_description(description, title)

            # Promote first ticket URL as booking_url if the raw link is generic
            booking_url = link.strip()
            if ticket_offers:
                best_ticket = ticket_offers[0]
                if best_ticket.url and best_ticket.url.startswith("http"):
                    booking_url = best_ticket.url

            # Add vibe from search angle
            vibes = [angle.lower()] if angle.lower() in ["chill", "energetic", "romantic", "intellectual"] else []

            # Classify category
            category = _classify_category_from_angle(angle, title, description)

            candidates.append(
                DiscoveryCandidate(
                    title=title.strip(),
                    booking_url=booking_url,
                    city=city,
                    source=self.source_name,
                    description=_coerce_str(description),
                    venue_name=_coerce_str(venue_name),
                    venue_address=venue_address,
                    venue_latitude=venue_latitude,
                    venue_longitude=venue_longitude,
                    venue_rating=venue_rating,
                    venue_review_count=venue_review_count,
                    timezone=tz_name,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    occurrences=occurrences,
                    image_url=image_url.strip() if isinstance(image_url, str) else None,
                    price_label=price_label,
                    is_free=is_free,
                    ticket_offers=ticket_offers,
                    category=category,
                    vibes=vibes,
                    tags=[angle.replace(" ", "-"), "serpapi"],
                    metadata={
                        "sourceType": "serpapi",
                        "venueCityLine": venue_city_line,
                        "venueRating": venue_rating,
                        "venueReviewCount": venue_review_count,
                        "ticketInfo": ticket_info_raw,
                        "originalData": raw,
                    },
                )
            )

        candidates_before_window = len(candidates)
        if date_window:
            candidates = _filter_by_date_window(candidates, date_window)

        self.last_meta = {
            "pagesPlanned": pages_planned,
            "pagesExecuted": pages_executed,
            "windowExhausted": window_exhausted,
            "candidatesReturned": candidates_before_window,
            "filteredOutByWindow": candidates_before_window - len(candidates),
            "serpapiMs": serpapi_ms_total,
            "serpapiCreditsUsed": pages_executed,
        }
        if date_window:
            self.last_meta["windowStartDays"] = date_window.get("startDays")
            self.last_meta["windowDurationDays"] = date_window.get("durationDays")
            if date_window.get("label"):
                self.last_meta["scanType"] = date_window.get("label")

        return candidates


def _filter_by_date_window(
    candidates: list[DiscoveryCandidate],
    window: dict[str, Any],
) -> list[DiscoveryCandidate]:
    """Client-side enforcement of (start_days, duration_days) window.

    Google Events ``htichips`` is best-effort and often includes events a
    few days outside the requested bucket. The scheduler supplies explicit
    integer day offsets; anything outside is discarded.
    """
    now = datetime.now(tz=UTC)
    start_days = int(window.get("startDays") or 0)
    duration_days = int(window.get("durationDays") or 0)
    if duration_days <= 0:
        return candidates
    window_start = now + timedelta(days=start_days)
    window_end = window_start + timedelta(days=duration_days)
    filtered: list[DiscoveryCandidate] = []
    for candidate in candidates:
        starts_at = candidate.starts_at
        if starts_at is None:
            # No parsed start date yet — keep it; downstream normalization
            # will assign a default. We don't want to over-filter when
            # SerpAPI's `when` parser missed a date format.
            filtered.append(candidate)
            continue
        # Normalize starts_at to UTC for comparison
        if starts_at.tzinfo is None:
            # Naive datetime: treat as local time in candidate's timezone or UTC
            tz_name = candidate.timezone or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = UTC
            starts_at = starts_at.replace(tzinfo=tz).astimezone(UTC)
        elif starts_at.tzinfo != UTC:
            # Timezone-aware but not UTC: convert to UTC
            starts_at = starts_at.astimezone(UTC)
        if window_start <= starts_at < window_end:
            filtered.append(candidate)
    return filtered


def build_market_scan_scraper(payload: dict[str, Any]) -> SearchGroundedScraper:
    source_type = str(payload.get("sourceType") or "mock").strip().lower()
    source_name = str(payload.get("sourceName") or source_type or "market-scan")
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
    if source_type in {"gemini", "ai"}:
        from aventi_backend.services.gemini import GeminiEventScraper
        return GeminiEventScraper(source_name=source_name)
    if source_type in {"serpapi", "google-events"}:
        return SerpApiEventScraper(source_name=source_name, source_data=source_data)
    return MockScraper()


class MockVerifier:
    async def verify_booking_url(self, url: str) -> bool | None:
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


def _classify_category_from_angle(angle: str, title: str | None, description: str | None) -> str:
    """Classify event category based on search angle and content."""
    angle_lower = angle.lower()
    text = f"{title or ''} {description or ''}".lower()

    # Prefer content-based classification so angle hints do not override what the event actually is.
    if any(
        word in text
        for word in [
            "concert",
            "music",
            "musica",
            "dj",
            "band",
            "live music",
            "orchestra",
            "opera",
            "choir",
            "recital",
        ]
    ):
        return "concerts"
    elif any(
        word in text
        for word in [
            "food",
            "dinner",
            "lunch",
            "brunch",
            "restaurant",
            "tasting",
            "prix fixe",
            "cocktail",
            "wine",
            "bar",
        ]
    ):
        return "dining"
    elif any(word in text for word in ["party", "club", "nightclub", "dance"]):
        return "nightlife"
    elif any(
        word in text
        for word in [
            "art",
            "museum",
            "gallery",
            "exhibit",
            "poetry",
            "poet",
            "literary",
            "reading",
            "book",
            "author",
            "lecture",
            "talk",
            "workshop",
        ]
    ):
        return "experiences"
    elif any(word in text for word in ["wellness", "yoga", "meditation", "fitness"]):
        return "wellness"

    # Use the angle only as a soft fallback when the content itself gives no clue.
    if angle_lower == "energetic":
        return "nightlife"
    if angle_lower == "chill":
        return "wellness"
    if angle_lower in {"romantic", "intellectual"}:
        return "experiences"

    return "experiences"


def _build_serpapi_query(city: str, angle: str, source_data: Any) -> str:
    if isinstance(source_data, dict):
        explicit_query = source_data.get("query")
        if isinstance(explicit_query, str) and explicit_query.strip():
            return explicit_query.strip()

        filters = source_data.get("filters") or {}
        if isinstance(filters, dict):
            parts: list[str] = []
            price = str(filters.get("price") or "").strip().lower()
            time_of_day = str(filters.get("timeOfDay") or "").strip().lower()
            date = str(filters.get("date") or "").strip().lower()
            radius = filters.get("radiusMiles")
            vibes = [str(value).strip() for value in (filters.get("vibes") or []) if str(value).strip()]
            categories = [
                _category_query_label(str(value).strip().lower())
                for value in (filters.get("categories") or [])
                if str(value).strip()
            ]

            if price == "free":
                parts.append("free")
            elif price == "paid":
                parts.append("paid")
            if time_of_day:
                parts.append(time_of_day)
            if vibes:
                parts.extend(vibes)
            if categories:
                parts.extend(categories)
            parts.append("events")
            parts.append(f"in {city}")
            if date == "today":
                parts.append("today")
            elif date == "tomorrow":
                parts.append("tomorrow")
            elif date == "weekend":
                parts.append("this weekend")
            elif date == "week":
                parts.append("this week")
            if radius not in {None, ""}:
                parts.append(f"within {radius} miles")
            return " ".join(part for part in parts if part).strip()

    return f"{angle} events in {city}"


def _category_query_label(category: str) -> str:
    if category == "concerts":
        return "live music"
    if category == "experiences":
        return "arts"
    return category


def _extract_lat_lon_from_maps_url(url: str) -> tuple[float | None, float | None]:
    """Parse lat/lon from a Google Maps URL.

    Handles formats like:
      https://maps.google.com/maps?q=37.7749,-122.4194
      https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194
      https://maps.google.com/?ll=37.7749,-122.4194
    """
    patterns = [
        r'[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)',
        r'[?&]query=(-?\d+\.?\d*),(-?\d+\.?\d*)',
        r'[?&]ll=(-?\d+\.?\d*),(-?\d+\.?\d*)',
        r'@(-?\d+\.?\d*),(-?\d+\.?\d*)',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            try:
                return float(m.group(1)), float(m.group(2))
            except ValueError:
                pass
    return None, None


def _normalise_ticket_info(ticket_info_raw: list[Any]) -> list[TicketOffer]:
    """Convert raw SerpAPI ticket_info list into TicketOffer objects."""
    offers: list[TicketOffer] = []
    if not isinstance(ticket_info_raw, list):
        return offers
    for item in ticket_info_raw:
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url") or ""
        if not url:
            continue
        provider = item.get("source") or item.get("provider") or None
        raw_price = item.get("price") or item.get("price_label") or None
        price_label: str | None = None
        is_free: bool | None = None
        if raw_price is not None:
            price_str = str(raw_price).strip()
            if price_str.lower() in {"free", "0", "$0"}:
                price_label = "Free"
                is_free = True
            else:
                price_label = price_str
                is_free = False
        offers.append(TicketOffer(url=url, provider=provider, price_label=price_label, is_free=is_free))
    return offers


def _extract_price_from_ticket_offers(offers: list[TicketOffer]) -> tuple[str | None, bool | None]:
    """Pick the first non-None price from structured ticket offers."""
    for offer in offers:
        if offer.price_label is not None:
            return offer.price_label, offer.is_free
    return None, None


_CITY_TZ_MAP: dict[str, str] = {
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "dallas": "America/Chicago",
    "austin": "America/Chicago",
    "san antonio": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "las vegas": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "san diego": "America/Los_Angeles",
    "miami": "America/New_York",
    "orlando": "America/New_York",
    "atlanta": "America/New_York",
    "boston": "America/New_York",
    "philadelphia": "America/New_York",
    "washington": "America/New_York",
    "dc": "America/New_York",
    "nashville": "America/Chicago",
    "minneapolis": "America/Chicago",
    "detroit": "America/Detroit",
    "cleveland": "America/New_York",
    "charlotte": "America/New_York",
    "raleigh": "America/New_York",
    "salt lake city": "America/Denver",
    "albuquerque": "America/Denver",
    "tucson": "America/Phoenix",
    "honolulu": "Pacific/Honolulu",
    "anchorage": "America/Anchorage",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
}


def _city_timezone(city: str) -> str:
    """Return an IANA timezone string for a city, defaulting to UTC."""
    key = city.strip().lower()
    # First: exact key match
    if key in _CITY_TZ_MAP:
        return _CITY_TZ_MAP[key]
    # Second: substring matching with longest-match-wins
    best_match: str | None = None
    best_tz: str = "UTC"
    for city_key, tz in _CITY_TZ_MAP.items():
        if city_key in key:
            if best_match is None or len(city_key) > len(best_match):
                best_match = city_key
                best_tz = tz
    return best_tz


def _extract_price_from_description(description: str | None, title: str | None) -> tuple[str | None, bool | None]:
    """Extract price information from description and title."""
    if not description and not title:
        return None, None

    text = f"{title or ''} {description or ''}".lower()

    # Check for free events
    free_indicators = ["free", "no charge", "complimentary", "free entry", "free admission"]
    if any(indicator in text for indicator in free_indicators):
        return "Free", True

    # Extract price patterns
    price_patterns = [
        r'\$(\d+)',  # $25
        r'(\d+)\s*dollars?',  # 25 dollars
        r'donation\s*\$?(\d+)',  # donation $25
        r'suggested\s*donation\s*\$?(\d+)',  # suggested donation $25
        r'\$\$\$',  # $$$
        r'\$\$',   # $$
    ]

    for pattern in price_patterns:
        match = re.search(pattern, text)
        if match:
            price = match.group(1) if match.lastindex else match.group(0)
            if price == '$$$':
                return "$$$", False
            elif price == '$$':
                return "$$", False
            else:
                return f"${price}", False

    return None, None


def _parse_serpapi_when_range(
    when_str: str | None, start_date_str: str | None
) -> tuple[datetime | None, datetime | None]:
    """Parse SerpAPI date.when into (starts_at, ends_at).

    Handles:
      "Fri, 17 Apr, 7:00 – 9:30 pm"          → single day, start + end time
      "Sat, 18 Apr, 11:00 pm – Sun, 19 Apr, 12:30 am"  → cross-day range
    Returns (starts_at, ends_at); ends_at is None when only start found.
    """
    now = datetime.now(tz=UTC)
    current_year = now.year

    def _parse_segment(seg: str) -> datetime | None:
        seg = re.sub(r'^\w+,\s*', '', seg.strip()).strip()
        for fmt in ("%d %b, %I:%M %p", "%d %b, %I %p", "%d %b", "%I:%M %p", "%I %p"):
            try:
                dt = datetime.strptime(seg, fmt)
                dt = dt.replace(year=current_year)
                # Keep datetime naive (local time) - filtering code will normalize to UTC
                # using the candidate's timezone
                if dt < now - timedelta(days=1):
                    dt = dt.replace(year=current_year + 1)
                return dt
            except ValueError:
                continue
        return None

    if isinstance(when_str, str) and when_str.strip():
        raw = when_str.strip()
        sep = "\u2013" if "\u2013" in raw else "–"
        parts = raw.split(sep, 1)
        start_seg = parts[0].strip()
        end_seg = parts[1].strip() if len(parts) > 1 else None

        starts_at = _parse_segment(start_seg)

        ends_at: datetime | None = None
        if end_seg:
            # End segment may be just a time (same day) or full "Sun, 19 Apr, 12:30 am"
            end_parsed = _parse_segment(end_seg)
            if end_parsed is not None and starts_at is not None:
                # If end_parsed has no date it defaults to Jan 1 current_year; copy date from start
                if end_parsed.month == 1 and end_parsed.day == 1 and starts_at.month != 1:
                    end_parsed = end_parsed.replace(month=starts_at.month, day=starts_at.day)
                # If end < start it crossed midnight
                if end_parsed < starts_at:
                    end_parsed = end_parsed + timedelta(days=1)
                ends_at = end_parsed
            elif end_parsed is not None:
                ends_at = end_parsed

        if starts_at is not None:
            return starts_at, ends_at

    if isinstance(start_date_str, str) and start_date_str.strip():
        for fmt in ("%b %d", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(start_date_str.strip(), fmt)
                dt = dt.replace(year=current_year)
                # Keep datetime naive (local time) - filtering code will normalize
                if dt < now:
                    dt = dt.replace(year=current_year + 1)
                return dt, None
            except ValueError:
                continue

    return None, None


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
