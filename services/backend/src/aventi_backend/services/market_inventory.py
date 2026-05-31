from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.jobs import JobQueueRepository, JobRecord, JobType
from aventi_backend.services.market_descriptors import (
    MarketDescriptor,
)
from aventi_backend.services.market_descriptors import (
    build_market_key as build_market_key,
)
from aventi_backend.services.market_descriptors import (
    market_from_payload as market_from_payload,
)
from aventi_backend.services.market_descriptors import (
    optional_str as _optional_str,
)
from aventi_backend.services.market_filters import (
    build_targeted_filter_signature,
)
from aventi_backend.services.market_filters import (
    coerce_utc_datetime as _coerce_utc_datetime,
)
from aventi_backend.services.market_inventory_state import MarketInventoryStateStore
from aventi_backend.services.market_scan_execution import MarketScanExecutionService
from aventi_backend.services.market_scan_planning import MarketScanPlan, MarketScanPlanner

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


def _scan_planner() -> MarketScanPlanner:
    return MarketScanPlanner(
        discovery_angles=DISCOVERY_ANGLES,
        page_budget_by_tier=PAGE_BUDGET_BY_TIER,
        scan_windows=SCAN_WINDOWS,
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
    scheduler_run_id: str | None = None,
    feed_filters: dict[str, Any] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await MarketScanExecutionService(
        session,
        inventory_state=_state_store(session),
    ).execute(
        market=market,
        angle=angle,
        source_name=source_name,
        source_type=source_type,
        source_url=source_url,
        source_data=source_data,
        job_id=job_id,
        scheduler_run_id=scheduler_run_id,
        feed_filters=feed_filters,
        latitude=latitude,
        longitude=longitude,
        extra_meta=extra_meta,
    )


async def count_visible_market_events(
    session: AsyncSession,
    market: MarketDescriptor,
    now: datetime,
) -> int:
    return await _state_store(session).visible_event_count(market, now)


def _state_store(session: AsyncSession) -> MarketInventoryStateStore:
    return MarketInventoryStateStore(
        session,
        active_window=MARKET_ACTIVE_WINDOW,
        heat_warm_window=HEAT_WARM_WINDOW,
        hot_min_users_7d=HEAT_HOT_MIN_USERS_7D,
        eligible_verification_statuses=ELIGIBLE_VERIFICATION_STATUSES,
    )


class MarketWarmupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.state_store = _state_store(session)

    async def touch_market_request(self, market: MarketDescriptor) -> None:
        await self.state_store.touch_market_request(market)

    async def refresh_market_inventory_state(self, market: MarketDescriptor) -> int:
        return await self.state_store.refresh_market_inventory_state(market)

    async def sync_market_inventory_from_event_venues(self) -> dict[str, Any]:
        """Upsert ``market_inventory_state`` for every market implied by the event catalog.

        Events are stored against **venues** (city / state / country). This pass groups
        live-ish occurrences by venue geography and upserts matching ``market_inventory_state``
        rows, then recomputes visible 7-day counts—the same signal the scanner uses.

        Rows are normally created by mobile ``/me/market-seen`` or scan workers; this is an
        admin backfill when catalog data exists but inventory rows were never created.
        """
        return await self.state_store.sync_market_inventory_from_event_venues()

    async def enqueue_admin_short_market_scan(
        self,
        market_key: str,
        *,
        scheduler_run_id: str | None = None,
    ) -> JobRecord:
        """Queue a single short-window ``MARKET_SCAN`` (SerpAPI) for an existing market row."""
        market = await self.state_store.get_market_by_key(market_key)
        if market is None:
            raise ValueError(f"Unknown market_key: {market_key}")
        await self.state_store.upsert_market_state(
            market,
            last_scan_requested_at=datetime.now(tz=UTC),
        )
        return await self._enqueue_scan_plan(
            market,
            _scan_planner().admin_short_scan(market),
            scheduler_run_id=scheduler_run_id,
        )

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
            await self.state_store.upsert_market_state(
                market,
                visible_event_count_7d=visible_count,
            )
        active_discovery_jobs = await self.state_store.has_active_discovery_jobs(market.key)
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
        state = await self.state_store.targeted_mining_state(market.key)
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

        await self.state_store.upsert_market_state(
            market,
            last_targeted_filter_signature=signature,
            last_targeted_requested_at=now,
            last_targeted_completed_at=None,
        )
        await self._enqueue_scan_plan(
            market,
            _scan_planner().targeted_scan(
                filters=filters,
                latitude=latitude,
                longitude=longitude,
                filter_signature=signature,
            ),
        )
        return "targeted_warming", True

    async def mark_targeted_mining_completed(
        self,
        market: MarketDescriptor,
        *,
        filter_signature: str,
    ) -> None:
        await self.state_store.upsert_market_state(
            market,
            last_targeted_filter_signature=filter_signature,
            last_targeted_completed_at=datetime.now(tz=UTC),
        )

    async def enqueue_scheduled_warmups(self, *, limit: int = 50) -> dict[str, int]:
        now = datetime.now(tz=UTC)
        markets = await self.state_store.scheduled_warmup_markets(
            limit=limit,
            target_count=MARKET_WARM_TARGET,
            now=now,
        )
        requested = 0
        triggered = 0
        for market in markets:
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
        await self.state_store.mark_scan_started(market, started_at)
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
                for scan_plan in _scan_planner().warmup_discovery_scans():
                    await self._enqueue_scan_plan(market, scan_plan)
                    discovery_jobs_enqueued += 1

            visible_count = await self.refresh_market_inventory_state(market)
            await self.state_store.mark_scan_completed(market, success=True, error=None)
            return {
                "marketKey": market.key,
                "city": market.city,
                "structuredSourcesRun": len(structured_runs),
                "structuredSourceRuns": structured_runs,
                "discoveryJobsEnqueued": discovery_jobs_enqueued,
                "visibleEventCount7d": visible_count,
            }
        except Exception as exc:  # noqa: BLE001
            await self.state_store.mark_scan_completed(market, success=False, error=str(exc))
            raise

    async def _enqueue_market_warmup_job(
        self,
        market: MarketDescriptor,
        *,
        force_discovery: bool = False,
        ignore_cooldown: bool = False,
        scheduler_run_id: str | None = None,
    ) -> bool:
        now = datetime.now(tz=UTC)
        lock_until = await self.state_store.scan_lock_until(market.key)
        if not ignore_cooldown and isinstance(lock_until, datetime) and lock_until > now:
            return False

        await self.state_store.upsert_market_state(
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
            scheduler_run_id=scheduler_run_id,
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
        scheduler_run_id: str | None = None,
    ) -> JobRecord:
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
        return await JobQueueRepository(self.session).enqueue_job(
            JobType.MARKET_SCAN,
            payload,
            scheduler_run_id=scheduler_run_id,
        )

    async def _enqueue_scan_plan(
        self,
        market: MarketDescriptor,
        scan_plan: MarketScanPlan,
        *,
        scheduler_run_id: str | None = None,
    ) -> JobRecord:
        return await self._enqueue_market_scan_job(
            market,
            angle=scan_plan.angle,
            source_name=scan_plan.source_name,
            source_type=scan_plan.source_type,
            source_url=scan_plan.source_url,
            source_data=scan_plan.source_data,
            extra_payload=scan_plan.extra_payload,
            scheduler_run_id=scheduler_run_id,
        )

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
        return await self.state_store.has_active_discovery_jobs(market_key)

    # ------------------------------------------------------------------
    # Heat-tier + cron scheduling helpers (plan 0008)
    # ------------------------------------------------------------------

    async def list_active_markets(self, *, limit: int = 200) -> list[MarketDescriptor]:
        """Return hot + warm markets eligible for weekly cron scans.

        Cold markets (no user activity in HEAT_WARM_WINDOW) are skipped. Rows
        currently scan-locked are also excluded to avoid clobbering an
        in-flight scan.
        """
        return await self.state_store.list_active_markets(limit=limit)

    async def recompute_all_heat(self) -> dict[str, int]:
        """Refresh ``heat_tier`` + activity counters for every indexed market.

        Attribution comes from ``public.swipe_actions.market_key`` and
        ``public.feed_impressions.market_key`` (both added in migration 0008).
        A single SQL statement updates every row in one round trip.
        """
        return await self.state_store.recompute_all_heat()

    async def mark_user_active(self, market: MarketDescriptor) -> None:
        """Record that a user is currently active in this market.

        Updates ``last_user_active_at`` immediately and nudges ``heat_tier``
        to at least ``warm``. The real tier is reconciled on the next
        ``recompute_all_heat()`` pass by the scheduler.
        """
        await self.state_store.mark_user_active(market)

    async def bootstrap_market_if_new(self, market: MarketDescriptor) -> bool:
        """Seed a ``market_inventory_state`` row for a newly-seen market.

        If the row doesn't exist yet, inserts it with ``heat_tier='warm'`` and
        enqueues a single short-term MARKET_SCAN job so the user sees events on
        first login instead of waiting up to a week for the cron. Idempotent:
        returns ``False`` if the market is already tracked.
        """
        inserted = await self.state_store.bootstrap_market_if_new(market)
        if not inserted:
            return False

        # Fire a one-shot short-term scan so the first user doesn't see an
        # empty feed for a week. Cold markets will be re-armed via cron only.
        await self._enqueue_scan_plan(market, _scan_planner().bootstrap_short_scan(market))
        return True

    async def enqueue_weekly_scans(
        self,
        *,
        limit: int = 200,
        scheduler_run_id: str | None = None,
    ) -> dict[str, int]:
        """Fan out one MARKET_SCAN job per (active market × SCAN_WINDOWS).

        Credit budget per market comes from ``PAGE_BUDGET_BY_TIER[heat_tier]``.
        Called by the weekly EventBridge-triggered scheduler Lambda.
        """
        await self.recompute_all_heat()
        markets = await self.list_active_markets(limit=limit)
        enqueued = 0
        for market in markets:
            for scan_plan in _scan_planner().weekly_scans(market):
                await self._enqueue_scan_plan(
                    market,
                    scan_plan,
                    scheduler_run_id=scheduler_run_id,
                )
                enqueued += 1
        return {"markets": len(markets), "jobs_enqueued": enqueued}

    async def _visible_event_count(self, market: MarketDescriptor, now: datetime) -> int:
        return await self.state_store.visible_event_count(market, now)

    async def _mark_scan_started(self, market: MarketDescriptor, started_at: datetime) -> None:
        await self.state_store.mark_scan_started(market, started_at)

    async def _mark_scan_completed(
        self,
        market: MarketDescriptor,
        *,
        success: bool,
        error: str | None,
    ) -> None:
        await self.state_store.mark_scan_completed(market, success=success, error=error)

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
        await self.state_store.upsert_market_state(
            market,
            last_requested_at=last_requested_at,
            last_scan_requested_at=last_scan_requested_at,
            last_scan_started_at=last_scan_started_at,
            last_scan_completed_at=last_scan_completed_at,
            last_scan_succeeded_at=last_scan_succeeded_at,
            scan_lock_until=scan_lock_until,
            visible_event_count_7d=visible_event_count_7d,
            last_targeted_filter_signature=last_targeted_filter_signature,
            last_targeted_requested_at=last_targeted_requested_at,
            last_targeted_completed_at=last_targeted_completed_at,
            last_error=last_error,
        )
