from datetime import UTC, datetime

import pytest

from aventi_backend.services.event_intake import (
    attach_image_metadata,
    booking_domain,
    coerce_datetime,
    coerce_float,
    coerce_list,
    normalize_category,
    normalize_event_payload,
    slugify,
)


def test_normalize_event_payload_accepts_manual_and_nested_venue_fields() -> None:
    starts_at = "2026-06-01T19:00:00Z"

    event = normalize_event_payload(
        {
            "title": "Jazz Night",
            "url": "https://tickets.example/jazz",
            "category": "live music",
            "venue": {
                "name": "Blue Room",
                "city": "Denver",
                "state": "CO",
                "latitude": "39.75",
                "longitude": "-104.99",
            },
            "starts_at": starts_at,
            "vibes": ("date-night", "music"),
            "tags": "jazz",
        },
        default_city="Austin",
    )

    assert event["title"] == "Jazz Night"
    assert event["bookingUrl"] == "https://tickets.example/jazz"
    assert event["category"] == "concerts"
    assert event["venueName"] == "Blue Room"
    assert event["city"] == "Denver"
    assert event["state"] == "CO"
    assert event["venueLatitude"] == 39.75
    assert event["venueLongitude"] == -104.99
    assert event["startsAt"] == datetime(2026, 6, 1, 19, tzinfo=UTC)
    assert event["vibes"] == ["date-night", "music"]
    assert event["tags"] == ["jazz"]


def test_normalize_event_payload_requires_title_and_booking_url() -> None:
    with pytest.raises(ValueError, match="title.*bookingUrl"):
        normalize_event_payload({"title": "Missing URL"}, default_city="Denver")


def test_event_intake_coercion_helpers() -> None:
    assert coerce_datetime("2026-06-01T19:00:00Z") == datetime(2026, 6, 1, 19, tzinfo=UTC)
    assert coerce_float("12.5") == 12.5
    assert coerce_float("bad") is None
    assert coerce_list(("a", 2)) == ["a", "2"]
    assert slugify("  The Blue Room! ") == "the-blue-room"
    assert booking_domain("https://tickets.example/path") == "tickets.example"
    assert normalize_category("late night club") == "nightlife"


def test_attach_image_metadata_records_source_type() -> None:
    event = attach_image_metadata(
        {
            "imageUrl": "https://serpapi.example/thumb.jpg",
            "metadata": {"sourceType": "serpapi"},
        }
    )

    assert event["metadata"]["imageSource"]
