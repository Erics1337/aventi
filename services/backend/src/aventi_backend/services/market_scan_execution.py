from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.market_descriptors import MarketDescriptor
from aventi_backend.services.market_filters import (
    candidate_matches_filters,
    normalize_category,
)
from aventi_backend.services.market_inventory_state import MarketInventoryStateStore
from aventi_backend.services.providers import (
    DiscoveryCandidate,
    ProviderConfigurationError,
    SearchGroundedScraper,
    build_market_scan_scraper,
    provider_config_from_settings,
)
from aventi_backend.services.verification import VerificationService


class IngestSummary(Protocol):
    event_ids: list[str]

    def as_dict(self) -> dict[str, Any]: ...


class ManualIngest(Protocol):
    async def ingest_manual(
        self,
        source_name: str,
        city: str,
        events: list[dict[str, Any]],
        scan_meta: dict[str, Any] | None = None,
        job_id: str | None = None,
        scheduler_run_id: str | None = None,
    ) -> IngestSummary: ...


class VerificationEnqueuer(Protocol):
    async def enqueue_verification_jobs(
        self,
        limit: int = 20,
        *,
        event_ids: list[str] | None = None,
        scheduler_run_id: str | None = None,
    ) -> int: ...


ScraperFactory = Callable[[dict[str, Any], Any], SearchGroundedScraper]
IngestFactory = Callable[[AsyncSession], ManualIngest]
VerificationFactory = Callable[[AsyncSession], VerificationEnqueuer]
SettingsProvider = Callable[[], Any]


class MarketScanExecutionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        inventory_state: MarketInventoryStateStore,
        settings_provider: SettingsProvider | None = None,
        scraper_factory: ScraperFactory | None = None,
        ingest_factory: IngestFactory | None = None,
        verification_factory: VerificationFactory | None = None,
    ) -> None:
        self.session = session
        self.inventory_state = inventory_state
        self.settings_provider = settings_provider or get_settings
        self.scraper_factory = scraper_factory or self._default_scraper_factory
        self.ingest_factory = ingest_factory or ManualIngestService
        self.verification_factory = verification_factory or VerificationService

    async def execute(
        self,
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

        settings = self.settings_provider()
        scraper = self.scraper_factory(payload, settings)
        try:
            candidates = await scraper.discover(city=market.city, angle=angle)
        except ProviderConfigurationError as exc:
            scan_meta = self._scan_meta(
                market=market,
                angle=angle,
                job_id=job_id,
                provider_error=str(exc),
                extra_meta=extra_meta,
            )
            await self.inventory_state.refresh_market_inventory_state(market)
            return {
                "source": source_name,
                "city": market.city,
                "skipped": True,
                "reason": "provider_configuration",
                "ingest": self._empty_ingest(source_name=source_name, city=market.city),
                "scanMeta": scan_meta,
                "verificationJobsEnqueued": 0,
            }

        if feed_filters:
            candidates = [
                candidate
                for candidate in candidates
                if candidate_matches_filters(
                    candidate,
                    feed_filters=feed_filters,
                    latitude=latitude,
                    longitude=longitude,
                )
            ]

        scan_meta = self._scan_meta(
            market=market,
            angle=angle,
            job_id=job_id,
            scraper_meta=dict(getattr(scraper, "last_meta", {}) or {}),
            extra_meta=extra_meta,
        )
        manual_events = build_manual_events(
            candidates=candidates,
            city=market.city,
            state=market.state,
            country=market.country,
            angle=angle,
            source_name=source_name,
            job_id=job_id,
        )
        if not manual_events:
            await self.inventory_state.refresh_market_inventory_state(market)
            return {
                "source": source_name,
                "city": market.city,
                "ingest": self._empty_ingest(source_name=source_name, city=market.city),
                "scanMeta": scan_meta,
                "verificationJobsEnqueued": 0,
            }

        ingest_summary = await self.ingest_factory(self.session).ingest_manual(
            source_name=source_name,
            city=market.city,
            events=manual_events,
            scan_meta=scan_meta,
            job_id=job_id,
            scheduler_run_id=scheduler_run_id,
        )

        verification_enqueued = 0
        if settings.enable_verification and ingest_summary.event_ids:
            verification_enqueued = await self.verification_factory(
                self.session
            ).enqueue_verification_jobs(
                limit=len(ingest_summary.event_ids),
                event_ids=ingest_summary.event_ids,
                scheduler_run_id=scheduler_run_id,
            )
        await self.inventory_state.refresh_market_inventory_state(market)
        return {
            "source": source_name,
            "city": market.city,
            "ingest": ingest_summary.as_dict(),
            "scanMeta": scan_meta,
            "verificationJobsEnqueued": verification_enqueued,
        }

    @staticmethod
    def _default_scraper_factory(payload: dict[str, Any], settings: Any) -> SearchGroundedScraper:
        return build_market_scan_scraper(
            payload,
            provider_config=provider_config_from_settings(settings),
        )

    @staticmethod
    def _empty_ingest(*, source_name: str, city: str) -> dict[str, Any]:
        return {
            "ok": True,
            "sourceId": None,
            "ingestRunId": None,
            "source": source_name,
            "city": city,
            "discovered": 0,
            "insertedEvents": 0,
            "updatedEvents": 0,
            "insertedOccurrences": 0,
            "eventIds": [],
        }

    @staticmethod
    def _scan_meta(
        *,
        market: MarketDescriptor,
        angle: str,
        job_id: str | None,
        scraper_meta: dict[str, Any] | None = None,
        provider_error: str | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scan_meta: dict[str, Any] = {
            "angle": angle,
            "jobId": job_id,
            "marketKey": market.key,
            "heatTier": market.heat_tier,
        }
        if scraper_meta:
            scan_meta.update(scraper_meta)
        if provider_error is not None:
            scan_meta["providerError"] = provider_error
        if extra_meta:
            scan_meta.update(extra_meta)
        return scan_meta


def build_manual_events(
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

        ticket_offers_payload = [
            {
                "url": to.url,
                "provider": to.provider,
                "priceLabel": to.price_label,
                "isFree": to.is_free,
            }
            for to in (candidate.ticket_offers or [])
        ]

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
                "description": candidate.description
                or f"Discovered by MARKET_SCAN worker ({angle})",
                "category": normalize_category(candidate.category),
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
