from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.gemini import GeminiEventScraper
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.services.market_inventory import (
    MarketWarmupService,
    build_market_descriptor,
    execute_market_scan,
    market_from_payload,
)
from aventi_backend.services.verification import VerificationService


async def process_job(job: JobRecord, session: AsyncSession) -> dict[str, Any] | None:
    if job.type == JobType.HEALTH_CHECK:
        await session.execute(text("select 1"))
        return {"ok": True}
    if job.type == JobType.RETRY_ACCOUNT_DELETION:
        return await _handle_account_deletion(job, session)
    if job.type == JobType.RECONCILE_SUBSCRIPTION:
        return await _handle_subscription_reconcile(job, session)
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
    if job.type == JobType.GENERATE_INSIGHTS:
        return await _handle_generate_insights(job, session)
    raise ValueError(f"Unsupported job type: {job.type}")


async def _handle_account_deletion(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    user_id = (job.payload or {}).get("userId")
    if not isinstance(user_id, str):
        raise ValueError("RETRY_ACCOUNT_DELETION payload requires string `userId`")
    from aventi_backend.services.accounts import AccountDeletionService

    result = await AccountDeletionService(session).request_deletion(user_id)
    return {"userId": user_id, "result": result}


async def _handle_subscription_reconcile(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    user_id = (job.payload or {}).get("userId")
    if not isinstance(user_id, str):
        raise ValueError("RECONCILE_SUBSCRIPTION payload requires string `userId`")
    from aventi_backend.services.billing import BillingService

    result = await BillingService(session).reconcile(
        authenticated_user_id=user_id, app_user_id=user_id
    )
    return {"userId": user_id, "result": result}


async def _handle_generate_image(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("GENERATE_IMAGE job payload requires string `eventId`")

    from aventi_backend.services.budgets import BudgetManager

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

    from aventi_backend.core.settings import get_settings
    from aventi_backend.services.gemini import PollinationsImageGenerator
    from aventi_backend.services.storage import SupabaseStorageService

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
    await BudgetManager(session).reserve("pollinations", operation=f"event-image:{event_id}")

    storage = SupabaseStorageService()
    await storage.ensure_bucket_exists()
    storage_url = await storage.upload_image_from_url(
        pollinations_url, event_id, api_key=generator.api_key
    )
    if not storage_url:
        raise RuntimeError("Generated image could not be persisted to Supabase Storage")

    metadata_patch = {
        "imageSource": "supabase_storage",
        "imageAiGenerated": True,
        "imageProvider": "pollinations",
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

    result = await session.execute(
        text(
            """
            select e.id, e.title, e.description, e.category, e.metadata, e.booking_url,
                   coalesce(v.city, '') as city,
                   coalesce(array_agg(et.tag order by et.tag)
                     filter (where et.tag_type = 'vibe'), '{}'::text[]) as vibes,
                   coalesce(array_agg(et.tag order by et.tag)
                     filter (where et.tag_type = 'tag'), '{}'::text[]) as tags
            from public.events e
            left join public.venues v on v.id = e.venue_id
            left join public.event_tags et on et.event_id = e.id
            where e.id = :id
            group by e.id, v.city
            """
        ),
        {"id": event_id},
    )
    event_row = result.mappings().first()
    if not event_row:
        return {"skipped": True, "reason": "event-not-found", "eventId": event_id}

    description = event_row.get("description")
    if not description or len(description.strip()) < 20:
        return {"skipped": True, "reason": "insufficient-description", "eventId": event_id}

    # Enrichment facts must originate in the fetched source, not an earlier AI summary.
    from aventi_backend.services.gemini import _document_text
    from aventi_backend.services.safe_http import safe_fetch

    try:
        source = await safe_fetch(
            str(event_row["booking_url"]),
            max_bytes=512 * 1024,
            timeout_seconds=10,
            allowed_content_types=["text/html", "text/plain", "application/xhtml+xml"],
        )
        source.raise_for_status()
        description = _document_text(source)
    except Exception:
        return {"skipped": True, "reason": "source-unavailable", "eventId": event_id}
    if not description:
        return {"skipped": True, "reason": "source-empty", "eventId": event_id}

    context = f"{event_row.get('title', '')} in {event_row.get('city', '')}"

    from aventi_backend.services.budgets import BudgetManager

    enricher = GeminiEventScraper(
        source_name="enrichment-job", budget_manager=BudgetManager(session)
    )
    metadata_updates = await enricher.enrich_event(description=description, context=context)

    if not metadata_updates:
        return {"skipped": True, "reason": "no-metadata-extracted", "eventId": event_id}

    update_data: dict[str, Any] = {}
    category = metadata_updates.get("category")
    if category and str(event_row.get("category") or "").lower() in {"", "experiences"}:
        update_data["category"] = ManualIngestService._normalize_category(category)

    existing_vibes = _normalise_labels(event_row.get("vibes"), limit=5)
    existing_tags = _normalise_labels(event_row.get("tags"), limit=8)
    merged_vibes = _normalise_labels(
        [*existing_vibes, *(metadata_updates.get("vibes") or [])], limit=5
    )
    merged_tags = _normalise_labels(
        [*existing_tags, *(metadata_updates.get("tags") or [])], limit=8
    )

    existing_metadata = event_row.get("metadata") or {}
    new_metadata = dict(existing_metadata)

    for key in ["dressCode", "priceLabel"]:
        if (
            key in metadata_updates
            and metadata_updates[key]
            and str(metadata_updates[key]).casefold() in description.casefold()
        ):
            new_metadata[key] = metadata_updates[key]

    admission = _normalise_admission(metadata_updates.get("ageRestriction"))
    if admission and _description_supports_admission(description, admission):
        update_data["admission_restriction"] = admission
        update_data["admission_source_url"] = str(event_row["booking_url"])

    if metadata_updates.get("isFree") is True and re.search(
        r"\bfree (?:entry|admission|tickets)\b", description, re.IGNORECASE
    ):
        update_data["is_free"] = True
    new_metadata["enrichmentProvenance"] = {
        "sourceUrl": source.url,
        "fetchedAt": datetime.now(tz=UTC).isoformat(),
        "method": "source_document",
    }

    new_metadata["enrichedAt"] = datetime.now(tz=UTC).isoformat()
    update_data["metadata_json"] = json.dumps(new_metadata)

    set_clauses = ", ".join(
        "metadata = cast(:metadata_json as jsonb)" if key == "metadata_json" else f"{key} = :{key}"
        for key in update_data
    )
    if not set_clauses:
        return {"skipped": True, "reason": "no-updates-needed", "eventId": event_id}

    await session.execute(
        text(f"UPDATE public.events SET {set_clauses}, updated_at = now() WHERE id = :id"),
        {**update_data, "id": event_id},
    )
    for label_type, labels in (("vibe", merged_vibes), ("tag", merged_tags)):
        for label in labels:
            await session.execute(
                text(
                    """
                    insert into public.event_tags (event_id, tag, tag_type, score)
                    values (:event_id, :tag, :tag_type, null)
                    on conflict (event_id, tag, tag_type) do nothing
                    """
                ),
                {"event_id": event_id, "tag": label, "tag_type": label_type},
            )
    await session.commit()

    return {
        "jobId": job.id,
        "jobType": str(job.type),
        "eventId": event_id,
        "updates": [
            *("metadata" if key == "metadata_json" else key for key in update_data),
            "event_tags",
        ],
        "extracted": metadata_updates,
    }


def _normalise_labels(values: Any, *, limit: int) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    labels: list[str] = []
    for value in values:
        label = "-".join(str(value).strip().lower().split())[:64].strip("-")
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _normalise_admission(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace(" ", "")
    if normalized in {"allages", "all", "family", "familyfriendly"}:
        return "all"
    if normalized in {"18", "18+", "18andover"}:
        return "18+"
    if normalized in {"21", "21+", "21andover"}:
        return "21+"
    return None


def _description_supports_admission(description: str, admission: str) -> bool:
    text_value = " ".join(description.lower().split())
    if admission == "all":
        return any(phrase in text_value for phrase in ("all ages", "family friendly"))
    age = admission.removesuffix("+")
    return any(
        phrase in text_value for phrase in (f"{age}+", f"{age} and over", f"ages {age} and up")
    )


async def _handle_market_scan(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    market = market_from_payload(payload) or build_market_descriptor(
        city=str(payload.get("city") or "Austin")
    )
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
        await MarketWarmupService(session)._mark_scan_completed(
            market, success=False, error=f"market_scan failed for angle={angle}"
        )
        await session.execute(
            text(
                "update public.market_inventory_state set scan_lock_until = null where market_key = :key"
            ),
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
        start_date=str(payload["startDate"]) if payload.get("startDate") else None,
        end_date=str(payload["endDate"]) if payload.get("endDate") else None,
    )
    return {"jobId": job.id, "jobType": str(job.type), **result}


async def _handle_verify_event(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("VERIFY_EVENT job payload requires string `eventId`")
    result = await VerificationService(session).verify_event(event_id)
    return {"jobId": job.id, "jobType": str(job.type), **result}


async def _handle_generate_insights(job: JobRecord, session: AsyncSession) -> dict[str, Any]:
    payload = job.payload or {}
    event_id = payload.get("eventId")
    if not isinstance(event_id, str):
        raise ValueError("GENERATE_INSIGHTS job payload requires string `eventId`")
    from aventi_backend.services.insights import InsightsService

    context_hash = str(payload.get("contextHash") or "default")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    result = await InsightsService(session).generate_and_cache(
        event_id, context_hash=context_hash, context=context
    )
    return {"jobId": job.id, "jobType": str(job.type), "eventId": event_id, "result": result}
