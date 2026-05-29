from datetime import UTC, datetime, timedelta

from aventi_backend.services.market_descriptors import (
    build_market_descriptor,
    build_market_key,
    market_from_payload,
)
from aventi_backend.services.market_filters import (
    build_targeted_filter_signature,
    candidate_matches_filters,
    date_window_for_filters,
)
from aventi_backend.services.providers import DiscoveryCandidate


def test_market_descriptor_normalizes_key_and_payload() -> None:
    assert build_market_key(" Denver ", " CO ", " us ") == "denver|co|us"

    market = build_market_descriptor(city=" Denver ", state=" CO ")
    assert market is not None
    assert market.key == "denver|co|us"
    assert market.city == "Denver"
    assert market.state == "CO"
    assert market.country == "US"

    payload_market = market_from_payload(
        {
            "marketCity": "Austin",
            "marketState": "TX",
            "centerLatitude": "30.26",
            "centerLongitude": "-97.74",
        }
    )
    assert payload_market is not None
    assert payload_market.key == "austin|tx|us"
    assert payload_market.center_latitude == 30.26


def test_targeted_filter_signature_is_order_independent() -> None:
    first = build_targeted_filter_signature(
        {"categories": ["concerts", "dining"], "vibes": ["social", "date"], "date": "week"},
        latitude=39.7392,
        longitude=-104.9903,
    )
    second = build_targeted_filter_signature(
        {"categories": ["dining", "concerts"], "vibes": ["date", "social"], "date": "week"},
        latitude=39.73922,
        longitude=-104.99031,
    )

    assert first == second


def test_date_window_for_filters_weekend() -> None:
    friday = datetime(2026, 5, 29, 12, tzinfo=UTC)
    start, end = date_window_for_filters("weekend", friday)

    assert start == datetime(2026, 5, 30, tzinfo=UTC)
    assert end == datetime(2026, 6, 1, tzinfo=UTC)

    saturday_afternoon = datetime(2026, 5, 30, 15, tzinfo=UTC)
    start, end = date_window_for_filters("weekend", saturday_afternoon)

    assert start == datetime(2026, 5, 30, tzinfo=UTC)
    assert end == datetime(2026, 6, 1, tzinfo=UTC)


def test_candidate_matches_filters_applies_category_vibe_price_and_radius() -> None:
    candidate = DiscoveryCandidate(
        title="Rooftop Jazz",
        booking_url="https://tickets.example/rooftop",
        city="Denver",
        source="test",
        category="live music",
        starts_at=datetime.now(tz=UTC) + timedelta(days=1),
        is_free=True,
        venue_latitude=39.7392,
        venue_longitude=-104.9903,
        vibes=["social"],
        tags=["jazz"],
    )

    assert candidate_matches_filters(
        candidate,
        feed_filters={
            "date": "week",
            "categories": ["concerts"],
            "vibes": ["jazz"],
            "price": "free",
            "radiusMiles": 2,
        },
        latitude=39.7392,
        longitude=-104.9903,
    )
    assert not candidate_matches_filters(
        candidate,
        feed_filters={"date": "week", "categories": ["wellness"]},
        latitude=39.7392,
        longitude=-104.9903,
    )
