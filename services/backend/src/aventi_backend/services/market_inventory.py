from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.providers import DiscoveryCandidate, build_market_scan_scraper
from aventi_backend.services.verification import VerificationService

MARKET_ACTIVE_WINDOW = timedelta(days=7)
MARKET_WARM_TARGET = 10
MARKET_SCAN_COOLDOWN = timedelta(minutes=30)
MARKET_WARMUP_COOLDOWN = timedelta(minutes=30)
TARGETED_MINING_COOLDOWN = timedelta(minutes=10)
DISCOVERY_ANGLES = ("Chill", "Energetic", "Romantic", "Intellectual")
ELIGIBLE_VERIFICATION_STATUSES = ("pending", "verified", "suspect")

# Heat-tier thresholds (see plan 0008).
HEAT_HOT_MIN_USERS_7D = 5
HEAT_WARM_WINDOW = timedelta(days=14)
PAGE_BUDGET_BY_TIER: dict[str, int] = {"hot": 3, "warm": 1, "bootstrap": 1}

# Weekly cron windows: short-term + long-term.
SCAN_WINDOWS: tuple[dict[str, Any], ...] = (
    {"label": "short_term", "angle": "events", "startDays": 0, "durationDays": 7},
    {"label": "long_term", "angle": "events", "startDays": 14, "durationDays": 45},
)

_UNSET = object()


@dataclass(slots=True)
class MarketDescriptor:
    key: str
    city: str
    state: str | None
    country: str
    center_latitude: float | None = None
    center_longitude: float | None = None
    heat_tier: str = "cold"


def build_market_key(city: str, state: str | None = None, country: str | None = None) -> str:
    normalized_city = city.strip().lower()
    normalized_state = (state or "").strip().lower()
    normalized_country = (country or "US").strip().lower()
    return f"{normalized_city}|{normalized_state}|{normalized_country}"


def build_market_descriptor(
    *,
    city: str | None,
    state: str | None = None,
    country: str | None = None,
    center_latitude: float | None = None,
    center_longitude: float | None = None,
) -> MarketDescriptor | None:
    if not city or not city.strip():
        return None
    normalized_city = city.strip()
    normalized_state = state.strip() if state and state.strip() else None
    normalized_country = country.strip().upper() if country and country.strip() else "US"
    return MarketDescriptor(
        key=build_market_key(normalized_city, normalized_state, normalized_country),
        city=normalized_city,
        state=normalized_state,
        country=normalized_country,
        center_latitude=center_latitude,
        center_longitude=center_longitude,
    )


def market_from_payload(payload: dict[str, Any]) -> MarketDescriptor | None:
    market_key = payload.get("marketKey")
    market_city = payload.get("marketCity") or payload.get("city")
    if not isinstance(market_city, str) or not market_city.strip():
        return None
    if not isinstance(market_key, str) or not market_key.strip():
        return build_market_descriptor(
            city=market_city,
            state=payload.get("marketState"),
            country=payload.get("marketCountry"),
            center_latitude=_coerce_float(payload.get("centerLatitude")),
            center_longitude=_coerce_float(payload.get("centerLongitude")),
        )
    return MarketDescriptor(
        key=market_key,
        city=market_city.strip(),
        state=_optional_str(payload.get("marketState")),
        country=_optional_str(payload.get("marketCountry")) or "US",
        center_latitude=_coerce_float(payload.get("centerLatitude")),
        center_longitude=_coerce_float(payload.get("centerLongitude")),
    )


