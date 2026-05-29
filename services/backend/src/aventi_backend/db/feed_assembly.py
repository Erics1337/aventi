from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings
from aventi_backend.db.feed_query import FeedFilterContext, FeedItemFilter, FeedQueryBuilder
from aventi_backend.models.schemas import EVENT_VIBE_TAGS
from aventi_backend.services.market_descriptors import build_market_descriptor
from aventi_backend.services.market_inventory import (
    ELIGIBLE_VERIFICATION_STATUSES,
    MarketWarmupService,
)

RemainingFreeSwipes = Callable[[str, Settings, datetime], Awaitable[int | None]]
WarmupServiceFactory = Callable[[AsyncSession], Any]


def date_window(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(UTC)
    if date_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if date_filter == "tomorrow":
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow, tomorrow + timedelta(days=1)
    if date_filter == "week":
        return now, now + timedelta(days=7)

    if now.weekday() == 5:
        saturday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif now.weekday() == 6:
        saturday = (now - timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        days_until_sat = (5 - now.weekday()) % 7
        saturday = (now + timedelta(days=days_until_sat)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    return saturday, saturday + timedelta(days=2)


def decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def encode_offset_cursor(offset: int) -> str | None:
    return str(offset) if offset > 0 else None


class FeedAssemblyService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        remaining_free_swipes: RemainingFreeSwipes,
        warmup_service_factory: WarmupServiceFactory = MarketWarmupService,
    ) -> None:
        self.session = session
        self.remaining_free_swipes = remaining_free_swipes
        self.warmup_service_factory = warmup_service_factory

    async def get_feed(
        self,
        *,
        user_id: str,
        db_user_id: str,
        settings: Settings,
        date: str,
        latitude: float,
        longitude: float,
        limit: int,
        time_of_day: str | None,
        price: str | None,
        radius_miles: float | None,
        selected_vibes: list[str] | None,
        categories: list[str] | None,
        cursor: str | None,
        market_city: str | None,
        market_state: str | None,
        market_country: str | None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        offset = decode_offset_cursor(cursor)
        now = datetime.now(tz=UTC)
        start_ts, end_ts = date_window(date, now)

        market_descriptor = build_market_descriptor(
            city=market_city,
            state=market_state,
            country=market_country,
            center_latitude=latitude,
            center_longitude=longitude,
        )

        query_result = await FeedQueryBuilder(
            session=self.session,
            user_id=db_user_id,
            start_ts=start_ts,
            end_ts=end_ts,
            eligible_statuses=list(ELIGIBLE_VERIFICATION_STATUSES),
            seen_window_days=settings.seen_events_window_days,
        ).with_price_filter(price).execute()

        filter_context = FeedFilterContext(
            user_latitude=latitude,
            user_longitude=longitude,
            radius_miles=radius_miles,
            time_of_day=time_of_day,
            selected_vibes=selected_vibes,
            categories=categories,
            supported_vibe_tags=EVENT_VIBE_TAGS,
        )
        scored_items = FeedItemFilter(filter_context).filter_and_score(query_result)
        scored_items.sort(key=lambda entry: (-entry[0], entry[1]))
        page_slice = scored_items[offset : offset + limit]
        items = [item for _, _, item in page_slice]
        next_cursor = (
            encode_offset_cursor(offset + limit) if len(scored_items) > offset + limit else None
        )

        remaining = await self.remaining_free_swipes(user_id, settings, now)
        fallback_status = "none" if items else "insufficient_inventory"
        market_key: str | None = market_descriptor.key if market_descriptor is not None else None
        inventory_status = "ready" if items else "no_matches"
        warmup_triggered = False

        if market_descriptor is not None and not items:
            market_key, inventory_status, warmup_triggered = await self.warmup_service_factory(
                self.session
            ).request_warmup(
                market_descriptor,
                force_refresh=force_refresh,
            )

        return {
            "items": items,
            "nextCursor": next_cursor,
            "fallbackStatus": fallback_status,
            "remainingFreeSwipes": remaining,
            "remainingFreePreferenceActions": remaining,
            "marketKey": market_key,
            "inventoryStatus": inventory_status,
            "warmupTriggered": warmup_triggered,
        }
