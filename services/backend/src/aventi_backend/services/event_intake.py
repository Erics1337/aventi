from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from aventi_backend.services.event_images import infer_image_source


def normalize_event_payload(raw: dict[str, Any], *, default_city: str) -> dict[str, Any]:
    title = pick(raw, "title")
    booking_url = pick(raw, "bookingUrl", "booking_url", "url")
    starts_at_raw = pick(raw, "startsAt", "starts_at", default=None)
    if not title or not booking_url:
        raise ValueError("Manual ingest event requires `title` and `bookingUrl`")

    starts_at = (
        coerce_datetime(starts_at_raw)
        if starts_at_raw
        else datetime.now(tz=UTC) + timedelta(hours=6)
    )
    ends_at = coerce_datetime(pick(raw, "endsAt", "ends_at", default=None))

    venue_obj = raw.get("venue") if isinstance(raw.get("venue"), dict) else {}
    venue_name = pick(raw, "venueName", default=None) or pick(venue_obj, "name", default=None)
    if not venue_name:
        venue_name = f"{default_city} Spotlight"

    city = pick(raw, "city", default=None) or pick(venue_obj, "city", default=None) or default_city
    country = pick(raw, "country", default=None) or pick(venue_obj, "country", default=None) or "US"

    return {
        "title": str(title),
        "description": pick(raw, "description", default=None),
        "category": normalize_category(pick(raw, "category", default="experiences")),
        "bookingUrl": str(booking_url),
        "imageUrl": pick(raw, "imageUrl", "image_url", default=None),
        "priceLabel": pick(raw, "priceLabel", "price_label", default=None),
        "isFree": bool(pick(raw, "isFree", "is_free", default=False)),
        "startsAt": starts_at,
        "endsAt": ends_at,
        "timezone": pick(raw, "timezone", default="UTC"),
        "venueName": str(venue_name),
        "venueSlug": pick(raw, "venueSlug", default=None) or pick(venue_obj, "slug", default=None),
        "venueAddress": pick(raw, "venueAddress", default=None)
        or pick(venue_obj, "address", default=None),
        "venueLatitude": coerce_float(
            pick(raw, "venueLatitude", default=None) or pick(venue_obj, "latitude", default=None)
        ),
        "venueLongitude": coerce_float(
            pick(raw, "venueLongitude", default=None)
            or pick(venue_obj, "longitude", default=None)
        ),
        "city": str(city),
        "state": pick(raw, "state", default=None) or pick(venue_obj, "state", default=None),
        "country": str(country),
        "dressCode": pick(raw, "dressCode", "dress_code", default=None),
        "crowdAge": pick(raw, "crowdAge", "crowd_age", default=None),
        "musicGenre": pick(raw, "musicGenre", "music_genre", default=None),
        "sourceEventKey": pick(raw, "sourceEventKey", "source_event_key", default=None),
        "vibes": coerce_list(pick(raw, "vibes", default=[])),
        "tags": coerce_list(pick(raw, "tags", default=[])),
        "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
        "venueMetadata": (
            venue_obj.get("metadata") if isinstance(venue_obj.get("metadata"), dict) else {}
        ),
        "venueRating": coerce_float(pick(raw, "venueRating", "venue_rating", default=None)),
        "venueReviewCount": pick(raw, "venueReviewCount", "venue_review_count", default=None),
        "ticketOffers": raw.get("ticketOffers") or [],
        "extraOccurrences": raw.get("extraOccurrences") or [],
    }


def attach_image_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(event.get("metadata") or {})
    image_source = infer_image_source(
        event.get("imageUrl"),
        str(metadata.get("sourceType")) if metadata.get("sourceType") else None,
    )
    if image_source:
        metadata["imageSource"] = image_source
    return {**event, "metadata": metadata}


def pick(payload: Any, *keys: str, default: Any = None) -> Any:
    if not isinstance(payload, dict):
        return default
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"Unsupported datetime value: {value!r}")


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return [str(value)]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if slug:
        return slug[:120]
    return f"venue-{uuid5(NAMESPACE_URL, value)}"


def booking_domain(url: str) -> str | None:
    match = re.match(r"https?://([^/]+)", url)
    return match.group(1).lower() if match else None


def normalize_category(value: Any) -> str:
    if value is None:
        return "experiences"
    normalized = str(value).strip().lower()
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
