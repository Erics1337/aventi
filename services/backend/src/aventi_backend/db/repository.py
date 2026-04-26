from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings
from aventi_backend.models.schemas import (
    FeedImpressionPayload,
    MembershipEntitlements,
    ProfileLocationPayload,
    SwipePayload,
    UserPreferences,
)
from aventi_backend.services.market_inventory import (
    build_market_descriptor,
    ELIGIBLE_VERIFICATION_STATUSES,
    MarketWarmupService,
)
from aventi_backend.services.personalization import apply_vibe_update
from aventi_backend.db.feed_query import FeedQueryBuilder, FeedItemFilter, FeedFilterContext

_SUPPORTED_VIBE_TAGS = {
    "chill",
    "energetic",
    "intellectual",
    "romantic",
    "social",
    "luxury",
    "live-music",
    "wellness",
    "late-night",
}
_DEFAULT_RADIUS_MILES = 25.0


def _canonical_user_uuid(user_id: str) -> str:
    try:
        return str(UUID(user_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"aventi:user:{user_id}"))


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _date_window(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(timezone.utc)
    if date_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    if date_filter == "tomorrow":
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow, tomorrow + timedelta(days=1)
    if date_filter == "week":
        return now, now + timedelta(days=7)

    # weekend: next upcoming Saturday -> Monday (UTC fallback)
    days_until_sat = (5 - now.weekday()) % 7
    saturday = (now + timedelta(days=days_until_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
    if saturday < now:
        saturday += timedelta(days=7)
    return saturday, saturday + timedelta(days=2)


def _decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _encode_offset_cursor(offset: int) -> str | None:
    return str(offset) if offset > 0 else None


class AventiRepository:
    async def bootstrap_user(self, user_id: str, email: str | None) -> dict[str, Any]:
        raise NotImplementedError

    async def get_me(self, user_id: str, email: str | None) -> dict[str, Any]:
        raise NotImplementedError

    async def update_preferences(self, user_id: str, payload: UserPreferences) -> dict[str, Any]:
        raise NotImplementedError

    async def update_profile_location(
        self, user_id: str, email: str | None, payload: ProfileLocationPayload
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_feed(
        self,
        *,
        user_id: str,
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
        raise NotImplementedError

    async def record_swipe(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: SwipePayload,
        settings: Settings,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def record_feed_impression(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: FeedImpressionPayload,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def list_favorites(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def save_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def delete_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def report_event(
        self, user_id: str, event_id: str, reason: str, details: str | None
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_entitlements(self, user_id: str, email: str | None) -> MembershipEntitlements:
        raise NotImplementedError

    async def reset_seen_events(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError


class PostgresAventiRepository(AventiRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def bootstrap_user(self, user_id: str, email: str | None) -> dict[str, Any]:
        db_user_id = _canonical_user_uuid(user_id)
        inserted = await self.session.execute(
            text(
                """
                insert into public.profiles (id, email)
                values (:id, :email)
                on conflict (id) do update set email = coalesce(excluded.email, public.profiles.email)
                returning (xmax = 0) as created, city, timezone, latitude, longitude, onboarding_completed
                """
            ),
            {"id": db_user_id, "email": email},
        )
        profile_row = inserted.mappings().first()
        await self.session.execute(
            text(
                """
                insert into public.user_preferences (user_id)
                values (:user_id)
                on conflict (user_id) do nothing
                """
            ),
            {"user_id": db_user_id},
        )
        await self.session.execute(
            text(
                """
                insert into public.premium_entitlements (user_id)
                values (:user_id)
                on conflict (user_id) do nothing
                """
            ),
            {"user_id": db_user_id},
        )
        await self.session.commit()

        city = profile_row["city"] if profile_row else None
        timezone_value = profile_row["timezone"] if profile_row else None
        latitude = profile_row["latitude"] if profile_row else None
        longitude = profile_row["longitude"] if profile_row else None
        onboarded = profile_row["onboarding_completed"] if profile_row else False
        created = bool(profile_row["created"]) if profile_row and "created" in profile_row else False
        return {
            "id": user_id,
            "email": email,
            "created": created,
            "profile": {
                "city": city,
                "timezone": timezone_value,
                "latitude": latitude,
                "longitude": longitude,
                "onboarded": onboarded,
            },
        }

    async def get_me(self, user_id: str, email: str | None) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text(
                """
                select p.email, p.city, p.timezone, p.latitude, p.longitude, p.onboarding_completed,
                       up.categories, up.vibes, up.radius_miles, up.travel_mode_city
                from public.profiles p
                left join public.user_preferences up on up.user_id = p.id
                where p.id = :user_id
                """
            ),
            {"user_id": db_user_id},
        )
        row = result.mappings().first()
        categories = list((row["categories"] or [])) if row else []
        vibes = list((row["vibes"] or [])) if row else []
        return {
            "id": user_id,
            "email": (row["email"] if row else None) or email,
            "preferences": {
                "categories": categories,
                "vibes": vibes,
                "city": row["travel_mode_city"] if row else None,
                "radiusMiles": int(row["radius_miles"] if row and row["radius_miles"] is not None else 10),
            },
            "profile": {
                "city": row["city"] if row else None,
                "timezone": row["timezone"] if row else None,
                "latitude": row["latitude"] if row else None,
                "longitude": row["longitude"] if row else None,
                "onboarded": bool(row["onboarding_completed"] if row else False),
            },
        }

    async def update_preferences(self, user_id: str, payload: UserPreferences) -> dict[str, Any]:
        db_user_id = _canonical_user_uuid(user_id)
        values = payload.model_dump(by_alias=True)
        await self.session.execute(
            text(
                """
                insert into public.user_preferences (user_id, categories, vibes, radius_miles, travel_mode_city, updated_at)
                values (:user_id, :categories, :vibes, :radius_miles, :city, now())
                on conflict (user_id) do update
                set categories = excluded.categories,
                    vibes = excluded.vibes,
                    radius_miles = excluded.radius_miles,
                    travel_mode_city = excluded.travel_mode_city,
                    updated_at = now()
                """
            ),
            {
                "user_id": db_user_id,
                "categories": values["categories"],
                "vibes": values["vibes"],
                "radius_miles": values["radiusMiles"],
                "city": values.get("city"),
            },
        )
        await self.session.commit()
        return {"ok": True, "userId": user_id, "preferences": values}

    async def update_profile_location(
        self, user_id: str, email: str | None, payload: ProfileLocationPayload
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text(
                """
                update public.profiles
                set city = coalesce(:city, city),
                    timezone = coalesce(:timezone, timezone),
                    latitude = :latitude,
                    longitude = :longitude,
                    onboarding_completed = true,
                    updated_at = now()
                where id = :user_id
                returning city, timezone, latitude, longitude, onboarding_completed
                """
            ),
            {
                "user_id": db_user_id,
                "city": payload.city,
                "timezone": payload.timezone,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
            },
        )
        row = result.mappings().one()
        await self.session.commit()
        return {
            "ok": True,
            "userId": user_id,
            "profile": {
                "city": row["city"],
                "timezone": row["timezone"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "onboarded": bool(row["onboarding_completed"]),
            },
        }

    async def _is_premium(self, user_id: str) -> bool:
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text(
                "select is_premium from public.premium_entitlements where user_id = :user_id"
            ),
            {"user_id": db_user_id},
        )
        row = result.first()
        return bool(row[0]) if row else False

    async def _count_swipes_today(self, user_id: str, now: datetime) -> int:
        db_user_id = _canonical_user_uuid(user_id)
        start, end = _utc_day_bounds(now)
        result = await self.session.execute(
            text(
                """
                select count(*)
                from public.swipe_actions
                where user_id = :user_id
                  and created_at >= :start_ts
                  and created_at < :end_ts
                """
            ),
            {"user_id": db_user_id, "start_ts": start, "end_ts": end},
        )
        return int(result.scalar_one())

    async def _remaining_free_swipes(self, user_id: str, settings: Settings, now: datetime) -> int | None:
        if await self._is_premium(user_id):
            return None
        count = await self._count_swipes_today(user_id, now)
        return max(0, settings.free_swipe_limit - count)

    async def get_feed(
        self,
        *,
        user_id: str,
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
        offset = _decode_offset_cursor(cursor)
        now = datetime.now(tz=timezone.utc)
        await self.bootstrap_user(user_id, None)
        start_ts, end_ts = _date_window(date, now)
        db_user_id = _canonical_user_uuid(user_id)

        # Build market descriptor (used for returning marketKey in response).
        # We no longer compute visible_count here because the cron scheduler
        # owns warmup decisions; repeat computation was wasted work on every
        # feed request.
        market_descriptor = build_market_descriptor(
            city=market_city,
            state=market_state,
            country=market_country,
            center_latitude=latitude,
            center_longitude=longitude,
        )

        # Execute query using builder
        query_result = await FeedQueryBuilder(
            session=self.session,
            user_id=db_user_id,
            start_ts=start_ts,
            end_ts=end_ts,
            eligible_statuses=list(ELIGIBLE_VERIFICATION_STATUSES),
            seen_window_days=settings.seen_events_window_days,
        ).with_price_filter(price).execute()

        # Filter and score results
        filter_context = FeedFilterContext(
            user_latitude=latitude,
            user_longitude=longitude,
            radius_miles=radius_miles,
            time_of_day=time_of_day,
            selected_vibes=selected_vibes,
            categories=categories,
            supported_vibe_tags=_SUPPORTED_VIBE_TAGS,
        )
        scored_items = FeedItemFilter(filter_context).filter_and_score(query_result)

        # Sort, paginate, and extract items
        scored_items.sort(key=lambda entry: (-entry[0], entry[1]))
        page_slice = scored_items[offset : offset + limit]
        items = [item for _, _, item in page_slice]
        next_cursor = (
            _encode_offset_cursor(offset + limit) if len(scored_items) > offset + limit else None
        )

        # Calculate remaining swipes
        remaining = await self._remaining_free_swipes(user_id, settings, now)

        fallback_status = "none" if items else "insufficient_inventory"
        market_key: str | None = market_descriptor.key if market_descriptor is not None else None
        inventory_status = "ready" if items else "no_matches"
        warmup_triggered = False

        if market_descriptor is not None and not items:
            market_key, inventory_status, warmup_triggered = await MarketWarmupService(
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

    async def record_swipe(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: SwipePayload,
        settings: Settings,
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        now = datetime.now(tz=timezone.utc)
        remaining = await self._remaining_free_swipes(user_id, settings, now)
        if remaining is not None and remaining <= 0:
            raise PermissionError("Free preference action limit reached")

        db_user_id = _canonical_user_uuid(user_id)
        event_uuid = str(UUID(payload.event_id))

        await self.session.execute(
            text(
                """
                insert into public.swipe_actions (
                    user_id, event_id, action, surfaced_at, position, market_key
                )
                select :user_id, :event_id, :action, :surfaced_at, :position,
                       lower(v.city) || '|' || lower(coalesce(v.state, '')) || '|' || lower(coalesce(v.country, 'us'))
                  from public.events e
                  join public.venues v on v.id = e.venue_id
                 where e.id = :event_id
                """
            ),
            {
                "user_id": db_user_id,
                "event_id": event_uuid,
                "action": payload.action,
                "surfaced_at": payload.surfaced_at,
                "position": payload.position,
            },
        )

        if payload.vibes:
            existing_result = await self.session.execute(
                text(
                    """
                    select vibe, weight
                    from public.user_vibe_weights
                    where user_id = :user_id
                      and vibe in :vibes
                    """
                ).bindparams(bindparam("vibes", expanding=True)),
                {"user_id": db_user_id, "vibes": list(payload.vibes)},
            )
            existing = {str(row[0]): float(row[1]) for row in existing_result.all()}
            updated = apply_vibe_update(existing, payload.vibes, payload.action)
            for vibe, weight in updated.items():
                await self.session.execute(
                    text(
                        """
                        insert into public.user_vibe_weights (user_id, vibe, weight, updated_at)
                        values (:user_id, :vibe, :weight, now())
                        on conflict (user_id, vibe) do update
                        set weight = excluded.weight,
                            updated_at = now()
                        """
                    ),
                    {"user_id": db_user_id, "vibe": vibe, "weight": weight},
                )

        await self.session.commit()
        remaining_after = await self._remaining_free_swipes(user_id, settings, now)
        return {
            "accepted": True,
            "remainingFreeSwipes": remaining_after,
            "remainingFreePreferenceActions": remaining_after,
        }

    async def record_feed_impression(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: FeedImpressionPayload,
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        db_user_id = _canonical_user_uuid(user_id)
        event_uuid = str(UUID(payload.event_id))
        await self.session.execute(
            text(
                """
                insert into public.feed_impressions (
                  user_id, event_id, served_at, position, affinity_score, filters, market_key
                )
                select :user_id, :event_id,
                       coalesce(:served_at, now()),
                       :position, :affinity_score, cast(:filters as jsonb),
                       lower(v.city) || '|' || lower(coalesce(v.state, '')) || '|' || lower(coalesce(v.country, 'us'))
                  from public.events e
                  join public.venues v on v.id = e.venue_id
                 where e.id = :event_id
                """
            ),
            {
                "user_id": db_user_id,
                "event_id": event_uuid,
                "served_at": payload.served_at,
                "position": payload.position,
                "affinity_score": payload.affinity_score,
                "filters": json.dumps(payload.filters or {}),
            },
        )
        await self.session.commit()
        return {"ok": True}

    async def list_favorites(self, user_id: str) -> dict[str, Any]:
        await self.bootstrap_user(user_id, None)
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text(
                """
                with next_occurrence as (
                  select distinct on (eo.event_id)
                    eo.event_id,
                    eo.starts_at,
                    eo.ends_at
                  from public.event_occurrences eo
                  where eo.cancelled = false
                  order by eo.event_id, eo.starts_at asc
                )
                select
                  f.event_id::text as favorite_event_id,
                  e.id::text as id,
                  e.title,
                  coalesce(e.description, '') as description,
                  e.category,
                  coalesce(v.name, 'Unknown Venue') as venue_name,
                  coalesce(v.city, '') as city,
                  no.starts_at,
                  no.ends_at,
                  e.booking_url,
                  e.image_url,
                  e.price_label,
                  e.is_free
                from public.favorites f
                join public.events e on e.id = f.event_id
                left join public.venues v on v.id = e.venue_id
                left join next_occurrence no on no.event_id = e.id
                where f.user_id = :user_id
                order by f.created_at desc
                """
            ),
            {"user_id": db_user_id},
        )
        rows = [dict(row) for row in result.mappings().all()]
        favorite_ids = [str(row["favorite_event_id"]) for row in rows]

        event_ids = [str(row["id"]) for row in rows]
        tag_map: dict[str, list[str]] = {event_id: [] for event_id in event_ids}
        if event_ids:
            tag_result = await self.session.execute(
                text(
                    """
                    select event_id::text as event_id, tag
                    from public.event_tags
                    where event_id in :event_ids
                    order by event_id, tag
                    """
                ).bindparams(bindparam("event_ids", expanding=True)),
                {"event_ids": event_ids},
            )
            for row in tag_result.mappings().all():
                tag_map.setdefault(str(row["event_id"]), []).append(str(row["tag"]))

        events: list[dict[str, Any]] = []
        for row in rows:
            tags = tag_map.get(str(row["id"]), [])
            vibes = [tag for tag in tags if tag in _SUPPORTED_VIBE_TAGS]
            starts_at = row.get("starts_at")
            ends_at = row.get("ends_at")
            events.append(
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "description": row["description"],
                    "category": row["category"],
                    "venueName": row["venue_name"],
                    "city": row["city"],
                    "startsAt": starts_at.isoformat() if starts_at else datetime.now(tz=timezone.utc).isoformat(),
                    "endsAt": ends_at.isoformat() if ends_at else None,
                    "bookingUrl": row["booking_url"] or "",
                    "imageUrl": row["image_url"],
                    "priceLabel": row["price_label"],
                    "isFree": bool(row["is_free"]),
                    "radiusMiles": None,
                    "vibes": vibes or ["social"],
                    "tags": tags,
                }
            )

        return {"items": favorite_ids, "events": events}

    async def save_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        await self.bootstrap_user(user_id, None)
        db_user_id = _canonical_user_uuid(user_id)
        await self.session.execute(
            text(
                """
                insert into public.favorites (user_id, event_id)
                values (:user_id, :event_id)
                on conflict (user_id, event_id) do nothing
                """
            ),
            {"user_id": db_user_id, "event_id": str(UUID(event_id))},
        )
        await self.session.commit()
        return {"ok": True, "eventId": event_id}

    async def delete_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        await self.bootstrap_user(user_id, None)
        db_user_id = _canonical_user_uuid(user_id)
        await self.session.execute(
            text(
                """
                delete from public.favorites
                where user_id = :user_id and event_id = :event_id
                """
            ),
            {"user_id": db_user_id, "event_id": str(UUID(event_id))},
        )
        await self.session.commit()
        return {"ok": True, "eventId": event_id}

    async def report_event(
        self, user_id: str, event_id: str, reason: str, details: str | None
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, None)
        db_user_id = _canonical_user_uuid(user_id)
        event_uuid = str(UUID(event_id))
        await self.session.execute(
            text(
                """
                insert into public.event_reports (event_id, user_id, reason, details)
                values (:event_id, :user_id, :reason, :details)
                on conflict (event_id, user_id) do nothing
                """
            ),
            {
                "event_id": event_uuid,
                "user_id": db_user_id,
                "reason": reason,
                "details": details,
            },
        )
        await self.session.commit()

        count_result = await self.session.execute(
            text(
                "select count(distinct user_id) from public.event_reports where event_id = :event_id"
            ),
            {"event_id": event_uuid},
        )
        hidden_result = await self.session.execute(
            text("select hidden from public.events where id = :event_id"),
            {"event_id": event_uuid},
        )
        hidden_row = hidden_result.first()
        return {
            "ok": True,
            "eventId": event_id,
            "reportCount": int(count_result.scalar_one()),
            "hidden": bool(hidden_row[0]) if hidden_row else False,
        }

    async def get_entitlements(self, user_id: str, email: str | None) -> MembershipEntitlements:
        await self.bootstrap_user(user_id, email)
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text(
                """
                select is_premium, plan, valid_until
                from public.premium_entitlements
                where user_id = :user_id
                """
            ),
            {"user_id": db_user_id},
        )
        row = result.mappings().first()
        is_premium = bool(row["is_premium"]) if row else False
        plan = str(row["plan"]) if row else "free"
        valid_until = row["valid_until"] if row else None
        return MembershipEntitlements(
            isPremium=is_premium,
            plan=plan,
            unlimitedSwipes=is_premium,
            advancedFilters=is_premium,
            travelMode=is_premium,
            insiderTips=is_premium,
            validUntil=valid_until,
        )

    async def reset_seen_events(self, user_id: str) -> dict[str, Any]:
        db_user_id = _canonical_user_uuid(user_id)
        result = await self.session.execute(
            text("delete from public.feed_impressions where user_id = :user_id"),
            {"user_id": db_user_id},
        )
        await self.session.commit()
        return {"ok": True, "deleted": result.rowcount}


def build_repository(session: AsyncSession) -> AventiRepository:
    return PostgresAventiRepository(session)
