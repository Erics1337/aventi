from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.event_images import infer_image_source, should_generate_main_image


@dataclass(slots=True)
class ManualIngestSummary:
    source_id: str
    ingest_run_id: str
    source_name: str
    city: str
    discovered_count: int
    inserted_events: int
    updated_events: int
    inserted_occurrences: int
    event_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "sourceId": self.source_id,
            "ingestRunId": self.ingest_run_id,
            "source": self.source_name,
            "city": self.city,
            "discovered": self.discovered_count,
            "insertedEvents": self.inserted_events,
            "updatedEvents": self.updated_events,
            "insertedOccurrences": self.inserted_occurrences,
            "eventIds": self.event_ids,
        }


class ManualIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest_manual(
        self,
        source_name: str,
        city: str,
        events: list[dict[str, Any]],
        *,
        scan_meta: dict[str, Any] | None = None,
    ) -> ManualIngestSummary:
        if not events:
            raise ValueError("Manual ingest requires at least one event payload")

        source = await self._ensure_ingest_source(source_name)
        ingest_run = await self._create_ingest_run(source_id=source["id"], city=city, discovered_count=len(events))

        inserted_events = 0
        updated_events = 0
        inserted_occurrences = 0
        near_duplicates_skipped = 0
        image_jobs_enqueued = 0
        image_job_event_ids: set[str] = set()
        event_ids: list[str] = []
        try:
            for raw_event in events:
                normalized = self._normalize_event_payload(raw_event, default_city=city)
                row_counts = await self._upsert_event_bundle(normalized)

                event_id = row_counts["event_id"]
                inserted_event = row_counts["inserted_event"]

                inserted_events += inserted_event
                updated_events += row_counts["updated_event"]
                inserted_occurrences += row_counts["inserted_occurrence"]
                near_duplicates_skipped += row_counts.get("near_duplicate", 0)
                event_ids.append(event_id)

                event_state = await self._fetch_event_image_state(event_id)
                metadata = event_state.get("metadata") if isinstance(event_state, dict) else {}
                incoming_source_type = None
                if isinstance(normalized.get("metadata"), dict):
                    incoming_source_type = normalized["metadata"].get("sourceType")

                should_generate_image = should_generate_main_image(
                    event_state.get("image_url"),
                    metadata if isinstance(metadata, dict) else None,
                    incoming_source_type=incoming_source_type,
                )

                if should_generate_image and event_id not in image_job_event_ids:
                    from aventi_backend.services.jobs import JobQueueRepository, JobType
                    await JobQueueRepository(self.session).enqueue_job(
                        JobType.GENERATE_IMAGE,
                        {"eventId": event_id}
                    )
                    image_jobs_enqueued += 1
                    image_job_event_ids.add(event_id)

            # Merge caller-provided scan_meta (e.g. SerpAPI pagination telemetry)
            # with our own ingest-side counters before persisting.
            final_metadata: dict[str, Any] = {
                "updatedEvents": updated_events,
                "insertedOccurrences": inserted_occurrences,
                "nearDuplicatesSkipped": near_duplicates_skipped,
                "imageJobsEnqueued": image_jobs_enqueued,
                "eventIds": event_ids,
            }
            if scan_meta:
                # scan_meta keys take precedence so callers can override counters.
                for key, value in scan_meta.items():
                    final_metadata[key] = value

            await self.session.execute(
                text(
                    """
                    update public.ingest_runs
                    set status = 'done',
                        started_at = coalesce(started_at, now()),
                        finished_at = now(),
                        discovered_count = :discovered_count,
                        inserted_count = :inserted_count,
                        metadata = cast(:metadata_json as jsonb)
                    where id = :ingest_run_id
                    """
                ),
                {
                    "ingest_run_id": ingest_run["id"],
                    "discovered_count": len(events),
                    "inserted_count": inserted_events,
                    "updated_events": updated_events,
                    "inserted_occurrences": inserted_occurrences,
                    "metadata_json": json.dumps(final_metadata),
                },
            )
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            await self.session.execute(
                text(
                    """
                    update public.ingest_runs
                    set status = 'failed',
                        started_at = coalesce(started_at, now()),
                        finished_at = now(),
                        error_message = :error_message,
                        discovered_count = :discovered_count,
                        inserted_count = :inserted_count
                    where id = :ingest_run_id
                    """
                ),
                {
                    "ingest_run_id": ingest_run["id"],
                    "error_message": str(exc)[:2000],
                    "discovered_count": len(events),
                    "inserted_count": inserted_events,
                },
            )
            await self.session.commit()
            raise

        return ManualIngestSummary(
            source_id=source["id"],
            ingest_run_id=ingest_run["id"],
            source_name=source_name,
            city=city,
            discovered_count=len(events),
            inserted_events=inserted_events,
            updated_events=updated_events,
            inserted_occurrences=inserted_occurrences,
            event_ids=event_ids,
        )

    async def _ensure_ingest_source(self, source_name: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.ingest_sources (name, source_type, enabled, created_at, updated_at)
                values (:name, 'manual', true, now(), now())
                on conflict (name) do update
                set updated_at = now()
                returning id::text as id, name
                """
            ),
            {"name": source_name},
        )
        row = result.mappings().one()
        await self.session.commit()
        return dict(row)

    async def _create_ingest_run(
        self, *, source_id: str, city: str, discovered_count: int
    ) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.ingest_runs (
                    source_id,
                    city,
                    status,
                    started_at,
                    discovered_count,
                    metadata,
                    created_at
                )
                values (
                    :source_id,
                    :city,
                    'running',
                    now(),
                    :discovered_count,
                    '{}'::jsonb,
                    now()
                )
                returning id::text as id
                """
            ),
            {
                "source_id": source_id,
                "city": city,
                "discovered_count": discovered_count,
            },
        )
        row = result.mappings().one()
        await self.session.commit()
        return dict(row)

    async def _upsert_event_bundle(self, event: dict[str, Any]) -> dict[str, Any]:
        event = self._attach_image_metadata(event)
        venue = await self._upsert_venue(event)

        # Fuzzy dedup: if an existing event already lives at the same venue on
        # the same calendar day with a highly-similar title, treat this ingest
        # as an update of that row rather than inserting a parallel duplicate.
        # This catches SerpAPI returning the same concert via two URLs
        # (e.g. Ticketmaster + venue page).
        fuzzy_match = await self._find_fuzzy_duplicate(
            venue_id=venue["id"],
            title=str(event["title"]),
            starts_at=event["startsAt"],
            incoming_booking_url=str(event["bookingUrl"]),
        )
        near_duplicate = 0
        if fuzzy_match is not None:
            event_row = await self._merge_into_existing(fuzzy_match, event)
            near_duplicate = 1
        else:
            event_row = await self._upsert_event(event, venue_id=venue["id"])
        occurrence_row = await self._upsert_occurrence(event_row["id"], event)
        await self._upsert_tags(event_row["id"], event)
        await self._upsert_ticket_offers(event_row["id"], event)

        # Insert extra occurrences for recurring events
        extra_inserted = 0
        for extra in (event.get("extraOccurrences") or []):
            if not isinstance(extra, dict):
                continue
            extra_starts_at = self._coerce_datetime(extra.get("startsAt"))
            extra_ends_at = self._coerce_datetime(extra.get("endsAt"))
            if extra_starts_at is None:
                continue
            extra_row = await self._upsert_occurrence(
                event_row["id"],
                {
                    "startsAt": extra_starts_at,
                    "endsAt": extra_ends_at,
                    "timezone": extra.get("timezone") or event.get("timezone") or "UTC",
                },
            )
            extra_inserted += 1 if extra_row["inserted"] else 0

        return {
            "event_id": event_row["id"],
            "inserted_event": 1 if event_row["inserted"] else 0,
            "updated_event": 0 if event_row["inserted"] else 1,
            "inserted_occurrence": (1 if occurrence_row["inserted"] else 0) + extra_inserted,
            "near_duplicate": near_duplicate,
        }

    async def _fetch_event_image_state(self, event_id: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                select image_url, metadata
                from public.events
                where id = :id
                """
            ),
            {"id": event_id},
        )
        row = result.mappings().first()
        return dict(row) if row else {"image_url": None, "metadata": {}}

    @staticmethod
    def _attach_image_metadata(event: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(event.get("metadata") or {})
        image_source = infer_image_source(
            event.get("imageUrl"),
            str(metadata.get("sourceType")) if metadata.get("sourceType") else None,
        )
        if image_source:
            metadata["imageSource"] = image_source
        return {**event, "metadata": metadata}

    async def _find_fuzzy_duplicate(
        self,
        *,
        venue_id: str,
        title: str,
        starts_at: Any,
        incoming_booking_url: str,
    ) -> dict[str, Any] | None:
        """Return an existing event at the same venue+day with similar title.

        Uses pg_trgm `similarity()` (>=0.85) on the generated ``normalized_title``
        column, and joins event_occurrences to pick rows whose starts_at falls
        on the same calendar day as the incoming candidate. Skips if the
        incoming booking_url matches — the booking_url unique constraint
        handles the exact case already.
        """
        if starts_at is None:
            return None
        result = await self.session.execute(
            text(
                """
                select e.id::text as id, e.title, e.booking_url, e.image_url, e.description
                from public.events e
                join public.event_occurrences eo on eo.event_id = e.id
                where e.venue_id = :venue_id
                  and e.booking_url <> :incoming_url
                  and e.hidden = false
                  and similarity(e.normalized_title, lower(regexp_replace(:incoming_title, '\\s+', ' ', 'g'))) >= 0.85
                  and date_trunc('day', eo.starts_at) = date_trunc('day', cast(:starts_at as timestamptz))
                order by similarity(e.normalized_title, lower(:incoming_title)) desc
                limit 1
                """
            ),
            {
                "venue_id": venue_id,
                "incoming_url": incoming_booking_url,
                "incoming_title": title,
                "starts_at": starts_at,
            },
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def _merge_into_existing(
        self,
        existing: dict[str, Any],
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge incoming candidate into an existing event row without rewriting booking_url."""
        await self.session.execute(
            text(
                """
                update public.events
                set description = coalesce(public.events.description, :description),
                    image_url = case
                        when public.events.metadata->>'imageSource' = 'supabase_storage'
                            then public.events.image_url
                        else coalesce(:image_url, public.events.image_url)
                    end,
                    price_label = coalesce(public.events.price_label, :price_label),
                    is_free = case when :is_free then true else public.events.is_free end,
                    metadata = case
                        when public.events.metadata->>'imageSource' = 'supabase_storage'
                            then public.events.metadata || (cast(:metadata_json as jsonb) - 'imageSource' - 'imageUpdatedAt')
                        else public.events.metadata || cast(:metadata_json as jsonb)
                    end,
                    updated_at = now()
                where id = :id
                returning id::text as id
                """
            ),
            {
                "id": existing["id"],
                "description": event.get("description"),
                "image_url": event.get("imageUrl"),
                "price_label": event.get("priceLabel"),
                "is_free": bool(event.get("isFree", False)),
                "metadata_json": json.dumps(event.get("metadata") or {}),
            },
        )
        return {"id": existing["id"], "inserted": False}

    async def _upsert_venue(self, event: dict[str, Any]) -> dict[str, Any]:
        venue_name = str(event["venueName"]).strip()
        city = str(event["city"]).strip()
        slug = self._slugify(
            event.get("venueSlug") or f"{venue_name}-{city}-{event.get('venueAddress') or ''}"
        )
        result = await self.session.execute(
            text(
                """
                insert into public.venues (
                    name, slug, city, state, country, address, latitude, longitude, rating, review_count, booking_domain, metadata, created_at, updated_at
                )
                values (
                    :name, :slug, :city, :state, :country, :address, :latitude, :longitude, :rating, :review_count, :booking_domain, cast(:metadata_json as jsonb), now(), now()
                )
                on conflict (slug) do update
                set name = excluded.name,
                    city = excluded.city,
                    state = excluded.state,
                    country = excluded.country,
                    address = coalesce(excluded.address, public.venues.address),
                    latitude = coalesce(excluded.latitude, public.venues.latitude),
                    longitude = coalesce(excluded.longitude, public.venues.longitude),
                    rating = coalesce(excluded.rating, public.venues.rating),
                    review_count = coalesce(excluded.review_count, public.venues.review_count),
                    booking_domain = coalesce(excluded.booking_domain, public.venues.booking_domain),
                    metadata = public.venues.metadata || excluded.metadata,
                    updated_at = now()
                returning id::text as id, (xmax = 0) as inserted
                """
            ),
            {
                "name": venue_name,
                "slug": slug,
                "city": city,
                "state": event.get("state"),
                "country": event.get("country") or "US",
                "address": event.get("venueAddress"),
                "latitude": event.get("venueLatitude"),
                "longitude": event.get("venueLongitude"),
                "rating": event.get("venueRating"),
                "review_count": event.get("venueReviewCount"),
                "booking_domain": self._booking_domain(event["bookingUrl"]),
                "metadata_json": json.dumps(event.get("venueMetadata") or {}),
            },
        )
        row = result.mappings().one()
        return dict(row)

    async def _upsert_event(self, event: dict[str, Any], *, venue_id: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.events (
                    venue_id,
                    source_event_key,
                    title,
                    description,
                    category,
                    booking_url,
                    image_url,
                    price_label,
                    is_free,
                    dress_code,
                    crowd_age,
                    music_genre,
                    hidden,
                    verification_status,
                    verification_fail_count,
                    last_verified_at,
                    last_verified_active,
                    metadata,
                    created_at,
                    updated_at
                )
                values (
                    :venue_id,
                    :source_event_key,
                    :title,
                    :description,
                    :category,
                    :booking_url,
                    :image_url,
                    :price_label,
                    :is_free,
                    :dress_code,
                    :crowd_age,
                    :music_genre,
                    false,
                    'pending',
                    0,
                    null,
                    null,
                    cast(:metadata_json as jsonb),
                    now(),
                    now()
                )
                on conflict (booking_url) do update
                set venue_id = coalesce(excluded.venue_id, public.events.venue_id),
                    source_event_key = coalesce(excluded.source_event_key, public.events.source_event_key),
                    title = excluded.title,
                    description = coalesce(excluded.description, public.events.description),
                    category = excluded.category,
                    image_url = case
                        when public.events.metadata->>'imageSource' = 'supabase_storage'
                            then public.events.image_url
                        else coalesce(excluded.image_url, public.events.image_url)
                    end,
                    price_label = coalesce(excluded.price_label, public.events.price_label),
                    is_free = excluded.is_free,
                    dress_code = coalesce(excluded.dress_code, public.events.dress_code),
                    crowd_age = coalesce(excluded.crowd_age, public.events.crowd_age),
                    music_genre = coalesce(excluded.music_genre, public.events.music_genre),
                    metadata = case
                        when public.events.metadata->>'imageSource' = 'supabase_storage'
                            then public.events.metadata || (excluded.metadata - 'imageSource' - 'imageUpdatedAt')
                        else public.events.metadata || excluded.metadata
                    end,
                    updated_at = now()
                returning id::text as id, (xmax = 0) as inserted
                """
            ),
            {
                "venue_id": venue_id,
                "source_event_key": event.get("sourceEventKey"),
                "title": event["title"],
                "description": event.get("description"),
                "category": event.get("category") or "experiences",
                "booking_url": event["bookingUrl"],
                "image_url": event.get("imageUrl"),
                "price_label": event.get("priceLabel"),
                "is_free": bool(event.get("isFree", False)),
                "dress_code": event.get("dressCode"),
                "crowd_age": event.get("crowdAge"),
                "music_genre": event.get("musicGenre"),
                "metadata_json": json.dumps(event.get("metadata") or {}),
            },
        )
        row = result.mappings().one()
        return dict(row)

    async def _upsert_occurrence(self, event_id: str, event: dict[str, Any]) -> dict[str, Any]:
        starts_at = event["startsAt"]
        ends_at = event.get("endsAt")
        result = await self.session.execute(
            text(
                """
                insert into public.event_occurrences (
                    event_id,
                    starts_at,
                    ends_at,
                    timezone,
                    cancelled,
                    created_at,
                    updated_at
                )
                values (:event_id, :starts_at, :ends_at, :timezone, false, now(), now())
                on conflict (event_id, starts_at) do update
                set ends_at = coalesce(excluded.ends_at, public.event_occurrences.ends_at),
                    timezone = coalesce(excluded.timezone, public.event_occurrences.timezone),
                    cancelled = false,
                    updated_at = now()
                returning id::text as id, (xmax = 0) as inserted
                """
            ),
            {
                "event_id": event_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "timezone": event.get("timezone") or "UTC",
            },
        )
        row = result.mappings().one()
        return dict(row)

    async def _upsert_ticket_offers(self, event_id: str, event: dict[str, Any]) -> None:
        offers = event.get("ticketOffers") or []
        for sort_order, offer in enumerate(offers):
            if not isinstance(offer, dict):
                continue
            url = offer.get("url")
            if not url:
                continue
            await self.session.execute(
                text(
                    """
                    insert into public.ticket_offers (
                        event_id, provider, url, price_label, is_free, sort_order, created_at, updated_at
                    )
                    values (:event_id, :provider, :url, :price_label, :is_free, :sort_order, now(), now())
                    on conflict (event_id, url) do update
                    set provider = coalesce(excluded.provider, public.ticket_offers.provider),
                        price_label = coalesce(excluded.price_label, public.ticket_offers.price_label),
                        is_free = coalesce(excluded.is_free, public.ticket_offers.is_free),
                        sort_order = excluded.sort_order,
                        updated_at = now()
                    """
                ),
                {
                    "event_id": event_id,
                    "provider": offer.get("provider"),
                    "url": url,
                    "price_label": offer.get("priceLabel"),
                    "is_free": offer.get("isFree"),
                    "sort_order": sort_order,
                },
            )

    async def _upsert_tags(self, event_id: str, event: dict[str, Any]) -> None:
        vibes = [str(v).strip() for v in (event.get("vibes") or []) if str(v).strip()]
        tags = [str(t).strip() for t in (event.get("tags") or []) if str(t).strip()]

        for vibe in vibes:
            await self.session.execute(
                text(
                    """
                    insert into public.event_tags (event_id, tag, tag_type, score)
                    values (:event_id, :tag, 'vibe', null)
                    on conflict (event_id, tag, tag_type) do update set score = excluded.score
                    """
                ),
                {"event_id": event_id, "tag": vibe},
            )

        for tag in tags:
            await self.session.execute(
                text(
                    """
                    insert into public.event_tags (event_id, tag, tag_type, score)
                    values (:event_id, :tag, 'tag', null)
                    on conflict (event_id, tag, tag_type) do update set score = excluded.score
                    """
                ),
                {"event_id": event_id, "tag": tag},
            )

    def _normalize_event_payload(self, raw: dict[str, Any], *, default_city: str) -> dict[str, Any]:
        title = self._pick(raw, "title")
        booking_url = self._pick(raw, "bookingUrl", "booking_url", "url")
        starts_at_raw = self._pick(raw, "startsAt", "starts_at", default=None)
        if not title or not booking_url:
            raise ValueError("Manual ingest event requires `title` and `bookingUrl`")
        starts_at = self._coerce_datetime(starts_at_raw) if starts_at_raw else datetime.now(tz=UTC) + timedelta(hours=6)
        ends_at = self._coerce_datetime(self._pick(raw, "endsAt", "ends_at", default=None))

        venue_obj = raw.get("venue") if isinstance(raw.get("venue"), dict) else {}
        venue_name = self._pick(raw, "venueName", default=None) or self._pick(venue_obj, "name", default=None)
        if not venue_name:
            venue_name = f"{default_city} Spotlight"

        city = self._pick(raw, "city", default=None) or self._pick(venue_obj, "city", default=None) or default_city
        country = self._pick(raw, "country", default=None) or self._pick(venue_obj, "country", default=None) or "US"

        return {
            "title": str(title),
            "description": self._pick(raw, "description", default=None),
            "category": self._normalize_category(self._pick(raw, "category", default="experiences")),
            "bookingUrl": str(booking_url),
            "imageUrl": self._pick(raw, "imageUrl", "image_url", default=None),
            "priceLabel": self._pick(raw, "priceLabel", "price_label", default=None),
            "isFree": bool(self._pick(raw, "isFree", "is_free", default=False)),
            "startsAt": starts_at,
            "endsAt": ends_at,
            "timezone": self._pick(raw, "timezone", default="UTC"),
            "venueName": str(venue_name),
            "venueSlug": self._pick(raw, "venueSlug", default=None) or self._pick(venue_obj, "slug", default=None),
            "venueAddress": self._pick(raw, "venueAddress", default=None) or self._pick(venue_obj, "address", default=None),
            "venueLatitude": self._coerce_float(self._pick(raw, "venueLatitude", default=None) or self._pick(venue_obj, "latitude", default=None)),
            "venueLongitude": self._coerce_float(self._pick(raw, "venueLongitude", default=None) or self._pick(venue_obj, "longitude", default=None)),
            "city": str(city),
            "state": self._pick(raw, "state", default=None) or self._pick(venue_obj, "state", default=None),
            "country": str(country),
            "dressCode": self._pick(raw, "dressCode", "dress_code", default=None),
            "crowdAge": self._pick(raw, "crowdAge", "crowd_age", default=None),
            "musicGenre": self._pick(raw, "musicGenre", "music_genre", default=None),
            "sourceEventKey": self._pick(raw, "sourceEventKey", "source_event_key", default=None),
            "vibes": self._coerce_list(self._pick(raw, "vibes", default=[])),
            "tags": self._coerce_list(self._pick(raw, "tags", default=[])),
            "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
            "venueMetadata": venue_obj.get("metadata") if isinstance(venue_obj.get("metadata"), dict) else {},
            "venueRating": self._coerce_float(self._pick(raw, "venueRating", "venue_rating", default=None)),
            "venueReviewCount": self._pick(raw, "venueReviewCount", "venue_review_count", default=None),
            "ticketOffers": raw.get("ticketOffers") or [],
            "extraOccurrences": raw.get("extraOccurrences") or [],
        }

    @staticmethod
    def _pick(payload: Any, *keys: str, default: Any = None) -> Any:
        if not isinstance(payload, dict):
            return default
        for key in keys:
            if key in payload and payload[key] is not None:
                return payload[key]
        return default

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ValueError(f"Unsupported datetime value: {value!r}")

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, tuple):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        if slug:
            return slug[:120]
        return f"venue-{uuid5(NAMESPACE_URL, value)}"

    @staticmethod
    def _booking_domain(url: str) -> str | None:
        match = re.match(r"https?://([^/]+)", url)
        return match.group(1).lower() if match else None

    @staticmethod
    def _normalize_category(value: Any) -> str:
        if value is None:
            return "experiences"
        normalized = str(value).strip().lower()
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
