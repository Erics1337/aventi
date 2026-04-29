from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.gemini import GeminiEventScraper
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.market_inventory import (
    MarketWarmupService,
    build_market_descriptor,
    execute_market_scan,
    market_from_payload,
)
from aventi_backend.services.verification import VerificationService


async def process_job(job: JobRecord, session: AsyncSession) -> dict[str, Any] | None:
    if job.type == JobType.MARKET_WARMUP:
        return await _handle_market_warmup(job, session)
    if job.type == JobType.MARKET_SCAN:
        return await _handle_market_scan(job, session)
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

    result = await session.execute(
        text(
            """
            SELECT
              e.id,
              e.title,
              e.description,
              e.category,
              e.booking_url,
              e.metadata,
              coalesce(v.city, '') as city,
              coalesce(
                array_agg(et.tag order by et.tag)
                  filter (where et.tag_type = 'vibe'),
                '{}'::text[]
              ) as vibes
            FROM events e
            LEFT JOIN venues v ON v.id = e.venue_id
            LEFT JOIN event_tags et ON et.event_id = e.id
            WHERE e.id = :id
            GROUP BY e.id, v.city
            """
        ),
        {"id": event_id},
    )
    event_row = result.mappings().first()
    if not event_row:
        return {"skipped": True, "reason": "event-not-found", "eventId": event_id}

    from aventi_backend.services.gemini import PollinationsImageGenerator
    from aventi_backend.services.storage import SupabaseStorageService
    from aventi_backend.core.settings import get_settings

    settings = get_settings()

    generator = PollinationsImageGenerator(api_key=settings.pollinations_api_key)
    vibes = [str(vibe) for vibe in (event_row.get("vibes") or []) if str(vibe).strip()]
    prompt = (
        f"A cinematic promotional event poster for {event_row.get('title')} "
        f"in {event_row.get('city') or 'the city'}, category: {event_row.get('category')}, "
        f"vibes: {', '.join(vibes or ['social'])}. "
        "No readable text, no logos, atmospheric photography style, vertical composition."
    )
    pollinations_url = await generator.generate_event_image(prompt)

    storage = SupabaseStorageService()
    await storage.ensure_bucket_exists()
    storage_url = await storage.upload_image_from_url(
        pollinations_url, event_id, api_key=generator.api_key
    )
    if not storage_url:
        raise RuntimeError("Generated image could not be persisted to Supabase Storage")

    metadata_patch = {
        "imageSource": "supabase_storage",
        "imageUpdatedAt": datetime.now(tz=UTC).isoformat(),
    }

    await session.execute(
        text(
            """
            UPDATE events
            SET image_url = :image_url,
                metadata = coalesce(metadata, '{}'::jsonb) || cast(:metadata_json as jsonb),
                updated_at = now()
            WHERE id = :id
            """
        ),
        {"image_url": storage_url, "metadata_json": json.dumps(metadata_patch), "id": event_id},
    )
    await session.commit()

    return {
        "jobId": job.id,
        "jobType": str(job.type),
        "eventId": event_id,
        "imageUrl": storage_url,
        "source": "supabase_storage",
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


async def _handle_market_scan(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    market = market_from_payload(payload) or build_market_descriptor(city=str(payload.get("city") or "Austin"))
    if market is None:
        raise ValueError("MARKET_SCAN job payload requires market or city context")
    # Propagate heat_tier hint (supplied by scheduler) so execute_market_scan can
    # tag ingest_runs.metadata with the tier this scan was billed under.
    heat_tier_hint = payload.get("heatTier")
    if isinstance(heat_tier_hint, str) and heat_tier_hint:
        market.heat_tier = heat_tier_hint
    city = market.city
    angle = str(payload.get("angle") or "hidden gems")
    source_name = str(payload.get("sourceName") or f"market-scan:{city.lower()}")
    filter_signature = payload.get("filterSignature")
    extra_meta: dict[str, Any] = {}
    scan_type = payload.get("scanType")
    if isinstance(scan_type, str) and scan_type:
        extra_meta["scanType"] = scan_type
    try:
        filter_payload = payload.get("filters")
        market_scan_result = await execute_market_scan(
            session,
            market=market,
            angle=angle,
            source_name=source_name,
            source_type=str(payload.get("sourceType")) if payload.get("sourceType") else None,
            source_url=str(payload.get("sourceUrl")) if payload.get("sourceUrl") else None,
            source_data=payload.get("sourceData"),
            job_id=job.id,
            feed_filters=filter_payload if isinstance(filter_payload, dict) else None,
            latitude=float(payload["latitude"]) if payload.get("latitude") is not None else None,
            longitude=float(payload["longitude"]) if payload.get("longitude") is not None else None,
            extra_meta=extra_meta or None,
        )
        if isinstance(filter_signature, str) and filter_signature.strip():
            await MarketWarmupService(session).mark_targeted_mining_completed(
                market,
                filter_signature=filter_signature,
            )
    except Exception:
        if isinstance(filter_signature, str) and filter_signature.strip():
            await MarketWarmupService(session).mark_targeted_mining_completed(
                market,
                filter_signature=filter_signature,
            )
        await MarketWarmupService(session)._mark_scan_completed(market, success=False, error=f"market_scan failed for angle={angle}")
        await session.execute(
            text("update public.market_inventory_state set scan_lock_until = null where market_key = :key"),
            {"key": market.key},
        )
        await session.commit()
        raise
    return {"jobId": job.id, "jobType": str(job.type), **market_scan_result}


def _parse_bool(value: Any) -> bool:
    """Parse a boolean from various input types (bool, str)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return False


async def _handle_market_warmup(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    market = market_from_payload(payload)
    if market is None:
        raise ValueError("MARKET_WARMUP job payload requires `marketCity` or `city`")
    result = await MarketWarmupService(session).run_market_warmup(
        market,
        job_id=job.id,
        force_discovery=_parse_bool(payload.get("forceDiscovery")),
    )
    return {"jobId": job.id, "jobType": str(job.type), **result}


async def _handle_verify_event(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("VERIFY_EVENT job payload requires string `eventId`")
    result = await VerificationService(session).verify_event(event_id)
    return {"jobId": job.id, "jobType": str(job.type), **result}
