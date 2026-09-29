from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.services.budgets import BudgetManager
from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.pollinations import PollinationsGroundedSelector


class PremiumRequiredError(PermissionError):
    pass


class InsightUnavailableError(RuntimeError):
    pass


def _safe_source(value: Any, *, label: str) -> dict[str, str] | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return {"label": label, "url": value}


def _context_hash(context: dict[str, Any]) -> str:
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class InsightSelector(Protocol):
    async def select(
        self,
        *,
        facts: list[dict[str, str]],
        compatible_events: list[dict[str, Any]],
        preferences: dict[str, Any],
    ) -> dict[str, list[str]]: ...


class InsightsService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        selector: InsightSelector | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        api_key = getattr(self.settings, "pollinations_api_key", None)
        self.selector = selector or (PollinationsGroundedSelector(api_key) if api_key else None)

    async def get_or_enqueue(
        self,
        *,
        user_id: str,
        event_id: str,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            event_id = str(UUID(event_id))
        except ValueError as exc:
            raise ValueError("event_id must be a UUID") from exc
        await self._require_premium(user_id)
        # Build the key from current verified state before reading cache. Hidden,
        # expired, or newly-unverified events can never leak an older cached result.
        context = await self._build_context(user_id, event_id, filters or {})
        context_hash = _context_hash(context)
        await self.session.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"event-insights:{event_id}:{context_hash}"},
        )
        existing = await self.session.execute(
            text(
                """
                select status, payload, job_id, generated_at, expires_at, updated_at
                from public.event_insights
                where event_id=:event_id and context_hash=:context_hash
                """
            ),
            {"event_id": event_id, "context_hash": context_hash},
        )
        row = existing.mappings().first()
        now = datetime.now(tz=UTC)
        if row and row["status"] == "ready" and row["expires_at"] and row["expires_at"] > now:
            event = await self._load_event(event_id)
            if event is None:
                raise InsightUnavailableError("Event is no longer available")
            current_pairings = {
                item["eventId"]: item for item in await self._load_compatible_events(event, context)
            }
            payload = dict(row["payload"] or {})
            payload["compatibleEvents"] = [
                current_pairings[item["eventId"]]
                for item in payload.get("compatibleEvents", [])
                if item.get("eventId") in current_pairings
            ][:2]
            return {
                "status": "ready",
                "insight": payload,
                "generatedAt": row["generated_at"],
                "expiresAt": row["expires_at"],
            }
        if (
            row
            and row["status"] in {"queued", "generating"}
            and row["updated_at"] > now - timedelta(minutes=10)
        ):
            return {"status": "pending", "jobId": row["job_id"], "retryAfterSeconds": 3}

        job_type = getattr(JobType, "GENERATE_INSIGHTS", None)
        if job_type is None:
            raise InsightUnavailableError("Insight worker is not deployed")
        try:
            if not await BudgetManager(self.session, settings=self.settings).remaining("pollinations"):
                raise InsightUnavailableError(
                    "AI processing is paused until the provider budget resets"
                )
            if row and row["job_id"]:
                await self.session.execute(
                    text(
                        """
                        update public.jobs set status='cancelled', updated_at=now()
                        where id=:job_id and (
                          status in ('queued', 'retry')
                          or (status='processing' and lease_expires_at < now())
                        )
                        """
                    ),
                    {"job_id": row["job_id"]},
                )
            await self.session.execute(
                text(
                    """
                    insert into public.event_insights
                      (event_id, context_hash, context, status, updated_at)
                    values (:event_id, :context_hash, cast(:context as jsonb), 'queued', now())
                    on conflict (event_id, context_hash) do update set
                      context=excluded.context, status='queued', payload=null,
                      last_error=null, updated_at=now()
                    """
                ),
                {
                    "event_id": event_id,
                    "context_hash": context_hash,
                    "context": json.dumps(context, default=str),
                },
            )
            job = await JobQueueRepository(self.session).enqueue_job(
                job_type,
                {"eventId": event_id, "contextHash": context_hash, "context": context},
                max_attempts=3,
            )
            await self.session.execute(
                text(
                    """
                    update public.event_insights set job_id=:job_id, updated_at=now()
                    where event_id=:event_id and context_hash=:context_hash
                    """
                ),
                {"event_id": event_id, "context_hash": context_hash, "job_id": job.id},
            )
            # Cache state, durable job, and outbox become visible together.
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            if isinstance(exc, InsightUnavailableError):
                raise
            raise InsightUnavailableError("Insight generation could not be queued") from exc
        return {"status": "pending", "jobId": job.id, "retryAfterSeconds": 3}

    async def generate_and_cache(
        self,
        event_id: str,
        *,
        context_hash: str = "default",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            event_id = str(UUID(event_id))
        except ValueError as exc:
            raise ValueError("event_id must be a UUID") from exc
        context = context or {}
        await self.session.execute(
            text(
                """
                update public.event_insights set status='generating', updated_at=now()
                where event_id=:event_id and context_hash=:context_hash
                """
            ),
            {"event_id": event_id, "context_hash": context_hash},
        )
        await self.session.commit()
        event = await self._load_event(event_id)
        if event is None:
            await self._mark_failed(event_id, context_hash, "Event is not currently verified")
            raise InsightUnavailableError("Event is not currently verified")
        compatible = await self._load_compatible_events(event, context)
        facts = self._build_facts(event, context)
        if self.selector is None:
            await self._mark_failed(event_id, context_hash, "Insight selector is not configured")
            raise InsightUnavailableError("Insight selector is not configured")
        await self._reserve_budget(event_id, commit=True)
        selected = await self.selector.select(
            facts=facts,
            compatible_events=compatible,
            preferences=dict(context.get("preferences") or {}),
        )
        fact_by_id = {fact["id"]: fact for fact in facts}
        compatible_by_id = {item["eventId"]: item for item in compatible}
        selected_facts = [
            fact_by_id[fact_id]["text"]
            for fact_id in selected.get("factIds", [])
            if fact_id in fact_by_id
        ][:3]
        selected_compatible = [
            compatible_by_id[item_id]
            for item_id in selected.get("compatibleEventIds", [])
            if item_id in compatible_by_id
        ][:2]

        metadata = dict(event["metadata"] or {})
        sources: list[dict[str, str]] = []
        for candidate in (
            _safe_source(event["booking_url"], label="Official event listing"),
            _safe_source(metadata.get("sourceUrl"), label="Event source"),
            _safe_source(metadata.get("officialUrl"), label="Official source"),
        ):
            if candidate and candidate["url"] not in {item["url"] for item in sources}:
                sources.append(candidate)
            if len(sources) == 2:
                break

        payload = {
            "summary": " ".join(
                fact["text"] for fact in facts if fact["field"] in {"category", "vibes"}
            ),
            "venueName": event["venue_name"],
            "city": event["city"],
            "startsAt": event["starts_at"],
            "insiderTips": [
                value for value in selected_facts if not value.startswith("Matches your")
            ],
            "aiGenerated": True,
            "sources": sources,
            "compatibleEvents": selected_compatible,
            "grounded": True,
            "selectionMethod": "grounded_model_ids",
        }
        cache_hours = int(getattr(self.settings, "insights_cache_hours", 24) or 24)
        expires_at = datetime.now(tz=UTC) + timedelta(hours=max(1, cache_hours))
        await self.session.execute(
            text(
                """
                update public.event_insights
                set status='ready', payload=cast(:payload as jsonb), generated_at=now(),
                    expires_at=:expires_at, last_error=null, updated_at=now()
                where event_id=:event_id and context_hash=:context_hash
                """
            ),
            {
                "event_id": event_id,
                "context_hash": context_hash,
                "payload": json.dumps(payload, default=str),
                "expires_at": expires_at,
            },
        )
        await self.session.commit()
        return payload

    async def _build_context(
        self, user_id: str, event_id: str, filters: dict[str, Any]
    ) -> dict[str, Any]:
        event_result = await self.session.execute(
            text(
                """
                select updated_at, last_verified_at
                from public.events
                where id=:event_id and hidden=false and verification_status='verified'
                  and last_verified_active is true
                  and last_verified_at >= now() - interval '72 hours'
                  and exists(select 1 from public.event_occurrences o where o.event_id=events.id and not o.cancelled and o.starts_at>now())
                """
            ),
            {"event_id": event_id},
        )
        event = event_result.mappings().first()
        if event is None:
            raise InsightUnavailableError("Event is not currently verified")
        prefs_result = await self.session.execute(
            text(
                """
                select categories, vibes, radius_miles, travel_mode_city, updated_at
                from public.user_preferences where user_id=:user_id
                """
            ),
            {"user_id": user_id},
        )
        prefs = prefs_result.mappings().first()
        preferences = {
            "categories": sorted(str(v) for v in (prefs["categories"] or [])) if prefs else [],
            "vibes": sorted(str(v) for v in (prefs["vibes"] or [])) if prefs else [],
            "radiusMiles": int(prefs["radius_miles"]) if prefs else None,
            "travelModeCity": prefs["travel_mode_city"] if prefs else None,
            "revision": prefs["updated_at"] if prefs else None,
        }
        radius = filters.get("radiusMiles") or 10
        age = filters.get("ageRestriction") or "all"
        if radius not in {5, 10, 25, 50, 100} or age not in {"all", "18+", "21+"}:
            raise ValueError("Unsupported insight filters")
        destination_id = filters.get("destinationId")
        location_result = await self.session.execute(
            text("select latitude,longitude,timezone from public.destinations where id=:id")
            if destination_id
            else text("select latitude,longitude,timezone from public.profiles where id=:id"),
            {"id": str(UUID(destination_id)) if destination_id else user_id},
        )
        location = location_result.mappings().first()
        if not location or location["latitude"] is None or location["longitude"] is None:
            raise InsightUnavailableError("A discovery location is required")
        filters = {
            **filters,
            "radiusMiles": radius,
            "ageRestriction": age,
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "timezone": location["timezone"] or "UTC",
        }
        cache_hours = max(1, int(getattr(self.settings, "insights_cache_hours", 24) or 24))
        return {
            "eventRevision": [event["updated_at"], event["last_verified_at"]],
            "preferences": preferences,
            "filters": filters,
            "cacheBucket": int(datetime.now(tz=UTC).timestamp() // (cache_hours * 3600)),
        }

    async def _load_event(self, event_id: str) -> Any | None:
        result = await self.session.execute(
            text("""
            select e.*, e.id::text as id, v.name as venue_name, v.city, v.state,
                   v.latitude, v.longitude, o.starts_at, o.ends_at, o.timezone,
                   array(select tag from public.event_tags t where t.event_id=e.id) as tags
            from public.events e join public.venues v on v.id=e.venue_id
            join lateral (select starts_at,ends_at,timezone from public.event_occurrences
                where event_id=e.id and not cancelled and starts_at>now() order by starts_at limit 1) o on true
            where e.id=:event_id and not e.hidden and e.verification_status='verified'
              and e.last_verified_active is true and e.last_verified_at>=now()-interval '72 hours'
              and v.country='US' and v.location is not null
        """),
            {"event_id": event_id},
        )
        return result.mappings().first()

    async def _load_compatible_events(
        self, event: Any, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        # Without the main event's end time a nonoverlapping pairing is unknown.
        if not event["ends_at"]:
            return []
        filters = context.get("filters") or {}
        result = await self.session.execute(
            text("""
            select distinct on (e.id) e.id::text, e.title, e.booking_url,
                   v.name as venue_name, o.starts_at
            from public.events e join public.venues v on v.id=e.venue_id
            join public.event_occurrences o on o.event_id=e.id
            where e.id<>:event_id and not e.hidden and e.verification_status='verified'
              and e.last_verified_active is true and e.last_verified_at>=now()-interval '72 hours'
              and v.country='US' and not o.cancelled and o.starts_at>now()
              and o.ends_at is not null
              and (o.starts_at>=:main_end or o.ends_at<=:main_start)
              and (o.starts_at at time zone :timezone)::date=(:main_start at time zone :timezone)::date
              and (:start_date='' or (o.starts_at at time zone :timezone)::date>=cast(nullif(:start_date,'') as date))
              and (:end_date='' or (o.starts_at at time zone :timezone)::date<=cast(nullif(:end_date,'') as date))
              and extensions.st_dwithin(v.location,extensions.st_setsrid(extensions.st_makepoint(:longitude,:latitude),4326)::extensions.geography,:radius)
              and extensions.st_dwithin(v.location,extensions.st_setsrid(extensions.st_makepoint(:event_longitude,:event_latitude),4326)::extensions.geography,8046.72)
              and (:age='all' or (e.admission_restriction=:age and e.admission_source_url is not null))
              and (cardinality(cast(:categories as text[]))=0 or e.category=any(cast(:categories as text[])))
              and (cardinality(cast(:vibes as text[]))=0 or exists(select 1 from public.event_tags t where t.event_id=e.id and t.tag=any(cast(:vibes as text[]))))
            order by e.id,o.starts_at limit 6
        """),
            {
                "event_id": event["id"],
                "main_start": event["starts_at"],
                "main_end": event["ends_at"],
                "timezone": filters.get("timezone") or event["timezone"] or "UTC",
                "start_date": filters.get("startDate") or "",
                "end_date": filters.get("endDate") or "",
                "latitude": filters.get("latitude", event["latitude"]),
                "longitude": filters.get("longitude", event["longitude"]),
                "event_latitude": event["latitude"],
                "event_longitude": event["longitude"],
                "radius": float(filters.get("radiusMiles") or 10) * 1609.344,
                "age": filters.get("ageRestriction") or "all",
                "categories": filters.get("categories") or [],
                "vibes": filters.get("vibes") or [],
            },
        )
        return [
            {
                "eventId": row["id"],
                "title": row["title"],
                "venueName": row["venue_name"],
                "startsAt": row["starts_at"],
                "bookingUrl": row["booking_url"],
            }
            for row in result.mappings().all()
        ]

    @staticmethod
    def _build_facts(event: Any, context: dict[str, Any]) -> list[dict[str, str]]:
        facts: list[dict[str, str]] = []
        # Crowd descriptions and inferred dress/price/music metadata are not admission evidence.
        if event.get("admission_restriction") and event.get("admission_source_url"):
            facts.append(
                {
                    "id": "admission",
                    "field": "admission",
                    "text": f"Listed admission restriction: {event['admission_restriction']}.",
                }
            )
        preferences = dict(context.get("preferences") or {})
        if event["category"] in set(preferences.get("categories") or []):
            facts.append(
                {
                    "id": "category-match",
                    "field": "category",
                    "text": f"Matches your interest in {event['category']}.",
                }
            )
        matching_vibes = sorted(set(event["tags"] or []) & set(preferences.get("vibes") or []))
        if matching_vibes:
            facts.append(
                {
                    "id": "vibe-match",
                    "field": "vibes",
                    "text": f"Matches your {', '.join(matching_vibes[:2])} preferences.",
                }
            )
        return facts

    async def _require_premium(self, user_id: str) -> None:
        result = await self.session.execute(
            text(
                """
                select coalesce(is_premium, false)
                  and valid_until > now()
                from public.premium_entitlements where user_id=:user_id
                """
            ),
            {"user_id": user_id},
        )
        if result.scalar_one_or_none() is not True:
            raise PremiumRequiredError("Aventi Unlimited is required for event insights")

    async def _reserve_budget(self, event_id: str, *, commit: bool) -> None:
        from aventi_backend.services.budgets import BudgetError, BudgetManager

        try:
            await BudgetManager(self.session, settings=self.settings).reserve(
                "pollinations", units=1, operation=f"insights:{event_id}", commit=commit
            )
        except BudgetError as exc:
            raise InsightUnavailableError(str(exc)) from exc

    async def _mark_failed(self, event_id: str, context_hash: str, error: str) -> None:
        await self.session.execute(
            text(
                """
                update public.event_insights
                set status='failed', last_error=:error, updated_at=now()
                where event_id=:event_id and context_hash=:context_hash
                """
            ),
            {"event_id": event_id, "context_hash": context_hash, "error": error[:1000]},
        )
        await self.session.commit()
