from datetime import datetime, timedelta, timezone
from typing import Any

from aventi_backend.core.settings import Settings
from aventi_backend.models.schemas import EventCard, FeedResponse
from aventi_backend.services.constants import FREE_SWIPE_LIMIT_PER_DAY


def _seed_event(event_id: str, title: str, category: str, venue: str, vibes: list[str], starts_in_hours: int) -> dict[str, Any]:
    starts_at = datetime.now(tz=timezone.utc) + timedelta(hours=starts_in_hours)
    return {
        "id": event_id,
        "title": title,
        "description": f"Seeded event placeholder for {title}",
        "category": category,
        "venueName": venue,
        "city": "Austin",
        "startsAt": starts_at.isoformat(),
        "endsAt": None,
        "bookingUrl": f"https://example.com/{event_id}",
        "imageUrl": None,
        "priceLabel": "$20",
        "isFree": False,
        "radiusMiles": 4.0,
        "vibes": vibes,
        "tags": vibes,
    }


def get_seed_feed(settings: Settings) -> FeedResponse:
    events = [
        _seed_event("evt_seed_1", "Neon Roofline", "nightlife", "Aster Roof", ["energetic", "social"], 4),
        _seed_event("evt_seed_2", "Candlelight Reset", "wellness", "Quiet Room", ["chill", "wellness"], 18),
        _seed_event("evt_seed_3", "Indie Warehouse", "concerts", "Southline Works", ["live-music", "social"], 30),
    ]
    return FeedResponse(
        items=[EventCard.model_validate(item) for item in events],
        nextCursor=None,
        fallbackStatus="none",
        remainingFreeSwipes=settings.free_swipe_limit or FREE_SWIPE_LIMIT_PER_DAY,
        remainingFreePreferenceActions=settings.free_swipe_limit or FREE_SWIPE_LIMIT_PER_DAY,
    )
