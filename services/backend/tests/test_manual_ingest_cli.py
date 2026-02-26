from __future__ import annotations

import json
from pathlib import Path

from aventi_backend.cli.manual_ingest import load_events_from_file


def test_load_events_from_json_array(tmp_path: Path) -> None:
    file_path = tmp_path / "events.json"
    file_path.write_text(
        json.dumps(
            [
                {
                    "title": "Midnight Jazz",
                    "bookingUrl": "https://example.com/jazz",
                    "startsAt": "2026-03-01T03:00:00Z",
                }
            ]
        )
    )

    events = load_events_from_file(file_path)
    assert len(events) == 1
    assert events[0]["bookingUrl"] == "https://example.com/jazz"


def test_load_events_from_csv_maps_common_fields(tmp_path: Path) -> None:
    file_path = tmp_path / "events.csv"
    file_path.write_text(
        "\n".join(
            [
                "title,booking_url,starts_at,category,is_free,vibes,tags,venue_name,venue_city,venue_state,venue_latitude,venue_longitude",
                "Rooftop Set,https://example.com/rooftop,2026-03-01T03:00:00Z,nightlife,true,social|energetic,late-night|dj,Skylight,Austin,TX,30.2672,-97.7431",
            ]
        )
    )

    events = load_events_from_file(file_path)
    assert len(events) == 1
    event = events[0]
    assert event["bookingUrl"] == "https://example.com/rooftop"
    assert event["startsAt"] == "2026-03-01T03:00:00Z"
    assert event["isFree"] is True
    assert event["vibes"] == ["social", "energetic"]
    assert event["tags"] == ["late-night", "dj"]
    assert event["venue"]["name"] == "Skylight"
    assert event["venue"]["city"] == "Austin"
    assert event["venue"]["state"] == "TX"
    assert event["venue"]["latitude"] == 30.2672
    assert event["venue"]["longitude"] == -97.7431

