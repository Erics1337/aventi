from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SwipeAction = Literal["like", "pass"]
ReportReason = Literal["invalid", "cancelled", "duplicate", "unsafe", "other"]
EventCategory = Literal["nightlife", "dining", "concerts", "wellness", "experiences"]
EventVibeTag = Literal[
    "chill",
    "energetic",
    "romantic",
    "social",
    "luxury",
    "live-music",
    "wellness",
    "late-night",
]


class EventCard(BaseModel):
    id: str
    title: str
    description: str
    category: EventCategory
    venue_name: str = Field(alias="venueName")
    city: str
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    booking_url: str = Field(alias="bookingUrl")
    image_url: str | None = Field(default=None, alias="imageUrl")
    price_label: str | None = Field(default=None, alias="priceLabel")
    is_free: bool = Field(alias="isFree")
    radius_miles: float | None = Field(default=None, alias="radiusMiles")
    vibes: list[EventVibeTag]
    tags: list[str]


class FeedFilters(BaseModel):
    date: Literal["today", "tomorrow", "weekend", "week"]
    time_of_day: Literal["morning", "afternoon", "evening", "night"] | None = Field(
        default=None, alias="timeOfDay"
    )
    price: Literal["free", "paid", "any"] | None = None
    radius_miles: float | None = Field(default=None, alias="radiusMiles")


class FeedResponse(BaseModel):
    items: list[EventCard]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    fallback_status: Literal["none", "relaxed_filters", "insufficient_inventory"] | None = Field(
        default=None, alias="fallbackStatus"
    )
    remaining_free_swipes: int | None = Field(default=None, alias="remainingFreeSwipes")
    remaining_free_preference_actions: int | None = Field(
        default=None, alias="remainingFreePreferenceActions"
    )
    market_key: str | None = Field(default=None, alias="marketKey")
    inventory_status: Literal["ready", "warming"] = Field(alias="inventoryStatus")
    warmup_triggered: bool = Field(default=False, alias="warmupTriggered")


class SwipePayload(BaseModel):
    event_id: str = Field(alias="eventId")
    action: SwipeAction
    surfaced_at: datetime = Field(alias="surfacedAt")
    position: int
    vibes: list[EventVibeTag]


class FeedImpressionPayload(BaseModel):
    event_id: str = Field(alias="eventId")
    served_at: datetime | None = Field(default=None, alias="servedAt")
    position: int | None = None
    affinity_score: float | None = Field(default=None, alias="affinityScore")
    filters: dict[str, Any] = Field(default_factory=dict)


class UserPreferences(BaseModel):
    categories: list[EventCategory]
    vibes: list[EventVibeTag]
    city: str | None = None
    radius_miles: int = Field(alias="radiusMiles")


class ProfileLocationPayload(BaseModel):
    latitude: float
    longitude: float
    city: str | None = None
    state: str | None = None
    country: str | None = None
    timezone: str | None = None


class MembershipEntitlements(BaseModel):
    is_premium: bool = Field(alias="isPremium")
    plan: Literal["free", "unlimited"]
    unlimited_swipes: bool = Field(alias="unlimitedSwipes")
    advanced_filters: bool = Field(alias="advancedFilters")
    travel_mode: bool = Field(alias="travelMode")
    insider_tips: bool = Field(alias="insiderTips")
    valid_until: datetime | None = Field(default=None, alias="validUntil")