async def execute_market_scan(
    session: AsyncSession,
    *,
    market: MarketDescriptor,
    angle: str,
    source_name: str,
    source_type: str | None = None,
    source_url: str | None = None,
    source_data: Any = None,
    job_id: str | None = None,
    feed_filters: dict[str, Any] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sourceName": source_name,
        "city": market.city,
    }
    if source_type:
        payload["sourceType"] = source_type
    if source_url:
        payload["sourceUrl"] = source_url
    if source_data is not None:
        payload["sourceData"] = source_data

    scraper = build_market_scan_scraper(payload)
    candidates = await scraper.discover(city=market.city, angle=angle)
    # Scrapers that instrument themselves (SerpApiEventScraper) stash pagination
    # + timing stats on last_meta; others leave it empty.
    scraper_meta: dict[str, Any] = dict(getattr(scraper, "last_meta", {}) or {})
    if feed_filters:
        candidates = [
            candidate
            for candidate in candidates
            if _candidate_matches_filters(
                candidate,
                feed_filters=feed_filters,
                latitude=latitude,
                longitude=longitude,
            )
        ]

    # Build combined scan_meta passed through to ingest_runs.metadata. Includes
    # scraper stats (SerpAPI pagination) and caller-supplied extras (scan_type,
    # heat_tier, job_id).
    scan_meta: dict[str, Any] = {
        "angle": angle,
        "jobId": job_id,
        "marketKey": market.key,
        "heatTier": market.heat_tier,
    }
    scan_meta.update(scraper_meta)
    if extra_meta:
        scan_meta.update(extra_meta)

    manual_events = _build_manual_events(
        candidates=candidates,
        city=market.city,
        state=market.state,
        country=market.country,
        angle=angle,
        source_name=source_name,
        job_id=job_id,
    )
    if not manual_events:
        await MarketWarmupService(session).refresh_market_inventory_state(market)
        return {
            "source": source_name,
            "city": market.city,
            "ingest": {
                "ok": True,
                "sourceId": None,
                "ingestRunId": None,
                "source": source_name,
                "city": market.city,
                "discovered": 0,
                "insertedEvents": 0,
                "updatedEvents": 0,
                "insertedOccurrences": 0,
                "eventIds": [],
            },
            "scanMeta": scan_meta,
            "verificationJobsEnqueued": 0,
        }

    ingest_summary = await ManualIngestService(session).ingest_manual(
        source_name=source_name,
        city=market.city,
        events=manual_events,
        scan_meta=scan_meta,
    )

    settings = get_settings()
    verification_enqueued = 0
    if settings.enable_verification and ingest_summary.event_ids:
        verification_enqueued = await VerificationService(session).enqueue_verification_jobs(
            limit=len(ingest_summary.event_ids),
            event_ids=ingest_summary.event_ids,
        )
    await MarketWarmupService(session).refresh_market_inventory_state(market)
    return {
        "source": source_name,
        "city": market.city,
        "ingest": ingest_summary.as_dict(),
        "scanMeta": scan_meta,
        "verificationJobsEnqueued": verification_enqueued,
    }


async def count_visible_market_events(
    session: AsyncSession,
    market: MarketDescriptor,
    now: datetime,
) -> int:
    result = await session.scalar(
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
            "end_ts": now + MARKET_ACTIVE_WINDOW,
            "eligible_statuses": list(ELIGIBLE_VERIFICATION_STATUSES),
            "city": market.city.lower(),
            "state": (market.state or "").lower(),
            "country": market.country.lower(),
        },
    )
    return int(result or 0)


class MarketWarmupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def touch_market_request(self, market: MarketDescriptor) -> None:
        await self._upsert_market_state(
            market,
            last_requested_at=datetime.now(tz=UTC),
        )

    async def refresh_market_inventory_state(self, market: MarketDescriptor) -> int:
        now = datetime.now(tz=UTC)
        visible_count = await self._visible_event_count(market, now)
        await self._upsert_market_state(
            market,
            visible_event_count_7d=visible_count,
        )
        return visible_count

    async def request_warmup(
        self,
        market: MarketDescriptor,
        *,
        force_refresh: bool = False,
        visible_count: int | None = None,
    ) -> tuple[str, str, bool]:
        await self.touch_market_request(market)
        if visible_count is None:
            visible_count = await self.refresh_market_inventory_state(market)
        else:
            await self._upsert_market_state(
                market,
                visible_event_count_7d=visible_count,
            )
        active_discovery_jobs = await self._has_active_discovery_jobs(market.key)
        if visible_count >= MARKET_WARM_TARGET and not force_refresh:
            return market.key, "ready", False
        if force_refresh:
            triggered = await self._enqueue_market_warmup_job(
                market,
                force_discovery=True,
                ignore_cooldown=True,
            )
            return market.key, "warming", triggered
        if active_discovery_jobs:
            return market.key, "warming", False
        triggered = await self._enqueue_market_warmup_job(market)
        return market.key, "warming", triggered

    async def request_targeted_mining(
        self,
        market: MarketDescriptor,
        *,
        filters: dict[str, Any],
        latitude: float,
        longitude: float,
        force_refresh: bool = False,
    ) -> tuple[str, bool]:
        signature = build_targeted_filter_signature(filters, latitude=latitude, longitude=longitude)
        now = datetime.now(tz=UTC)
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
            {"market_key": market.key},
        )
        state = row.mappings().first()
        requested_at = _coerce_utc_datetime(state["last_targeted_requested_at"]) if state else None
        completed_at = _coerce_utc_datetime(state["last_targeted_completed_at"]) if state else None
        same_signature = bool(state and state["last_targeted_filter_signature"] == signature)
        in_progress = (
            same_signature
            and requested_at is not None
            and (completed_at is None or requested_at > completed_at)
        )
        recently_completed = (
            same_signature
            and completed_at is not None
            and completed_at >= now - TARGETED_MINING_COOLDOWN
        )

        if in_progress and not force_refresh:
            return "targeted_warming", False
        if recently_completed and not force_refresh:
            return "no_matches", False

        await self._upsert_market_state(
            market,
            last_targeted_filter_signature=signature,
            last_targeted_requested_at=now,
            last_targeted_completed_at=None,
        )
        await self._enqueue_market_scan_job(
            market,
            angle="targeted discovery",
            source_name="serpapi-targeted",
            source_type="serpapi",
            source_data={
                "mode": "targeted",
                "filters": filters,
                "latitude": latitude,
                "longitude": longitude,
                "filterSignature": signature,
            },
            extra_payload={
                "filters": filters,
                "latitude": latitude,
                "longitude": longitude,
                "filterSignature": signature,
            },
        )
        return "targeted_warming", True

    async def mark_targeted_mining_completed(
        self,
        market: MarketDescriptor,
        *,
        filter_signature: str,
    ) -> None:
        await self._upsert_market_state(
            market,
            last_targeted_filter_signature=filter_signature,
            last_targeted_completed_at=datetime.now(tz=UTC),
        )

    async def enqueue_scheduled_warmups(self, *, limit: int = 50) -> dict[str, int]:
        now = datetime.now(tz=UTC)
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
                "active_cutoff": now - MARKET_ACTIVE_WINDOW,
                "target_count": MARKET_WARM_TARGET,
                "now_ts": now,
                "limit_rows": limit,
            },
        )
        requested = 0
        triggered = 0
        for row in result.mappings().all():
            market = MarketDescriptor(
                key=str(row["market_key"]),
                city=str(row["city"]),
                state=_optional_str(row["state"]),
                country=_optional_str(row["country"]) or "US",
                center_latitude=_coerce_float(row["center_latitude"]),
                center_longitude=_coerce_float(row["center_longitude"]),
            )
            requested += 1
            if await self._enqueue_market_warmup_job(market):
                triggered += 1
        return {"requested": requested, "triggered": triggered}

    async def run_market_warmup(
        self,
        market: MarketDescriptor,
        *,
        job_id: str | None = None,
        force_discovery: bool = False,
    ) -> dict[str, Any]:
        started_at = datetime.now(tz=UTC)
        await self._mark_scan_started(market, started_at)
        structured_runs: list[dict[str, Any]] = []
        try:
            source_rows = await self._structured_source_rows(market.key)
            for source in source_rows:
                config = dict(source["config"] or {})
                run = await execute_market_scan(
                    self.session,
                    market=market,
                    angle=str(config.get("angle") or "market warmup"),
                    source_name=str(source["name"]),
                    source_type=str(source["source_type"]),
                    source_url=_optional_str(source["base_url"]),
                    source_data=config.get("sourceData"),
                    job_id=job_id,
                )
                structured_runs.append(run)

            visible_count = await self.refresh_market_inventory_state(market)
            discovery_jobs_enqueued = 0
            if force_discovery or visible_count < MARKET_WARM_TARGET:
                for angle in DISCOVERY_ANGLES:
                    if await self._enqueue_market_scan_job(
                        market,
                        angle=angle,
                        source_name="serpapi",
                        source_type="serpapi",
                    ):
                        discovery_jobs_enqueued += 1

            visible_count = await self.refresh_market_inventory_state(market)
            await self._mark_scan_completed(market, success=True, error=None)
            return {
                "marketKey": market.key,
                "city": market.city,
                "structuredSourcesRun": len(structured_runs),
                "structuredSourceRuns": structured_runs,
                "discoveryJobsEnqueued": discovery_jobs_enqueued,
                "visibleEventCount7d": visible_count,
            }
        except Exception as exc:  # noqa: BLE001
            await self._mark_scan_completed(market, success=False, error=str(exc))
            raise

    async def _enqueue_market_warmup_job(
        self,
        market: MarketDescriptor,
        *,
        force_discovery: bool = False,
        ignore_cooldown: bool = False,
    ) -> bool:
        now = datetime.now(tz=UTC)
        lock_until = await self.session.scalar(
            text(
                """
                select scan_lock_until
                from public.market_inventory_state
                where market_key = :market_key
                """
            ),
            {"market_key": market.key},
        )
        if lock_until and getattr(lock_until, "tzinfo", None) is None:
            lock_until = lock_until.replace(tzinfo=UTC)

        if not ignore_cooldown and isinstance(lock_until, datetime) and lock_until > now:
            return False

        await self._upsert_market_state(
            market,
            last_scan_requested_at=now,
            scan_lock_until=now + MARKET_WARMUP_COOLDOWN,
            last_error=None,
        )
        await JobQueueRepository(self.session).enqueue_job(
            JobType.MARKET_WARMUP,
            {
                "marketKey": market.key,
                "marketCity": market.city,
                "marketState": market.state,
                "marketCountry": market.country,
                "centerLatitude": market.center_latitude,
                "centerLongitude": market.center_longitude,
                "forceDiscovery": force_discovery,
            },
        )
        return True

    async def _enqueue_market_scan_job(
        self,
        market: MarketDescriptor,
        *,
        angle: str,
        source_name: str,
        source_type: str | None = None,
        source_url: str | None = None,
        source_data: Any = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "marketKey": market.key,
            "marketCity": market.city,
            "marketState": market.state,
            "marketCountry": market.country,
            "centerLatitude": market.center_latitude,
            "centerLongitude": market.center_longitude,
            "city": market.city,
            "angle": angle,
            "sourceName": source_name,
        }
        if source_type:
            payload["sourceType"] = source_type
        if source_url:
            payload["sourceUrl"] = source_url
        if source_data is not None:
            payload["sourceData"] = source_data
        if extra_payload:
            payload.update(extra_payload)
        await JobQueueRepository(self.session).enqueue_job(JobType.MARKET_SCAN, payload)
        return True

    async def _structured_source_rows(self, market_key: str) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                select
                  src.id::text as id,
                  src.name,
                  src.source_type,
                  src.base_url,
                  src.config,
                  mis.priority
                from public.market_ingest_sources mis
                join public.ingest_sources src on src.id = mis.source_id
                where mis.market_key = :market_key
                  and mis.enabled = true
                  and src.enabled = true
                  and src.source_type not in ('gemini', 'ai')
                order by mis.priority asc, src.name asc
                """
            ),
            {"market_key": market_key},
        )
        return [dict(row) for row in result.mappings().all()]

    async def _has_active_discovery_jobs(self, market_key: str) -> bool:
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
        return lock_until is not None and lock_until > datetime.now(tz=UTC)

    # ------------------------------------------------------------------
    # Heat-tier + cron scheduling helpers (plan 0008)
    # ------------------------------------------------------------------

    async def list_active_markets(self, *, limit: int = 200) -> list[MarketDescriptor]:
        """Return hot + warm markets eligible for weekly cron scans.

        Cold markets (no user activity in HEAT_WARM_WINDOW) are skipped. Rows
        currently scan-locked are also excluded to avoid clobbering an
        in-flight scan.
        """
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
        markets: list[MarketDescriptor] = []
        for row in result.mappings().all():
            markets.append(
                MarketDescriptor(
                    key=str(row["market_key"]),
                    city=str(row["city"]),
                    state=_optional_str(row["state"]),
                    country=_optional_str(row["country"]) or "US",
                    center_latitude=_coerce_float(row["center_latitude"]),
                    center_longitude=_coerce_float(row["center_longitude"]),
                    heat_tier=str(row["heat_tier"] or "cold"),
                )
            )
        return markets

    async def recompute_all_heat(self) -> dict[str, int]:
        """Refresh ``heat_tier`` + activity counters for every indexed market.

        Attribution comes from ``public.swipe_actions.market_key`` and
        ``public.feed_impressions.market_key`` (both added in migration 0008).
        A single SQL statement updates every row in one round trip.
        """
        result = await self.session.execute(
            text(
                """
                with activity as (
                  select market_key,
                         count(distinct user_id) filter (where ts >= now() - interval '7 days')  as u7,
                         count(distinct user_id) filter (where ts >= now() - interval '14 days') as u14,
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
            {"hot_min": HEAT_HOT_MIN_USERS_7D},
        )
        rows = result.mappings().all()
        # Also demote markets with no recorded activity at all to cold — the
        # join above only touches markets that have at least one impression.
        await self.session.execute(
            text(
                """
                update public.market_inventory_state
                set heat_tier = 'cold',
                    active_user_count_7d = 0,
                    active_user_count_14d = 0,
                    updated_at = now()
                where (last_user_active_at is null
                       or last_user_active_at < now() - interval '14 days')
                  and heat_tier <> 'cold'
                """
            )
        )
        await self.session.commit()
        tiers = [str(r.get("heat_tier") or "cold") for r in rows]
        return {
            "updated": len(tiers),
            "hot": sum(1 for t in tiers if t == "hot"),
            "warm": sum(1 for t in tiers if t == "warm"),
            "cold": sum(1 for t in tiers if t == "cold"),
        }

    async def mark_user_active(self, market: MarketDescriptor) -> None:
        """Record that a user is currently active in this market.

        Updates ``last_user_active_at`` immediately and nudges ``heat_tier``
        to at least ``warm``. The real tier is reconciled on the next
        ``recompute_all_heat()`` pass by the scheduler.
        """
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
        """Seed a ``market_inventory_state`` row for a newly-seen market.

        If the row doesn't exist yet, inserts it with ``heat_tier='warm'`` and
        enqueues a single short-term MARKET_SCAN job so the user sees events on
        first login instead of waiting up to a week for the cron. Idempotent:
        returns ``False`` if the market is already tracked.
        """
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
        if result is None:
            return False

        await self.session.commit()

        # Fire a one-shot short-term scan so the first user doesn't see an
        # empty feed for a week. Cold markets will be re-armed via cron only.
        short_window = SCAN_WINDOWS[0]
        await self._enqueue_market_scan_job(
            market,
            angle=str(short_window["angle"]),
            source_name=f"bootstrap-short:{market.city.lower()}",
            source_type="serpapi",
            source_data={"dateWindow": dict(short_window), "pages": PAGE_BUDGET_BY_TIER["bootstrap"]},
            extra_payload={"scanType": "bootstrap", "heatTier": "bootstrap"},
        )
        return True

    async def enqueue_weekly_scans(self, *, limit: int = 200) -> dict[str, int]:
        """Fan out one MARKET_SCAN job per (active market × SCAN_WINDOWS).

        Credit budget per market comes from ``PAGE_BUDGET_BY_TIER[heat_tier]``.
        Called by the weekly EventBridge-triggered scheduler Lambda.
        """
        await self.recompute_all_heat()
        markets = await self.list_active_markets(limit=limit)
        enqueued = 0
        for market in markets:
            pages = PAGE_BUDGET_BY_TIER.get(market.heat_tier, 1)
            for window in SCAN_WINDOWS:
                source_data: dict[str, Any] = {
                    "dateWindow": dict(window),
                    "pages": pages,
                }
                await self._enqueue_market_scan_job(
                    market,
                    angle=str(window["angle"]),
                    source_name=f"weekly-{window['label']}:{market.city.lower()}",
                    source_type="serpapi",
                    source_data=source_data,
                    extra_payload={
                        "scanType": window["label"],
                        "heatTier": market.heat_tier,
                    },
                )
                enqueued += 1
        return {"markets": len(markets), "jobs_enqueued": enqueued}

    async def _visible_event_count(self, market: MarketDescriptor, now: datetime) -> int:
        return await count_visible_market_events(self.session, market, now)

    async def _mark_scan_started(self, market: MarketDescriptor, started_at: datetime) -> None:
        await self._upsert_market_state(
            market,
            last_scan_started_at=started_at,
            last_error=None,
        )

    async def _mark_scan_completed(
        self,
        market: MarketDescriptor,
        *,
        success: bool,
        error: str | None,
    ) -> None:
        now = datetime.now(tz=UTC)
        await self._upsert_market_state(
            market,
            last_scan_completed_at=now,
            last_scan_succeeded_at=now if success else None,
            last_error=error,
        )

    async def _upsert_market_state(
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
                  market_key,
                  city,
                  state,
                  country,
                  center_latitude,
                  center_longitude,
                  last_requested_at,
                  last_scan_requested_at,
                  last_scan_started_at,
                  last_scan_completed_at,
                  last_scan_succeeded_at,
                  scan_lock_until,
                  visible_event_count_7d,
                  last_targeted_filter_signature,
                  last_targeted_requested_at,
                  last_targeted_completed_at,
                  last_error,
                  created_at,
                  updated_at
                )
                values (
                  :market_key,
                  :city,
                  :state,
                  :country,
                  :center_latitude,
                  :center_longitude,
                  :last_requested_at,
                  :last_scan_requested_at,
                  :last_scan_started_at,
                  :last_scan_completed_at,
                  :last_scan_succeeded_at,
                  :scan_lock_until,
                  coalesce(:visible_event_count_7d, 0),
                  :last_targeted_filter_signature,
                  :last_targeted_requested_at,
                  :last_targeted_completed_at,
                  :last_error,
                  now(),
                  now()
                )
                on conflict (market_key) do update
                set city = excluded.city,
                    state = excluded.state,
                    country = excluded.country,
                    center_latitude = coalesce(excluded.center_latitude, public.market_inventory_state.center_latitude),
                    center_longitude = coalesce(excluded.center_longitude, public.market_inventory_state.center_longitude),
                    last_requested_at = coalesce(excluded.last_requested_at, public.market_inventory_state.last_requested_at),
                    last_scan_requested_at = coalesce(excluded.last_scan_requested_at, public.market_inventory_state.last_scan_requested_at),
                    last_scan_started_at = coalesce(excluded.last_scan_started_at, public.market_inventory_state.last_scan_started_at),
                    last_scan_completed_at = coalesce(excluded.last_scan_completed_at, public.market_inventory_state.last_scan_completed_at),
                    last_scan_succeeded_at = coalesce(excluded.last_scan_succeeded_at, public.market_inventory_state.last_scan_succeeded_at),
                    scan_lock_until = coalesce(excluded.scan_lock_until, public.market_inventory_state.scan_lock_until),
                    visible_event_count_7d = coalesce(excluded.visible_event_count_7d, public.market_inventory_state.visible_event_count_7d),
                    last_targeted_filter_signature = case
                      when :last_targeted_filter_signature_set then excluded.last_targeted_filter_signature
                      else public.market_inventory_state.last_targeted_filter_signature
                    end,
                    last_targeted_requested_at = case
                      when :last_targeted_requested_at_set then excluded.last_targeted_requested_at
                      else public.market_inventory_state.last_targeted_requested_at
                    end,
                    last_targeted_completed_at = case
                      when :last_targeted_completed_at_set then excluded.last_targeted_completed_at
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


