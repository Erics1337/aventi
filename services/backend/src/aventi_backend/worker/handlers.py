from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.gemini import GeminiEventScraper
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.market_inventory import (
    MarketWarmupService,
    build_market_descriptor,
    execute_city_scan,
    market_from_payload,
)
from aventi_backend.services.verification import VerificationService


async def process_job(job: JobRecord, session: AsyncSession) -> dict[str, Any] | None:
    if job.type == JobType.MARKET_WARMUP:
        return await _handle_market_warmup(job, session)
    if job.type == JobType.CITY_SCAN:
        return await _handle_city_scan(job, session)
    if job.type == JobType.VERIFY_EVENT:
        return await _handle_verify_event(job, session)
    if job.type == JobType.ENRICH_EVENT:
        return await _handle_enrich_event(job, session)
    if job.type == JobType.GENERATE_IMAGE:
        return await _handle_generate_image(job, session)
    raise ValueError(f"Unsupported job type: {job.type}")


async def _handle_generate_image(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("GENERATE_IMAGE job payload requires string `eventId`")

    # Fetch event to build a prompt
    result = await session.execute(
        text("SELECT id, title, description, category, vibes, tags, city FROM events WHERE id = :id"),
        {"id": event_id}
    )
    event_row = result.mappings().first()
    if not event_row:
        return {"skipped": True, "reason": "event-not-found", "eventId": event_id}

    # Use a GeminiImageGenerator since we have an API key configured
    from aventi_backend.services.gemini import GeminiImageGenerator
    generator = GeminiImageGenerator()
    prompt = f"A promotional poster for {event_row.get('title')} in {event_row.get('city')}, vibes: {', '.join(event_row.get('vibes') or [])}"
    image_url = await generator.generate_event_image(prompt)

    # Update event with the generated image
    await session.execute(
        text("UPDATE events SET image_url = :image_url, updated_at = now() WHERE id = :id"),
        {
            "image_url": image_url,
            "id": event_id
        }
    )
    await session.commit()

    return {
        "jobId": job.id,
        "jobType": str(job.type),
        "eventId": event_id,
        "imageUrl": image_url
    }

async def _handle_enrich_event(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("ENRICH_EVENT job payload requires string `eventId`")

    # Fetch event details
    result = await session.execute(
        text("SELECT id, title, description, category, vibes, tags, metadata, city FROM events WHERE id = :id"),
        {"id": event_id}
    )
    event_row = result.mappings().first()
    if not event_row:
        return {"skipped": True, "reason": "event-not-found", "eventId": event_id}

    description = event_row.get("description")
    if not description or len(description.strip()) < 20:
        return {"skipped": True, "reason": "insufficient-description", "eventId": event_id}

    context = f"{event_row.get('title', '')} in {event_row.get('city', '')}"
    
    # Run enrichment
    enricher = GeminiEventScraper(source_name="enrichment-job")
    metadata_updates = await enricher.enrich_event(description=description, context=context)

    if not metadata_updates:
         return {"skipped": True, "reason": "no-metadata-extracted", "eventId": event_id}

    # Prepare update payload
    update_data: dict[str, Any] = {}
    if "category" in metadata_updates and not event_row.get("category"):
         update_data["category"] = metadata_updates["category"]
    
    existing_vibes = event_row.get("vibes") or []
    new_vibes = metadata_updates.get("vibes") or []
    merged_vibes = list(set(existing_vibes + new_vibes))[:5] # keep max 5
    if merged_vibes != existing_vibes:
        update_data["vibes"] = merged_vibes

    existing_tags = event_row.get("tags") or []
    new_tags = metadata_updates.get("tags") or []
    merged_tags = list(set(existing_tags + new_tags))[:8] # keep max 8
    if merged_tags != existing_tags:
         update_data["tags"] = merged_tags

    existing_metadata = event_row.get("metadata") or {}
    new_metadata = dict(existing_metadata)
    
    for key in ["dressCode", "ageRestriction", "priceLabel"]:
        if key in metadata_updates and metadata_updates[key]:
             new_metadata[key] = metadata_updates[key]
    
    if "isFree" in metadata_updates:
         update_data["is_free"] = metadata_updates["isFree"]

    new_metadata["enrichedAt"] = datetime.now(tz=UTC).isoformat()
    update_data["metadata"] = new_metadata

    # Update database
    set_clauses = ", ".join([f"{k} = :{k}" for k in update_data.keys()])
    if not set_clauses:
        return {"skipped": True, "reason": "no-updates-needed", "eventId": event_id}

    await session.execute(
        text(f"UPDATE events SET {set_clauses} WHERE id = :id"),
        {**update_data, "id": event_id}
    )
    await session.commit()

    return {
        "jobId": job.id,
        "jobType": str(job.type),
        "eventId": event_id,
        "updates": list(update_data.keys()),
        "extracted": metadata_updates
    }


async def _handle_city_scan(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    market = market_from_payload(payload) or build_market_descriptor(city=str(payload.get("city") or "Austin"))
    if market is None:
        raise ValueError("CITY_SCAN job payload requires market or city context")
    city = market.city
    angle = str(payload.get("angle") or "hidden gems")
    source_name = str(payload.get("sourceName") or f"city-scan:{city.lower()}")
    city_scan_result = await execute_city_scan(
        session,
        market=market,
        angle=angle,
        source_name=source_name,
        source_type=str(payload.get("sourceType")) if payload.get("sourceType") else None,
        source_url=str(payload.get("sourceUrl")) if payload.get("sourceUrl") else None,
        source_data=payload.get("sourceData"),
        job_id=job.id,
    )
    return {"jobId": job.id, "jobType": str(job.type), **city_scan_result}


async def _handle_market_warmup(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    market = market_from_payload(payload)
    if market is None:
        raise ValueError("MARKET_WARMUP job payload requires `marketCity` or `city`")
    result = await MarketWarmupService(session).run_market_warmup(market, job_id=job.id)
    return {"jobId": job.id, "jobType": str(job.type), **result}


async def _handle_verify_event(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("VERIFY_EVENT job payload requires string `eventId`")
    result = await VerificationService(session).verify_event(event_id)
    return {"jobId": job.id, "jobType": str(job.type), **result}
