import re
from pathlib import Path
from typing import get_args

from aventi_backend.db.feed_query import FeedFilterContext
from aventi_backend.db.repository import _SUPPORTED_VIBE_TAGS
from aventi_backend.models.schemas import EventCategory, EventVibeTag, FeedFilters
from aventi_backend.services.categories import normalize_category
from aventi_backend.services.providers import _classify_category_from_angle


def test_mobile_and_backend_taxonomy_are_identical():
    source = (Path(__file__).resolve().parents[3] / "packages/contracts/src/index.ts").read_text()
    for name, contract in (("EventCategory", EventCategory), ("EventVibeTag", EventVibeTag)):
        definition = re.search(rf"export type {name} =(.+?);", source, re.S)
        assert definition
        assert set(re.findall(r"'([^']+)'", definition.group(1))) == set(get_args(contract))
    categories = list(get_args(EventCategory))
    vibes = list(get_args(EventVibeTag))
    FeedFilters(date="week", categories=categories, vibes=vibes)
    assert all(normalize_category(category) == category for category in categories)
    assert _SUPPORTED_VIBE_TAGS == set(vibes)
    assert FeedFilterContext(0, 0).supported_vibe_tags == set(vibes)


def test_ingestion_classifies_new_categories_from_source_text():
    for title, category in (
        ("Stand-up comedy show", "comedy"),
        ("Farmers market", "markets"),
        ("Basketball game", "sports"),
        ("Guided hiking tour", "outdoors"),
        ("Startup hackathon", "tech"),
    ):
        assert _classify_category_from_angle("events", title, None) == category