def _build_manual_events(
    *,
    candidates: list[DiscoveryCandidate],
    city: str,
    state: str | None = None,
    country: str = "US",
    angle: str,
    source_name: str,
    job_id: str | None,
) -> list[dict[str, Any]]:
    base_time = datetime.now(tz=UTC) + timedelta(hours=4)
    manual_events: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        starts_at = candidate.starts_at or (base_time + timedelta(hours=index * 2))
        ends_at = (
            candidate.ends_at
            or (candidate.starts_at + timedelta(hours=3) if candidate.starts_at else None)
            or (base_time + timedelta(hours=index * 2 + 3))
        )

        # Build ticket_offers list for downstream storage
        ticket_offers_payload = [
            {
                "url": to.url,
                "provider": to.provider,
                "priceLabel": to.price_label,
                "isFree": to.is_free,
            }
            for to in (candidate.ticket_offers or [])
        ]

        # Build extra occurrences for recurring events
        extra_occurrences = [
            {
                "startsAt": occ.starts_at.isoformat(),
                "endsAt": occ.ends_at.isoformat() if occ.ends_at else None,
                "timezone": occ.timezone or candidate.timezone or "UTC",
            }
            for occ in (candidate.occurrences or [])
            if occ.starts_at
        ]

        manual_events.append(
            {
                "title": candidate.title,
                "description": candidate.description or f"Discovered by MARKET_SCAN worker ({angle})",
                "category": _normalize_category(candidate.category),
                "bookingUrl": candidate.booking_url,
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "timezone": candidate.timezone or "UTC",
                "city": candidate.city or city,
                "venueName": candidate.venue_name or f"{city} Spotlight",
                "venueAddress": candidate.venue_address,
                "state": candidate.venue_state or state,
                "country": country,
                "venueLatitude": candidate.venue_latitude,
                "venueLongitude": candidate.venue_longitude,
                "venueRating": candidate.venue_rating,
                "venueReviewCount": candidate.venue_review_count,
                "imageUrl": candidate.image_url,
                "priceLabel": candidate.price_label,
                "isFree": candidate.is_free if candidate.is_free is not None else False,
                "vibes": candidate.vibes or ["social"],
                "tags": candidate.tags or [angle.replace(" ", "-")],
                "ticketOffers": ticket_offers_payload,
                "extraOccurrences": extra_occurrences,
                "metadata": {
                    **(candidate.metadata or {}),
                    "source": candidate.source,
                    "sourceName": source_name,
                    "discoveredByJobId": job_id,
                },
            }
        )
    return manual_events


