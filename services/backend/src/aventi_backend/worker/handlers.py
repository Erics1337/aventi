from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.providers import build_city_scan_scraper
from aventi_backend.services.verification import VerificationService


async def process_job(job: JobRecord, session: AsyncSession) -> dict[str, Any] | None:
    if job.type == JobType.CITY_SCAN:
        return await _handle_city_scan(job, session)
    if job.type == JobType.VERIFY_EVENT:
        return await _handle_verify_event(job, session)
    if job.type in {JobType.ENRICH_EVENT, JobType.GENERATE_IMAGE}:
        # Stubs remain until LLM/image integrations are implemented.
        return {"skipped": True, "jobType": str(job.type), "reason": "handler-not-implemented"}
    raise ValueError(f"Unsupported job type: {job.type}")


async def _handle_city_scan(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    city = str(payload.get("city") or "Austin")
    angle = str(payload.get("angle") or "hidden gems")
    source_name = str(payload.get("sourceName") or f"city-scan:{city.lower()}")

    scraper = build_city_scan_scraper(payload)
    candidates = await scraper.discover(city=city, angle=angle)

    base_time = datetime.now(tz=UTC) + timedelta(hours=4)
    manual_events: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        manual_events.append(
            {
                "title": candidate.title,
                "description": candidate.description or f"Discovered by CITY_SCAN worker ({angle})",
                "category": candidate.category or "experiences",
                "bookingUrl": candidate.booking_url,
                "startsAt": (
                    candidate.starts_at or (base_time + timedelta(hours=index * 2))
                ).isoformat(),
                "endsAt": (
                    candidate.ends_at
                    or (candidate.starts_at + timedelta(hours=3) if candidate.starts_at else None)
                    or (base_time + timedelta(hours=index * 2 + 3))
                ).isoformat(),
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
                    "discoveredByJobId": job.id,
                },
            }
        )

    ingest_summary = await ManualIngestService(session).ingest_manual(source_name=source_name, city=city, events=manual_events)
    verification_enqueued = await VerificationService(session).enqueue_verification_jobs(
        limit=10,
        event_ids=ingest_summary.event_ids,
    )
    return {
        "jobId": job.id,
        "jobType": str(job.type),
        "source": source_name,
        "city": city,
        "ingest": ingest_summary.as_dict(),
        "verificationJobsEnqueued": verification_enqueued,
    }


async def _handle_verify_event(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("VERIFY_EVENT job payload requires string `eventId`")
    result = await VerificationService(session).verify_event(event_id)
    return {"jobId": job.id, "jobType": str(job.type), **result}
