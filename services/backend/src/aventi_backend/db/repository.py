from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, tzinfo
from hashlib import sha256
from typing import Any, get_args
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.feed_query import FeedFilterContext, FeedItemFilter, FeedQueryBuilder
from aventi_backend.models.schemas import (
    EventVibeTag,
    FeedImpressionPayload,
    MembershipEntitlements,
    ProfileLocationPayload,
    SwipePayload,
    UserPreferences,
)
from aventi_backend.services.budgets import BudgetManager
from aventi_backend.services.market_inventory import (
    MarketWarmupService,
    build_market_descriptor,
)
from aventi_backend.services.personalization import apply_vibe_update

_SUPPORTED_VIBE_TAGS = set(get_args(EventVibeTag))
_DEFAULT_RADIUS_MILES = 10.0


def _canonical_user_uuid(user_id: str) -> str:
    try:
        return str(UUID(user_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"aventi:user:{user_id}"))


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _date_window(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(UTC)
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
    saturday = (now + timedelta(days=days_until_sat)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
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
        destination_id: str | None = None,
        start_date: Any = None,
        end_date: Any = None,
        premium_age_restriction: str = "all",
        query: str | None = None,
        request_ip: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def record_swipe(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: SwipePayload,
        settings: Settings,
        ensure_favorite: bool = False,
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
        deleted = await self.session.scalar(
            text("select exists(select 1 from public.account_deletions where user_id=:id)"),
            {"id": db_user_id},
        )
        if deleted:
            raise HTTPException(410, "Account deletion requested")
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
        created = (
            bool(profile_row["created"]) if profile_row and "created" in profile_row else False
        )
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
        categories = list(row["categories"] or []) if row else []
        vibes = list(row["vibes"] or []) if row else []
        return {
            "id": user_id,
            "email": (row["email"] if row else None) or email,
            "preferences": {
                "categories": categories,
                "vibes": vibes,
                "city": row["travel_mode_city"] if row else None,
                "radiusMiles": int(
                    row["radius_miles"] if row and row["radius_miles"] is not None else 10
                ),
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
                "select is_premium and valid_until > now() from public.premium_entitlements where user_id = :user_id"
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

    async def _remaining_free_swipes(
        self, user_id: str, settings: Settings, now: datetime
    ) -> int | None:
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
        destination_id: str | None = None,
        start_date: Any = None,
        end_date: Any = None,
        premium_age_restriction: str = "all",
        query: str | None = None,
        request_ip: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(tz=UTC)
        await self.bootstrap_user(user_id, None)
        db_user_id = _canonical_user_uuid(user_id)
        premium = await self._is_premium(user_id)
        radius_miles = radius_miles or 10
        if radius_miles not in {5, 10, 25, 50, 100}:
            raise HTTPException(422, "Unsupported radius")
        if not premium and (
            radius_miles != 10
            or destination_id
            or start_date
            or end_date
            or premium_age_restriction != "all"
        ):
            raise HTTPException(403, "Premium membership required")
        profile = (
            (
                await self.session.execute(
                    text("select latitude,longitude,timezone from public.profiles where id=:id"),
                    {"id": db_user_id},
                )
            )
            .mappings()
            .one()
        )
        local_tz = profile.get("timezone") or "UTC"
        if destination_id:
            dest = (
                (
                    await self.session.execute(
                        text("select * from public.destinations where id=:id"),
                        {"id": str(destination_id)},
                    )
                )
                .mappings()
                .first()
            )
            if not dest:
                raise HTTPException(422, "Unknown destination")
            latitude, longitude = float(dest["latitude"]), float(dest["longitude"])
            market_city, market_state, market_country = dest["city"], dest["state"], dest["country"]
            local_tz = dest["timezone"]
        elif profile["latitude"] is not None and profile["longitude"] is not None:
            # A free feed follows the saved device location, not arbitrary request coordinates.
            latitude, longitude = float(profile["latitude"]), float(profile["longitude"])
        else:
            raise HTTPException(422, "Set your device location first")
        tz: tzinfo
        try:
            tz = ZoneInfo(local_tz)
        except Exception:
            tz = UTC
        local_now = now.astimezone(tz)
        if bool(start_date) != bool(end_date):
            raise HTTPException(422, "Both travel dates are required")
        if start_date:
            if (
                start_date < local_now.date()
                or end_date < start_date
                or (end_date - start_date).days > 6
                or (end_date - local_now.date()).days > 60
            ):
                raise HTTPException(422, "Travel must be within 60 days, for at most seven days")
            start_ts = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
            end_ts = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        elif date == "week":
            start_ts, end_ts = local_now, local_now + timedelta(days=7)
        else:
            midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            if date == "tomorrow":
                midnight += timedelta(days=1)
            elif date == "weekend":
                midnight += timedelta(
                    days=0 if local_now.weekday() == 6 else (5 - local_now.weekday()) % 7
                )
            start_ts, end_ts = (
                midnight,
                midnight
                + timedelta(days=1 if date != "weekend" or local_now.weekday() == 6 else 2),
            )
        country = (market_country or "US").upper()
        remaining = await self._remaining_free_swipes(user_id, settings, now)
        base = {
            "remainingFreeSwipes": remaining,
            "remainingFreePreferenceActions": remaining,
            "resetAt": _utc_day_bounds(now)[1],
            "retryAt": None,
        }
        if country != "US":
            return {
                **base,
                "items": [],
                "nextCursor": None,
                "inventoryStatus": "unsupported",
                "warmupTriggered": False,
                "marketKey": None,
                "fallbackStatus": "insufficient_inventory",
            }
        signature = sha256(
            json.dumps(
                [
                    latitude,
                    longitude,
                    radius_miles,
                    date,
                    str(start_date),
                    str(end_date),
                    time_of_day,
                    price,
                    sorted(selected_vibes or []),
                    sorted(categories or []),
                    premium_age_restriction,
                    query,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        snapshot_ids = None
        position = 0
        session_id = str(uuid4())
        if cursor:
            try:
                session_id, raw_position = cursor.split(":")
                session_id = str(UUID(session_id))
                position = int(raw_position)
                if position < 0:
                    raise ValueError()
            except (ValueError, AttributeError):
                raise HTTPException(422, "Invalid feed cursor") from None
            snapshot = (
                (
                    await self.session.execute(
                        text(
                            "select event_ids,request_hash from public.feed_sessions where id=:id and user_id=:user and expires_at>now()"
                        ),
                        {"id": session_id, "user": db_user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not snapshot or snapshot["request_hash"] != signature:
                raise HTTPException(410, "Feed session expired; refresh discovery")
            snapshot_ids = [str(value) for value in snapshot["event_ids"]]
        result = (
            await FeedQueryBuilder(
                session=self.session,
                user_id=db_user_id,
                start_ts=start_ts,
                end_ts=end_ts,
                eligible_statuses=["verified"],
                seen_window_days=settings.seen_events_window_days,
                latitude=latitude,
                longitude=longitude,
                radius_miles=radius_miles,
                categories=categories,
                vibes=selected_vibes,
                age=premium_age_restriction,
                query=query,
                time_of_day=time_of_day,
                snapshot_ids=snapshot_ids,
            )
            .with_price_filter(price)
            .execute()
        )
        context = FeedFilterContext(
            user_latitude=latitude,
            user_longitude=longitude,
            radius_miles=radius_miles,
            time_of_day=time_of_day,
            selected_vibes=selected_vibes,
            categories=categories,
            supported_vibe_tags=_SUPPORTED_VIBE_TAGS,
        )
        scored = FeedItemFilter(context).filter_and_score(result)
        scored.sort(key=lambda item: (-item[0], item[1], item[2]["id"]))
        items_by_id = {item[2]["id"]: item[2] for item in scored}
        if snapshot_ids is None:
            snapshot_ids = list(items_by_id)
            await self.session.execute(
                text(
                    "insert into public.feed_sessions(id,user_id,event_ids,request_hash) values (:id,:user,cast(:ids as uuid[]),:hash)"
                ),
                {"id": session_id, "user": db_user_id, "ids": snapshot_ids, "hash": signature},
            )
            await self.session.commit()
        items: list[dict[str, Any]] = []
        while position < len(snapshot_ids) and len(items) < limit:
            event = items_by_id.get(snapshot_ids[position])
            position += 1
            if event:
                items.append(event)
        next_cursor = f"{session_id}:{position}" if position < len(snapshot_ids) else None
        market = build_market_descriptor(
            city=market_city,
            state=market_state,
            country=country,
            center_latitude=latitude,
            center_longitude=longitude,
        )
        market_key = market.key if market else None
        inventory = "ready" if items else "no_matches"
        budgets = BudgetManager(self.session, settings=settings)

        async def provider_budget_state() -> tuple[bool, datetime | None]:
            providers = ("serpapi", "gemini", "geocoding", "pollinations")
            remaining = {
                provider: await budgets.remaining(provider) for provider in providers
            }
            exhausted = [provider for provider, units in remaining.items() if units <= 0]
            if not exhausted:
                return True, None
            resets = [await budgets.next_reset_at(provider) for provider in exhausted]
            # Missing/disabled configuration has no time-based reset, so do not
            # promise a retry time that cannot make processing available.
            if any(reset is None for reset in resets):
                return False, None
            return False, max(reset for reset in resets if reset is not None)

        processing_available, budget_retry_at = await provider_budget_state()
        if not processing_available:
            inventory = "budget_paused"
            base["retryAt"] = budget_retry_at
        triggered = False
        if not items and market and not cursor:
            if not processing_available:
                inventory = "budget_paused"
            else:
                market_key, inventory, triggered = await MarketWarmupService(
                    self.session
                ).request_warmup(
                    market,
                    force_refresh=False,
                    visible_count=len(items),
                    admission_limits=[
                        (f"discovery-user:{db_user_id}", 6),
                        (f"discovery-ip:{request_ip or db_user_id}", 30),
                    ],
                    start_date=str(start_date) if start_date else None,
                    end_date=str(end_date) if end_date else None,
                )
                await self.session.commit()
                if inventory == "budget_paused":
                    _, base["retryAt"] = await provider_budget_state()
                elif inventory == "unavailable":
                    base["retryAt"] = _utc_day_bounds(now)[1]
        return {
            **base,
            "items": items,
            "nextCursor": next_cursor,
            "fallbackStatus": "none" if items else "insufficient_inventory",
            "marketKey": market_key,
            "inventoryStatus": inventory,
            "warmupTriggered": triggered,
        }

    async def record_swipe(
        self,
        *,
        user_id: str,
        email: str | None,
        payload: SwipePayload,
        settings: Settings,
        ensure_favorite: bool = False,
    ) -> dict[str, Any]:
        await self.bootstrap_user(user_id, email)
        now = datetime.now(tz=UTC)
        db_user_id = _canonical_user_uuid(user_id)
        await self.session.execute(
            text("select id from public.profiles where id=:id for update"), {"id": db_user_id}
        )
        if ensure_favorite and await self.session.scalar(
            text("select exists(select 1 from favorites where user_id=:user and event_id=:event)"),
            {"user": db_user_id, "event": str(UUID(payload.event_id))},
        ):
            remaining = await self._remaining_free_swipes(user_id, settings, now)
            await self.session.commit()
            return {
                "accepted": True,
                "favorite": True,
                "remainingFreePreferenceActions": remaining,
                "remainingFreeSwipes": remaining,
                "resetAt": _utc_day_bounds(now)[1].isoformat(),
            }
        prior = (
            (
                await self.session.execute(
                    text(
                        "select event_id,action,result from public.swipe_actions where user_id=:user and action_id=:action"
                    ),
                    {"user": db_user_id, "action": str(payload.action_id)},
                )
            )
            .mappings()
            .first()
        )
        if prior:
            if str(prior["event_id"]) != payload.event_id or prior["action"] != payload.action:
                raise HTTPException(409, "Action ID already used for another action")
            await self.session.commit()
            return dict(prior["result"])
        eligible = await self.session.scalar(
            text("""select exists(select 1 from public.events e join public.event_occurrences o on o.event_id=e.id
            where e.id=:id and not e.hidden and e.verification_status='verified' and e.last_verified_active is true and e.last_verified_at>=now()-interval '72 hours'
            and not o.cancelled and o.starts_at>=now())"""),
            {"id": str(UUID(payload.event_id))},
        )
        if not eligible:
            raise HTTPException(409, "Event is no longer available")
        remaining = await self._remaining_free_swipes(user_id, settings, now)
        if remaining is not None and remaining <= 0:
            raise PermissionError("Free preference action limit reached")

        db_user_id = _canonical_user_uuid(user_id)
        event_uuid = str(UUID(payload.event_id))

        await self.session.execute(
            text(
                """
                insert into public.swipe_actions (
                    user_id, event_id, action, surfaced_at, position, market_key, action_id
                )
                select :user_id, :event_id, :action, :surfaced_at, :position,
                       lower(v.city) || '|' || lower(coalesce(v.state, '')) || '|' || lower(coalesce(v.country, 'us')), :action_id
                  from public.events e
                  join public.venues v on v.id = e.venue_id
                 where e.id = :event_id
                """
            ),
            {
                "user_id": db_user_id,
                "event_id": event_uuid,
                "action": payload.action,
                "action_id": str(payload.action_id),
                "surfaced_at": payload.surfaced_at,
                "position": payload.position,
            },
        )

        vibes = list(
            (
                await self.session.execute(
                    text(
                        "select tag from public.event_tags where event_id=:id and tag_type='vibe'"
                    ),
                    {"id": event_uuid},
                )
            )
            .scalars()
            .all()
        )
        if vibes:
            existing_result = await self.session.execute(
                text(
                    """
                    select vibe, weight
                    from public.user_vibe_weights
                    where user_id = :user_id
                      and vibe in :vibes
                    """
                ).bindparams(bindparam("vibes", expanding=True)),
                {"user_id": db_user_id, "vibes": list(vibes)},
            )
            existing = {str(row[0]): float(row[1]) for row in existing_result.all()}
            updated = apply_vibe_update(existing, vibes, payload.action)
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

        if payload.action == "like":
            await self.session.execute(
                text(
                    "insert into public.favorites(user_id,event_id) values (:user,:event) on conflict do nothing"
                ),
                {"user": db_user_id, "event": event_uuid},
            )
        remaining_after = await self._remaining_free_swipes(user_id, settings, now)
        result = {
            "accepted": True,
            "remainingFreeSwipes": remaining_after,
            "remainingFreePreferenceActions": remaining_after,
            "actionId": str(payload.action_id),
            "favorite": payload.action == "like",
            "resetAt": _utc_day_bounds(now)[1].isoformat(),
        }
        await self.session.execute(
            text(
                "update public.swipe_actions set result=cast(:result as jsonb) where user_id=:user and action_id=:id"
            ),
            {"result": json.dumps(result), "user": db_user_id, "id": str(payload.action_id)},
        )
        await self.session.commit()
        return result

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
            for tag_row in tag_result.mappings().all():
                tag_map.setdefault(str(tag_row["event_id"]), []).append(str(tag_row["tag"]))

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
                    "startsAt": starts_at.isoformat()
                    if starts_at
                    else datetime.now(tz=UTC).isoformat(),
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
        exists = await self.session.scalar(
            text("select exists(select 1 from favorites where user_id=:user and event_id=:event)"),
            {"user": _canonical_user_uuid(user_id), "event": str(UUID(event_id))},
        )
        if exists:
            return {"ok": True, "eventId": event_id, "favorite": True}
        result = await self.record_swipe(
            user_id=user_id,
            email=None,
            settings=get_settings(),
            ensure_favorite=True,
            payload=SwipePayload(
                eventId=event_id,
                action="like",
                actionId=uuid4(),
                surfacedAt=datetime.now(UTC),
                position=0,
                vibes=[],
            ),
        )
        return {**result, "ok": True, "eventId": event_id}

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
        is_premium = bool(
            row
            and row["is_premium"]
            and row["valid_until"]
            and row["valid_until"] > datetime.now(UTC)
        )
        valid_until = row["valid_until"] if row else None
        return MembershipEntitlements(
            isPremium=is_premium,
            plan="unlimited" if is_premium else "free",
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
        return {"ok": True, "deleted": getattr(result, "rowcount", 0)}


def build_repository(session: AsyncSession) -> AventiRepository:
    return PostgresAventiRepository(session)