def _normalize_category(value: str | None) -> str:
    if not value:
        return "experiences"
    normalized = value.strip().lower()
    if normalized in {"nightlife", "dining", "concerts", "wellness", "experiences"}:
        return normalized
    if "music" in normalized or "concert" in normalized or "show" in normalized:
        return "concerts"
    if "food" in normalized or "drink" in normalized or "dining" in normalized:
        return "dining"
    if "well" in normalized or "fitness" in normalized or "yoga" in normalized:
        return "wellness"
    if "night" in normalized or "club" in normalized or "bar" in normalized:
        return "nightlife"
    return "experiences"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_targeted_filter_signature(
    filters: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
) -> str:
    payload = {
        "categories": sorted(str(value) for value in (filters.get("categories") or [])),
        "date": filters.get("date"),
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "price": filters.get("price"),
        "radiusMiles": filters.get("radiusMiles"),
        "timeOfDay": filters.get("timeOfDay"),
        "vibes": sorted(str(value) for value in (filters.get("vibes") or [])),
    }
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _coerce_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _date_window_for_filters(date_filter: str, now: datetime) -> tuple[datetime, datetime]:
    if date_filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    if date_filter == "tomorrow":
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow, tomorrow + timedelta(days=1)
    if date_filter == "week":
        return now, now + timedelta(days=7)

    days_until_sat = (5 - now.weekday()) % 7
    saturday = (now + timedelta(days=days_until_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
    if saturday < now:
        saturday += timedelta(days=7)
    return saturday, saturday + timedelta(days=2)


def _time_of_day_matches(starts_at: datetime, bucket: str | None) -> bool:
    if not bucket:
        return True
    hour = starts_at.astimezone(UTC).hour
    if bucket == "morning":
        return 5 <= hour < 12
    if bucket == "afternoon":
        return 12 <= hour < 17
    if bucket == "evening":
        return 17 <= hour < 22
    if bucket == "night":
        return hour >= 22 or hour < 5
    return True


def _haversine_miles(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> float | None:
    if lat2 is None or lon2 is None:
        return None
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


def _candidate_matches_filters(
    candidate: DiscoveryCandidate,
    *,
    feed_filters: dict[str, Any],
    latitude: float | None,
    longitude: float | None,
) -> bool:
    now = datetime.now(tz=UTC)
    date_filter = str(feed_filters.get("date") or "week")
    start_ts, end_ts = _date_window_for_filters(date_filter, now)
    starts_at = candidate.starts_at
    if starts_at is None or starts_at < start_ts or starts_at >= end_ts:
        return False

    if not _time_of_day_matches(starts_at, _optional_str(feed_filters.get("timeOfDay"))):
        return False

    price = _optional_str(feed_filters.get("price"))
    if price == "free" and not candidate.is_free:
        return False
    if price == "paid" and candidate.is_free:
        return False

    radius_miles = _coerce_float(feed_filters.get("radiusMiles"))
    if radius_miles is not None and latitude is not None and longitude is not None:
        miles = _haversine_miles(latitude, longitude, candidate.venue_latitude, candidate.venue_longitude)
        if miles is None or miles > radius_miles:
            return False

    categories = [str(value).strip().lower() for value in (feed_filters.get("categories") or []) if str(value).strip()]
    candidate_category = _normalize_category(candidate.category)
    if categories and candidate_category not in categories:
        return False

    selected_vibes = {
        str(value).strip().lower()
        for value in (feed_filters.get("vibes") or [])
        if str(value).strip()
    }
    candidate_vibes = {value.strip().lower() for value in candidate.vibes if value.strip()}
    candidate_tags = {value.strip().lower() for value in candidate.tags if value.strip()}
    if selected_vibes and not selected_vibes.intersection(candidate_vibes.union(candidate_tags)):
        return False

    return True
