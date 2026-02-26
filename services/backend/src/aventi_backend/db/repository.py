from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.models.schemas import (
    FeedImpressionPayload,
    MembershipEntitlements,
    ProfileLocationPayload,
    SwipePayload,
    UserPreferences,
)
from aventi_backend.services.feed import get_seed_feed
from aventi_backend.services.personalization import apply_vibe_update

_SUPPORTED_VIBE_TAGS = {
    "chill",
    "energetic",
    "romantic",
    "social",
    "luxury",
    "live-music",
    "wellness",
    "late-night",
}


def _canonical_user_uuid(user_id: str) -> str:
    try:
        return str(UUID(user_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"aventi:user:{user_id}"))


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _time_of_day_matches(starts_at: datetime, bucket: str | None) -> bool:
    if not bucket:
        return True
    hour = starts_at.astimezone(timezone.utc).hour
    match bucket:
        case "morning":
            return 5 <= hour < 12
        case "afternoon":
            return 12 <= hour < 17
        case "evening":
            return 17 <= hour < 22
        case "night":
            return hour >= 22 or hour < 5
        case _:
            return True


def _date_window(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(timezone.utc)
    if date_filter == "today":
        start = now
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


def _haversine_miles(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> float | None:
    if lat2 is None or lon2 is None:
        return None
    # Light approximation is fine for scaffold filtering.
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


def _decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _encode_offset_cursor(offset: int) -> str | None:
    return str(offset) if offset > 0 else None


@dataclass(slots=True)
class _MemoryState:
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    preferences: dict[str, dict[str, Any]] = field(default_factory=dict)
    favorites: dict[str, set[str]] = field(default_factory=dict)
    reports: dict[str, set[str]] = field(default_factory=dict)
    hidden_events: set[str] = field(default_factory=set)
    swipes: dict[str, list[datetime]] = field(default_factory=dict)
    vibe_weights: dict[str, dict[str, float]] = field(default_factory=dict)
    entitlements: dict[str, dict[str, Any]] = field(default_factory=dict)
    feed_impressions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


_MEMORY_STATE = _MemoryState()


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
        cursor: str | None,
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


class InMemoryAventiRepository(AventiRepository):
    def __init__(self, state: _MemoryState) -> None:
        self.state = state

    async def bootstrap_user(self, user_id: str, email: str | None) -> dict[str, Any]:
        created = user_id not in self.state.profiles
        self.state.profiles.setdefault(
            user_id,
            {
                "id": user_id,
                "email": email,
                "city": None,
                "timezone": None,
                "latitude": None,
                "longitude": None,
                "onboarding_completed": False,
            },
        )
        self.state.preferences.setdefault(
            user_id,
            {"categories": [], "vibes": [], "city": None, "radiusMiles": 10},
        )
        self.state.entitlements.setdefault(
            user_id,
            {
                "isPremium": False,
                "plan": "free",
                "unlimitedSwipes": False,
                "advancedFilters": False,
                "travelMode": False,
                "insiderTips": False,
                "validUntil": None,
            },
        )
        return {
            "id": user_id,
            "email": email,
            "created": created,
            "profile": {
                "city": self.state.profiles[user_id]["city"],
                "timezone": self.state.profiles[user_id]["timezone"],
                "latitude": self.state.profiles[user_id]["latitude"],
                "longitude": self.state.profiles[user_id]["longitude"],
                "onboarded": self.state.profiles[user_id]["onboarding_completed"],
            },
        }

    async def get_me(self, user_id: str, email: str | None) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        profile = self.state.profiles[user_id]
        prefs = self.state.preferences[user_id]
        return {
            "id": user_id,
            "email": profile.get("email") or email,
            "preferences": prefs,
            "profile": {
                "city": profile.get("city"),
                "timezone": profile.get("timezone"),
                "latitude": profile.get("latitude"),
                "longitude": profile.get("longitude"),
                "onboarded": profile.get("onboarding_completed"),
            },
        }

    async def update_preferences(self, user_id: str, payload: UserPreferences) -> dict[str, Any]:
        current = self.state.preferences.setdefault(
            user_id, {"categories": [], "vibes": [], "city": None, "radiusMiles": 10}
        )
        current.update(payload.model_dump(by_alias=True))
        return {"ok": True, "userId": user_id, "preferences": current}

    async def update_profile_location(
        self, user_id: str, email: str | None, payload: ProfileLocationPayload
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        profile = self.state.profiles[user_id]
        profile["city"] = payload.city
        profile["timezone"] = payload.timezone
        profile["latitude"] = payload.latitude
        profile["longitude"] = payload.longitude
        profile["onboarding_completed"] = True
        return {
            "ok": True,
            "userId": user_id,
            "profile": {
                "city": profile["city"],
                "timezone": profile["timezone"],
                "latitude": profile["latitude"],
                "longitude": profile["longitude"],
                "onboarded": profile["onboarding_completed"],
            },
        }

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
        cursor: str | None,
    ) -> dict[str, Any]:
        _ = (user_id, date, latitude, longitude, time_of_day, price, radius_miles)
        response = get_seed_feed(settings).model_dump(by_alias=True)
        items = [item for item in response["items"] if item["id"] not in self.state.hidden_events]
        offset = _decode_offset_cursor(cursor)
        response["items"] = items[offset : offset + limit]
        response["nextCursor"] = (
            _encode_offset_cursor(offset + limit) if len(items) > offset + limit else None
        )
        now = datetime.now(tz=timezone.utc)
        remaining = self._remaining_free_swipes(user_id, settings, now)
        response["remainingFreeSwipes"] = remaining
        response["remainingFreePreferenceActions"] = remaining
        if not response["items"]:
            response["fallbackStatus"] = "insufficient_inventory"
        return response

    def _remaining_free_swipes(self, user_id: str, settings: Settings, now: datetime) -> int:
        start, end = _utc_day_bounds(now)
        swipes = self.state.swipes.get(user_id, [])
        todays = [t for t in swipes if start <= t < end]
        self.state.swipes[user_id] = todays
        return max(0, settings.free_swipe_limit - len(todays))

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
        remaining_before = self._remaining_free_swipes(user_id, settings, now)
        if remaining_before <= 0:
            raise PermissionError("Free preference action limit reached")
        self.state.swipes.setdefault(user_id, []).append(now)
        self.state.vibe_weights[user_id] = apply_vibe_update(
            self.state.vibe_weights.get(user_id, {}), payload.vibes, payload.action
        )
        remaining_after = self._remaining_free_swipes(user_id, settings, now)
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
        self.state.feed_impressions.setdefault(user_id, []).append(
            {
                "eventId": payload.event_id,
                "servedAt": (payload.served_at or datetime.now(tz=timezone.utc)).isoformat(),
                "position": payload.position,
                "affinityScore": payload.affinity_score,
                "filters": payload.filters,
            }
        )
        return {"ok": True}

    async def list_favorites(self, user_id: str) -> dict[str, Any]:
        favorite_ids = sorted(self.state.favorites.get(user_id, set()))
        seed_items = get_seed_feed(get_settings()).model_dump(by_alias=True)["items"]
        seed_by_id = {str(item["id"]): item for item in seed_items}
        events = [seed_by_id[favorite_id] for favorite_id in favorite_ids if favorite_id in seed_by_id]
        return {"items": favorite_ids, "events": events}

    async def save_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        self.state.favorites.setdefault(user_id, set()).add(event_id)
        return {"ok": True, "eventId": event_id}

    async def delete_favorite(self, user_id: str, event_id: str) -> dict[str, Any]:
        self.state.favorites.setdefault(user_id, set()).discard(event_id)
        return {"ok": True, "eventId": event_id}

    async def report_event(
        self, user_id: str, event_id: str, reason: str, details: str | None
    ) -> dict[str, Any]:
        _ = (reason, details)
        reporters = self.state.reports.setdefault(event_id, set())
        reporters.add(user_id)
        if len(reporters) >= 3:
            self.state.hidden_events.add(event_id)
        return {
            "ok": True,
            "eventId": event_id,
            "reportCount": len(reporters),
            "hidden": event_id in self.state.hidden_events,
        }

    async def get_entitlements(self, user_id: str, email: str | None) -> MembershipEntitlements:
        await self.bootstrap_user(user_id, email)
        return MembershipEntitlements.model_validate(self.state.entitlements[user_id])


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
        cursor: str | None,
    ) -> dict[str, Any]:
        offset = _decode_offset_cursor(cursor)
        now = datetime.now(tz=timezone.utc)
        await self.bootstrap_user(user_id, None)
        start_ts, end_ts = _date_window(date, now)
        db_user_id = _canonical_user_uuid(user_id)
        price_clause = ""
        query_params: dict[str, Any] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "limit_rows": max((offset + limit) * 4, 20),
        }
        verification_clause = ""
        if settings.feed_verification_max_age_hours > 0:
            verification_cutoff = now - timedelta(hours=settings.feed_verification_max_age_hours)
            unverified_grace_cutoff = now - timedelta(
                hours=max(0, settings.feed_unverified_grace_hours)
            )
            query_params["verification_cutoff_ts"] = verification_cutoff
            query_params["unverified_grace_cutoff_ts"] = unverified_grace_cutoff
            verification_clause = """
                  and (
                    (lv.event_id is not null and lv.active = true and lv.verified_at >= :verification_cutoff_ts)
                    or (lv.event_id is null and e.created_at >= :unverified_grace_cutoff_ts)
                  )
            """
        if price in {"free", "paid"}:
            price_clause = "and e.is_free = :is_free"
            query_params["is_free"] = price == "free"

        recent_passes_result = await self.session.execute(
            text(
                """
                select sa.event_id::text as event_id, e.normalized_title
                from public.swipe_actions sa
                join public.events e on e.id = sa.event_id
                where sa.user_id = :user_id
                  and sa.action = 'pass'
                order by sa.created_at desc
                limit 100
                """
            ),
            {"user_id": db_user_id},
        )
        recent_passed_event_ids: set[str] = set()
        recent_passed_titles: set[str] = set()
        for row in recent_passes_result.mappings().all():
            recent_passed_event_ids.add(str(row["event_id"]))
            normalized_title = row.get("normalized_title")
            if normalized_title:
                recent_passed_titles.add(str(normalized_title))

        weights_result = await self.session.execute(
            text(
                """
                select vibe, weight
                from public.user_vibe_weights
                where user_id = :user_id
                """
            ),
            {"user_id": db_user_id},
        )
        user_weights = {str(row[0]): float(row[1]) for row in weights_result.all()}

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
                    and eo.starts_at >= :start_ts
                    and eo.starts_at < :end_ts
                  order by eo.event_id, eo.starts_at asc
                ), latest_verification as (
                  select distinct on (vr.event_id)
                    vr.event_id,
                    vr.verified_at,
                    vr.active
                  from public.verification_runs vr
                  order by vr.event_id, vr.verified_at desc
                )
                select
                  e.id::text as id,
                  e.title,
                  e.normalized_title,
                  coalesce(e.description, '') as description,
                  e.category,
                  coalesce(v.name, 'Unknown Venue') as venue_name,
                  coalesce(v.city, '') as city,
                  no.starts_at,
                  no.ends_at,
                  e.booking_url,
                  e.image_url,
                  e.price_label,
                  e.is_free,
                  v.latitude,
                  v.longitude
                from public.events e
                join next_occurrence no on no.event_id = e.id
                left join public.venues v on v.id = e.venue_id
                left join latest_verification lv on lv.event_id = e.id
                where e.hidden = false
                  {price_clause}
                  {verification_clause}
                order by no.starts_at asc, e.created_at desc
                limit :limit_rows
                """
                .format(price_clause=price_clause, verification_clause=verification_clause)
            ),
            query_params,
        )
        rows = [dict(row) for row in result.mappings().all()]

        event_ids = [row["id"] for row in rows]
        tag_map: dict[str, list[str]] = {event_id: [] for event_id in event_ids}
        if event_ids:
            tag_result = await self.session.execute(
                text(
                    """
                    select event_id::text as event_id, tag, tag_type
                    from public.event_tags
                    where event_id in :event_ids
                    order by event_id, tag_type, tag
                    """
                ).bindparams(bindparam("event_ids", expanding=True)),
                {"event_ids": event_ids},
            )
            for row in tag_result.mappings().all():
                tag_map.setdefault(row["event_id"], []).append(str(row["tag"]))

        scored_items: list[tuple[float, datetime, dict[str, Any]]] = []
        for row in rows:
            if row["id"] in recent_passed_event_ids:
                continue
            if row.get("normalized_title") and str(row["normalized_title"]) in recent_passed_titles:
                continue

            miles = _haversine_miles(latitude, longitude, row.get("latitude"), row.get("longitude"))
            if radius_miles is not None and miles is not None and miles > radius_miles:
                continue
            starts_at = row["starts_at"]
            if not _time_of_day_matches(starts_at, time_of_day):
                continue

            tags = tag_map.get(row["id"], [])
            vibes = [tag for tag in tags if tag in _SUPPORTED_VIBE_TAGS]
            effective_vibes = vibes or ["social"]
            affinity = sum(user_weights.get(vibe, 1.0) for vibe in effective_vibes)
            # Small freshness bias: earlier events win tie-breaks.
            freshness_bias = max(0.0, 1_000_000_000 - starts_at.timestamp()) * 1e-12
            item = {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
                "venueName": row["venue_name"],
                "city": row["city"],
                "startsAt": starts_at.isoformat(),
                "endsAt": row["ends_at"].isoformat() if row["ends_at"] else None,
                "bookingUrl": row["booking_url"],
                "imageUrl": row["image_url"],
                "priceLabel": row["price_label"],
                "isFree": bool(row["is_free"]),
                "radiusMiles": miles,
                "vibes": effective_vibes,
                "tags": tags,
            }
            scored_items.append(
                (
                    affinity + freshness_bias,
                    starts_at,
                    item,
                )
            )

        scored_items.sort(key=lambda entry: (-entry[0], entry[1]))
        page_slice = scored_items[offset : offset + limit]
        items = [item for _, _, item in page_slice]
        next_cursor = (
            _encode_offset_cursor(offset + limit) if len(scored_items) > offset + limit else None
        )

        remaining = await self._remaining_free_swipes(user_id, settings, now)

        # Fallback to seed data only when the events table is actually empty (early development).
        if not items and offset == 0 and not recent_passed_event_ids:
            total_events = await self.session.scalar(text("select count(*) from public.events"))
            if int(total_events or 0) == 0:
                seed_repo = InMemoryAventiRepository(_MemoryState())
                return await seed_repo.get_feed(
                    user_id=user_id,
                    settings=settings,
                    date=date,
                    latitude=latitude,
                    longitude=longitude,
                    limit=limit,
                    time_of_day=None,  # Don't filter seed data by time
                    price=price,
                    radius_miles=None,  # Don't filter seed data by radius
                    cursor=cursor,
                )

        return {
            "items": items,
            "nextCursor": next_cursor,
            "fallbackStatus": "none" if items else "insufficient_inventory",
            "remainingFreeSwipes": remaining,
            "remainingFreePreferenceActions": remaining,
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
                insert into public.swipe_actions (user_id, event_id, action, surfaced_at, position)
                values (:user_id, :event_id, :action, :surfaced_at, :position)
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
                  user_id, event_id, served_at, position, affinity_score, filters
                )
                values (
                  :user_id,
                  :event_id,
                  coalesce(:served_at, now()),
                  :position,
                  :affinity_score,
                  cast(:filters as jsonb)
                )
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


_MEMORY_REPOSITORY = InMemoryAventiRepository(_MEMORY_STATE)


def build_repository(session: AsyncSession | None) -> AventiRepository:
    if session is None:
        return _MEMORY_REPOSITORY
    return PostgresAventiRepository(session)
