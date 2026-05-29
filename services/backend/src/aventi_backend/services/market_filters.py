from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from aventi_backend.services.market_descriptors import coerce_float, optional_str
from aventi_backend.services.providers import DiscoveryCandidate


def build_targeted_filter_signature(
    filters: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
) -> str:
    payload = {
        "categories": sorted(str(value) for value in (filters.get("categories") or [])),
        "date": filters.get("date"),
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "price": filters.get("price"),
        "radiusMiles": filters.get("radiusMiles"),
        "timeOfDay": filters.get("timeOfDay"),
        "vibes": sorted(str(value) for value in (filters.get("vibes") or [])),
    }
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def coerce_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def date_window_for_filters(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    if date_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    if date_filter == "tomorrow":
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow, tomorrow + timedelta(days=1)
    if date_filter == "week":
        return now, now + timedelta(days=7)

    days_until_sat = (5 - now.weekday()) % 7
    saturday = (now + timedelta(days=days_until_sat)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if saturday + timedelta(days=2) <= now:
        saturday += timedelta(days=7)
    return saturday, saturday + timedelta(days=2)


def time_of_day_matches(starts_at: datetime, bucket: str | None) -> bool:
    if not bucket:
        return True
    hour = starts_at.astimezone(UTC).hour
    if bucket == "morning":
        return 5 <= hour < 12
    if bucket == "afternoon":
        return 12 <= hour < 17
    if bucket == "evening":
        return 17 <= hour < 22
    if bucket == "night":
        return hour >= 22 or hour < 5
    return True


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: float | None,
    lon2: float | None,
) -> float | None:
    if lat2 is None or lon2 is None:
        return None
    from math import acos, cos, radians, sin

    return 3958.7613 * acos(
        min(
            1.0,
            max(
                -1.0,
                cos(radians(lat1)) * cos(radians(lat2)) * cos(radians(lon2) - radians(lon1))
                + sin(radians(lat1)) * sin(radians(lat2)),
            ),
        )
    )


def candidate_matches_filters(
    candidate: DiscoveryCandidate,
    *,
    feed_filters: dict[str, Any],
    latitude: float | None,
    longitude: float | None,
) -> bool:
    now = datetime.now(tz=UTC)
    date_filter = str(feed_filters.get("date") or "week")
    start_ts, end_ts = date_window_for_filters(date_filter, now)
    starts_at = candidate.starts_at
    if starts_at is None or starts_at < start_ts or starts_at >= end_ts:
        return False

    if not time_of_day_matches(starts_at, optional_str(feed_filters.get("timeOfDay"))):
        return False

    price = optional_str(feed_filters.get("price"))
    if price == "free" and not candidate.is_free:
        return False
    if price == "paid" and candidate.is_free:
        return False

    radius_miles = coerce_float(feed_filters.get("radiusMiles"))
    if radius_miles is not None and latitude is not None and longitude is not None:
        miles = haversine_miles(
            latitude,
            longitude,
            candidate.venue_latitude,
            candidate.venue_longitude,
        )
        if miles is None or miles > radius_miles:
            return False

    categories = [
        str(value).strip().lower()
        for value in (feed_filters.get("categories") or [])
        if str(value).strip()
    ]
    candidate_category = normalize_category(candidate.category)
    if categories and candidate_category not in categories:
        return False

    selected_vibes = {
        str(value).strip().lower()
        for value in (feed_filters.get("vibes") or [])
        if str(value).strip()
    }
    candidate_vibes = {value.strip().lower() for value in candidate.vibes if value.strip()}
    candidate_tags = {value.strip().lower() for value in candidate.tags if value.strip()}
    if selected_vibes and not selected_vibes.intersection(candidate_vibes.union(candidate_tags)):
        return False

    return True


def normalize_category(value: str | None) -> str:
    if not value:
        return "experiences"
    normalized = value.strip().lower()
    if normalized in {"nightlife", "dining", "concerts", "wellness", "experiences"}:
        return normalized
    if "music" in normalized or "concert" in normalized or "show" in normalized:
        return "concerts"
    if "food" in normalized or "drink" in normalized or "dining" in normalized:
        return "dining"
    if "well" in normalized or "fitness" in normalized or "yoga" in normalized:
        return "wellness"
    if "night" in normalized or "club" in normalized or "bar" in normalized:
        return "nightlife"
    return "experiences"
