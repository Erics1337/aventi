from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.providers import DiscoveryCandidate, build_city_scan_scraper
from aventi_backend.services.verification import VerificationService

MARKET_ACTIVE_WINDOW = timedelta(days=7)
MARKET_WARM_TARGET = 20
CITY_SCAN_COOLDOWN = timedelta(minutes=30)
MARKET_WARMUP_COOLDOWN = timedelta(minutes=30)
DISCOVERY_ANGLES = ("Trending", "Hidden Gems", "Weekend Vibes")
ELIGIBLE_VERIFICATION_STATUSES = ("pending", "verified", "suspect")
_UNSET = object()


@dataclass(slots=True)
class MarketDescriptor:
    key: str
    city: str
    state: str | None
    country: str
    center_latitude: float | None = None
    center_longitude: float | None = None


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


async def execute_city_scan(
    session: AsyncSession,
    *,
    market: MarketDescriptor,
    angle: str,
    source_name: str,
    source_type: str | None = None,
    source_url: str | None = None,
    source_data: Any = None,
    job_id: str | None = None,
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

    scraper = build_city_scan_scraper(payload)
    candidates = await scraper.discover(city=market.city, angle=angle)
    manual_events = _build_manual_events(
        candidates=candidates,
        city=market.city,
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
            "verificationJobsEnqueued": 0,
        }

    ingest_summary = await ManualIngestService(session).ingest_manual(
        source_name=source_name,
        city=market.city,
        events=manual_events,
    )
    verification_enqueued = await VerificationService(session).enqueue_verification_jobs(
        limit=len(ingest_summary.event_ids),
        event_ids=ingest_summary.event_ids,
    )
    await MarketWarmupService(session).refresh_market_inventory_state(market)
    return {
        "source": source_name,
        "city": market.city,
        "ingest": ingest_summary.as_dict(),
        "verificationJobsEnqueued": verification_enqueued,
    }


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

    async def request_warmup(self, market: MarketDescriptor) -> tuple[str, str, bool]:
        await self.touch_market_request(market)
        visible_count = await self.refresh_market_inventory_state(market)
        if visible_count >= MARKET_WARM_TARGET:
            return market.key, "ready", False
        triggered = await self._enqueue_market_warmup_job(market)
        return market.key, "warming", triggered

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

    async def run_market_warmup(self, market: MarketDescriptor, *, job_id: str | None = None) -> dict[str, Any]:
        started_at = datetime.now(tz=UTC)
        await self._mark_scan_started(market, started_at)
        structured_runs: list[dict[str, Any]] = []
        try:
            source_rows = await self._structured_source_rows(market.key)
            for source in source_rows:
                config = dict(source["config"] or {})
                run = await execute_city_scan(
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
            gemini_jobs_enqueued = 0
            if visible_count < MARKET_WARM_TARGET:
                for angle in DISCOVERY_ANGLES:
                    if await self._enqueue_city_scan_job(
                        market,
                        angle=angle,
                        source_name="gemini",
                        source_type="gemini",
                    ):
                        gemini_jobs_enqueued += 1

            visible_count = await self.refresh_market_inventory_state(market)
            await self._mark_scan_completed(market, success=True, error=None)
            return {
                "marketKey": market.key,
                "city": market.city,
                "structuredSourcesRun": len(structured_runs),
                "structuredSourceRuns": structured_runs,
                "geminiJobsEnqueued": gemini_jobs_enqueued,
                "visibleEventCount7d": visible_count,
            }
        except Exception as exc:  # noqa: BLE001
            await self._mark_scan_completed(market, success=False, error=str(exc))
            raise

    async def _enqueue_market_warmup_job(self, market: MarketDescriptor) -> bool:
        now = datetime.now(tz=UTC)
        existing = await self.session.scalar(
            text(
                """
                select count(*)
                from public.job_queue
                where job_type = 'MARKET_WARMUP'
                  and status in ('queued', 'running')
                  and payload ->> 'marketKey' = :market_key
                """
            ),
            {"market_key": market.key},
        )
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
        if int(existing or 0) > 0:
            return False
        if isinstance(lock_until, datetime) and lock_until > now:
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
            },
        )
        return True

    async def _enqueue_city_scan_job(
        self,
        market: MarketDescriptor,
        *,
        angle: str,
        source_name: str,
        source_type: str | None = None,
        source_url: str | None = None,
        source_data: Any = None,
    ) -> bool:
        now = datetime.now(tz=UTC)
        recent = await self.session.scalar(
            text(
                """
                select count(*)
                from public.job_queue
                where job_type = 'CITY_SCAN'
                  and created_at >= :created_cutoff
                  and payload ->> 'marketKey' = :market_key
                  and payload ->> 'angle' = :angle
                  and payload ->> 'sourceName' = :source_name
                """
            ),
            {
                "created_cutoff": now - CITY_SCAN_COOLDOWN,
                "market_key": market.key,
                "angle": angle,
                "source_name": source_name,
            },
        )
        if int(recent or 0) > 0:
            return False

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
        await JobQueueRepository(self.session).enqueue_job(JobType.CITY_SCAN, payload)
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

    async def _visible_event_count(self, market: MarketDescriptor, now: datetime) -> int:
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
                  and lower(coalesce(v.state, '')) = :state
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
                "last_error": None if last_error is _UNSET else last_error,
                "last_error_set": last_error is not _UNSET,
            },
        )
        await self.session.commit()


def _build_manual_events(
    *,
    candidates: list[DiscoveryCandidate],
    city: str,
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
        manual_events.append(
            {
                "title": candidate.title,
                "description": candidate.description or f"Discovered by CITY_SCAN worker ({angle})",
                "category": _normalize_category(candidate.category),
                "bookingUrl": candidate.booking_url,
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "city": candidate.city or city,
                "venueName": candidate.venue_name or f"{city} Spotlight",
                "venueAddress": candidate.venue_address,
                "state": candidate.venue_state,
                "venueLatitude": candidate.venue_latitude,
                "venueLongitude": candidate.venue_longitude,
                "imageUrl": candidate.image_url,
                "priceLabel": candidate.price_label,
                "isFree": candidate.is_free if candidate.is_free is not None else False,
                "vibes": candidate.vibes or ["social"],
                "tags": candidate.tags or [angle.replace(" ", "-")],
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
