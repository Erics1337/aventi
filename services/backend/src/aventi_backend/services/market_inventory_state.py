from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.market_descriptors import (
    MarketDescriptor,
    build_market_descriptor,
    coerce_float,
    optional_str,
)
from aventi_backend.services.market_filters import coerce_utc_datetime

_UNSET = object()


class MarketInventoryStateStore:
    def __init__(
        self,
        session: AsyncSession,
        *,
        active_window: timedelta,
        heat_warm_window: timedelta,
        hot_min_users_7d: int,
        eligible_verification_statuses: tuple[str, ...],
    ) -> None:
        self.session = session
        self.active_window = active_window
        self.heat_warm_window = heat_warm_window
        self.hot_min_users_7d = hot_min_users_7d
        self.eligible_verification_statuses = eligible_verification_statuses

    async def touch_market_request(self, market: MarketDescriptor) -> None:
        await self.upsert_market_state(market, last_requested_at=datetime.now(tz=UTC))

    async def visible_event_count(self, market: MarketDescriptor, now: datetime) -> int:
        result = await self.session.scalar(
            text(
                """
                select count(distinct e.id)
                from public.events e
                join public.venues v on v.id = e.venue_id
                join public.event_occurrences eo on eo.event_id = e.id
                where eo.cancelled = false
                  and eo.starts_at >= :start_ts
                  and eo.starts_at < :end_ts
                  and e.hidden = false
                  and e.verification_status = any(:eligible_statuses)
                  and lower(v.city) = :city
                  and (lower(coalesce(v.state, '')) = :state or v.state is null)
                  and lower(coalesce(v.country, 'us')) = :country
                """
            ),
            {
                "start_ts": now,
                "end_ts": now + self.active_window,
                "eligible_statuses": list(self.eligible_verification_statuses),
                "city": market.city.lower(),
                "state": (market.state or "").lower(),
                "country": market.country.lower(),
            },
        )
        return int(result or 0)

    async def refresh_market_inventory_state(self, market: MarketDescriptor) -> int:
        now = datetime.now(tz=UTC)
        visible_count = await self.visible_event_count(market, now)
        await self.upsert_market_state(market, visible_event_count_7d=visible_count)
        return visible_count

    async def sync_market_inventory_from_event_venues(self) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                select
                    trim(v.city) as city,
                    nullif(trim(coalesce(v.state, '')), '') as state,
                    upper(coalesce(nullif(trim(v.country), ''), 'US')) as country,
                    max(v.latitude) as center_latitude,
                    max(v.longitude) as center_longitude
                from public.events e
                join public.venues v on v.id = e.venue_id
                join public.event_occurrences eo on eo.event_id = e.id
                where e.hidden = false
                  and eo.cancelled = false
                  and eo.starts_at >= now() - interval '90 days'
                  and eo.starts_at < now() + interval '120 days'
                group by trim(v.city), nullif(trim(coalesce(v.state, '')), ''),
                         upper(coalesce(nullif(trim(v.country), ''), 'US'))
                having length(trim(v.city)) > 0
                """
            )
        )
        rows = result.mappings().all()
        synced = 0
        for row in rows:
            market = build_market_descriptor(
                city=str(row["city"]),
                state=row["state"],
                country=str(row["country"] or "US"),
                center_latitude=coerce_float(row["center_latitude"]),
                center_longitude=coerce_float(row["center_longitude"]),
            )
            if market is None:
                continue
            await self.refresh_market_inventory_state(market)
            synced += 1
        heat = await self.recompute_all_heat()
        return {"synced": synced, "marketsConsidered": len(rows), "heat": heat}

    async def get_market_by_key(self, market_key: str) -> MarketDescriptor | None:
        row = (
            await self.session.execute(
                text(
                    """
                    select market_key, city, state, country,
                           center_latitude, center_longitude, heat_tier
                    from public.market_inventory_state
                    where market_key = :market_key
                    """
                ),
                {"market_key": market_key},
            )
        ).mappings().first()
        if not row:
            return None
        return MarketDescriptor(
            key=str(row["market_key"]),
            city=str(row["city"]),
            state=optional_str(row["state"]),
            country=str(row["country"] or "US"),
            center_latitude=coerce_float(row["center_latitude"]),
            center_longitude=coerce_float(row["center_longitude"]),
            heat_tier=str(row["heat_tier"] or "cold"),
        )

    async def has_active_discovery_jobs(self, market_key: str) -> bool:
        lock_until = await self.scan_lock_until(market_key)
        return lock_until is not None and lock_until > datetime.now(tz=UTC)

    async def scan_lock_until(self, market_key: str) -> datetime | None:
        lock_until = await self.session.scalar(
            text(
                """
                select scan_lock_until
                from public.market_inventory_state
                where market_key = :market_key
                """
            ),
            {"market_key": market_key},
        )
        if lock_until and getattr(lock_until, "tzinfo", None) is None:
            lock_until = lock_until.replace(tzinfo=UTC)
        return lock_until if isinstance(lock_until, datetime) else None

    async def targeted_mining_state(self, market_key: str) -> dict[str, Any] | None:
        row = await self.session.execute(
            text(
                """
                select
                  last_targeted_filter_signature,
                  last_targeted_requested_at,
                  last_targeted_completed_at
                from public.market_inventory_state
                where market_key = :market_key
                """
            ),
            {"market_key": market_key},
        )
        state = row.mappings().first()
        if not state:
            return None
        return {
            "last_targeted_filter_signature": state["last_targeted_filter_signature"],
            "last_targeted_requested_at": coerce_utc_datetime(
                state["last_targeted_requested_at"]
            ),
            "last_targeted_completed_at": coerce_utc_datetime(
                state["last_targeted_completed_at"]
            ),
        }

    async def scheduled_warmup_markets(
        self,
        *,
        limit: int,
        target_count: int,
        now: datetime,
    ) -> list[MarketDescriptor]:
        result = await self.session.execute(
            text(
                """
                select market_key, city, state, country, center_latitude, center_longitude
                from public.market_inventory_state
                where last_requested_at >= :active_cutoff
                  and coalesce(visible_event_count_7d, 0) < :target_count
                  and (scan_lock_until is null or scan_lock_until <= :now_ts)
                order by last_requested_at desc nulls last
                limit :limit_rows
                """
            ),
            {
                "active_cutoff": now - self.active_window,
                "target_count": target_count,
                "now_ts": now,
                "limit_rows": limit,
            },
        )
        return [
            MarketDescriptor(
                key=str(row["market_key"]),
                city=str(row["city"]),
                state=optional_str(row["state"]),
                country=optional_str(row["country"]) or "US",
                center_latitude=coerce_float(row["center_latitude"]),
                center_longitude=coerce_float(row["center_longitude"]),
            )
            for row in result.mappings().all()
        ]

    async def list_active_markets(self, *, limit: int = 200) -> list[MarketDescriptor]:
        now = datetime.now(tz=UTC)
        result = await self.session.execute(
            text(
                """
                select market_key, city, state, country,
                       center_latitude, center_longitude, heat_tier
                from public.market_inventory_state
                where heat_tier in ('hot', 'warm')
                  and (scan_lock_until is null or scan_lock_until <= :now_ts)
                order by case heat_tier when 'hot' then 0 else 1 end,
                         last_user_active_at desc nulls last
                limit :limit_rows
                """
            ),
            {"now_ts": now, "limit_rows": limit},
        )
        return [
            MarketDescriptor(
                key=str(row["market_key"]),
                city=str(row["city"]),
                state=optional_str(row["state"]),
                country=optional_str(row["country"]) or "US",
                center_latitude=coerce_float(row["center_latitude"]),
                center_longitude=coerce_float(row["center_longitude"]),
                heat_tier=str(row["heat_tier"] or "cold"),
            )
            for row in result.mappings().all()
        ]

    async def recompute_all_heat(self) -> dict[str, int]:
        now = datetime.now(tz=UTC)
        result = await self.session.execute(
            text(
                """
                with activity as (
                  select market_key,
                         count(distinct user_id) filter (where ts >= :hot_cutoff) as u7,
                         count(distinct user_id) filter (where ts >= :warm_cutoff) as u14,
                         max(ts) as last_active
                  from (
                    select market_key, user_id, created_at as ts
                      from public.swipe_actions where market_key is not null
                    union all
                    select market_key, user_id, served_at as ts
                      from public.feed_impressions where market_key is not null
                  ) events
                  group by market_key
                )
                update public.market_inventory_state mis
                set active_user_count_7d  = coalesce(a.u7, 0),
                    active_user_count_14d = coalesce(a.u14, 0),
                    last_user_active_at   = a.last_active,
                    heat_tier = case
                      when coalesce(a.u7, 0)  >= :hot_min then 'hot'
                      when coalesce(a.u14, 0) >= 1        then 'warm'
                      else 'cold'
                    end,
                    updated_at = now()
                from activity a
                where mis.market_key = a.market_key
                returning mis.heat_tier
                """
            ),
            {
                "hot_min": self.hot_min_users_7d,
                "hot_cutoff": now - timedelta(days=7),
                "warm_cutoff": now - self.heat_warm_window,
            },
        )
        rows = result.mappings().all()
        backfill_result = await self.session.execute(
            text(
                """
                update public.market_inventory_state
                set heat_tier = 'cold',
                    active_user_count_7d = 0,
                    active_user_count_14d = 0,
                    updated_at = now()
                where (last_user_active_at is null
                       or last_user_active_at < :warm_cutoff)
                  and heat_tier <> 'cold'
                """
            ),
            {"warm_cutoff": now - self.heat_warm_window},
        )
        await self.session.commit()
        tiers = [str(r.get("heat_tier") or "cold") for r in rows]
        backfill_count = backfill_result.rowcount
        return {
            "updated": len(tiers) + backfill_count,
            "hot": sum(1 for t in tiers if t == "hot"),
            "warm": sum(1 for t in tiers if t == "warm"),
            "cold": sum(1 for t in tiers if t == "cold") + backfill_count,
        }

    async def mark_user_active(self, market: MarketDescriptor) -> None:
        now = datetime.now(tz=UTC)
        await self.session.execute(
            text(
                """
                update public.market_inventory_state
                set last_user_active_at = :now_ts,
                    heat_tier = case
                      when heat_tier = 'hot' then 'hot'
                      else 'warm'
                    end,
                    updated_at = now()
                where market_key = :market_key
                """
            ),
            {"now_ts": now, "market_key": market.key},
        )
        await self.session.commit()

    async def bootstrap_market_if_new(self, market: MarketDescriptor) -> bool:
        now = datetime.now(tz=UTC)
        result = await self.session.scalar(
            text(
                """
                insert into public.market_inventory_state (
                    market_key, city, state, country,
                    center_latitude, center_longitude,
                    last_user_active_at, heat_tier,
                    created_at, updated_at
                )
                values (
                    :market_key, :city, :state, :country,
                    :center_latitude, :center_longitude,
                    :now_ts, 'warm',
                    now(), now()
                )
                on conflict (market_key) do nothing
                returning market_key
                """
            ),
            {
                "market_key": market.key,
                "city": market.city,
                "state": market.state,
                "country": market.country,
                "center_latitude": market.center_latitude,
                "center_longitude": market.center_longitude,
                "now_ts": now,
            },
        )
        await self.session.commit()
        return result is not None

    async def mark_scan_started(self, market: MarketDescriptor, started_at: datetime) -> None:
        await self.upsert_market_state(market, last_scan_started_at=started_at, last_error=None)

    async def mark_scan_completed(
        self,
        market: MarketDescriptor,
        *,
        success: bool,
        error: str | None,
    ) -> None:
        now = datetime.now(tz=UTC)
        await self.upsert_market_state(
            market,
            last_scan_completed_at=now,
            last_scan_succeeded_at=now if success else None,
            last_error=error,
        )

    async def upsert_market_state(
        self,
        market: MarketDescriptor,
        *,
        last_requested_at: datetime | None = None,
        last_scan_requested_at: datetime | None = None,
        last_scan_started_at: datetime | None = None,
        last_scan_completed_at: datetime | None = None,
        last_scan_succeeded_at: datetime | None = None,
        scan_lock_until: datetime | None = None,
        visible_event_count_7d: int | None = None,
        last_targeted_filter_signature: str | None | object = _UNSET,
        last_targeted_requested_at: datetime | None | object = _UNSET,
        last_targeted_completed_at: datetime | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into public.market_inventory_state (
                  market_key, city, state, country,
                  center_latitude, center_longitude,
                  last_requested_at, last_scan_requested_at,
                  last_scan_started_at, last_scan_completed_at,
                  last_scan_succeeded_at, scan_lock_until,
                  visible_event_count_7d,
                  last_targeted_filter_signature,
                  last_targeted_requested_at,
                  last_targeted_completed_at,
                  last_error, created_at, updated_at
                )
                values (
                  :market_key, :city, :state, :country,
                  :center_latitude, :center_longitude,
                  :last_requested_at, :last_scan_requested_at,
                  :last_scan_started_at, :last_scan_completed_at,
                  :last_scan_succeeded_at, :scan_lock_until,
                  coalesce(:visible_event_count_7d, 0),
                  :last_targeted_filter_signature,
                  :last_targeted_requested_at,
                  :last_targeted_completed_at,
                  :last_error, now(), now()
                )
                on conflict (market_key) do update
                set city = excluded.city,
                    state = excluded.state,
                    country = excluded.country,
                    center_latitude = coalesce(
                      excluded.center_latitude,
                      public.market_inventory_state.center_latitude
                    ),
                    center_longitude = coalesce(
                      excluded.center_longitude,
                      public.market_inventory_state.center_longitude
                    ),
                    last_requested_at = coalesce(
                      excluded.last_requested_at,
                      public.market_inventory_state.last_requested_at
                    ),
                    last_scan_requested_at = coalesce(
                      excluded.last_scan_requested_at,
                      public.market_inventory_state.last_scan_requested_at
                    ),
                    last_scan_started_at = coalesce(
                      excluded.last_scan_started_at,
                      public.market_inventory_state.last_scan_started_at
                    ),
                    last_scan_completed_at = coalesce(
                      excluded.last_scan_completed_at,
                      public.market_inventory_state.last_scan_completed_at
                    ),
                    last_scan_succeeded_at = coalesce(
                      excluded.last_scan_succeeded_at,
                      public.market_inventory_state.last_scan_succeeded_at
                    ),
                    scan_lock_until = coalesce(
                      excluded.scan_lock_until,
                      public.market_inventory_state.scan_lock_until
                    ),
                    visible_event_count_7d = coalesce(
                      excluded.visible_event_count_7d,
                      public.market_inventory_state.visible_event_count_7d
                    ),
                    last_targeted_filter_signature = case
                      when :last_targeted_filter_signature_set
                        then excluded.last_targeted_filter_signature
                      else public.market_inventory_state.last_targeted_filter_signature
                    end,
                    last_targeted_requested_at = case
                      when :last_targeted_requested_at_set
                        then excluded.last_targeted_requested_at
                      else public.market_inventory_state.last_targeted_requested_at
                    end,
                    last_targeted_completed_at = case
                      when :last_targeted_completed_at_set
                        then excluded.last_targeted_completed_at
                      else public.market_inventory_state.last_targeted_completed_at
                    end,
                    last_error = case
                      when :last_error_set then excluded.last_error
                      else public.market_inventory_state.last_error
                    end,
                    updated_at = now()
                """
            ),
            {
                "market_key": market.key,
                "city": market.city,
                "state": market.state,
                "country": market.country,
                "center_latitude": market.center_latitude,
                "center_longitude": market.center_longitude,
                "last_requested_at": last_requested_at,
                "last_scan_requested_at": last_scan_requested_at,
                "last_scan_started_at": last_scan_started_at,
                "last_scan_completed_at": last_scan_completed_at,
                "last_scan_succeeded_at": last_scan_succeeded_at,
                "scan_lock_until": scan_lock_until,
                "visible_event_count_7d": visible_event_count_7d,
                "last_targeted_filter_signature": None
                if last_targeted_filter_signature is _UNSET
                else last_targeted_filter_signature,
                "last_targeted_requested_at": None
                if last_targeted_requested_at is _UNSET
                else last_targeted_requested_at,
                "last_targeted_completed_at": None
                if last_targeted_completed_at is _UNSET
                else last_targeted_completed_at,
                "last_targeted_filter_signature_set": last_targeted_filter_signature is not _UNSET,
                "last_targeted_requested_at_set": last_targeted_requested_at is not _UNSET,
                "last_targeted_completed_at_set": last_targeted_completed_at is not _UNSET,
                "last_error": None if last_error is _UNSET else last_error,
                "last_error_set": last_error is not _UNSET,
            },
        )
        await self.session.commit()
