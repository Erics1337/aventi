from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.event_intake import (
    attach_image_metadata,
    booking_domain,
    coerce_datetime,
    slugify,
)


class IngestRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_ingest_source(self, source_name: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.ingest_sources (
                    name, source_type, enabled, created_at, updated_at
                )
                values (:name, 'manual', true, now(), now())
                on conflict (name) do update
                set updated_at = now()
                returning id::text as id, name
                """
            ),
            {"name": source_name},
        )
        row = result.mappings().one()
        return dict(row)

    async def create_ingest_run(
        self,
        *,
        source_id: str,
        city: str,
        discovered_count: int,
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
        return dict(row)

    async def mark_done(
        self,
        *,
        ingest_run_id: str,
        discovered_count: int,
        inserted_count: int,
        metadata: dict[str, Any],
    ) -> None:
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
                "ingest_run_id": ingest_run_id,
                "discovered_count": discovered_count,
                "inserted_count": inserted_count,
                "metadata_json": json.dumps(metadata),
            },
        )

    async def mark_failed(
        self,
        *,
        ingest_run_id: str,
        error_message: str,
        discovered_count: int,
        inserted_count: int,
    ) -> None:
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
                "ingest_run_id": ingest_run_id,
                "error_message": error_message[:2000],
                "discovered_count": discovered_count,
                "inserted_count": inserted_count,
            },
        )


class EventBundlePersistence:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_event_bundle(self, event: dict[str, Any]) -> dict[str, Any]:
        event = attach_image_metadata(event)
        venue = await self.upsert_venue(event)

        fuzzy_match = await self.find_fuzzy_duplicate(
            venue_id=venue["id"],
            title=str(event["title"]),
            starts_at=event["startsAt"],
            incoming_booking_url=str(event["bookingUrl"]),
        )
        near_duplicate = 0
        if fuzzy_match is not None:
            event_row = await self.merge_into_existing(fuzzy_match, event)
            near_duplicate = 1
        else:
            event_row = await self.upsert_event(event, venue_id=venue["id"])
        occurrence_row = await self.upsert_occurrence(event_row["id"], event)
        await self.upsert_tags(event_row["id"], event)
        await self.upsert_ticket_offers(event_row["id"], event)

        extra_inserted = 0
        for extra in (event.get("extraOccurrences") or []):
            if not isinstance(extra, dict):
                continue
            extra_starts_at = coerce_datetime(extra.get("startsAt"))
            extra_ends_at = coerce_datetime(extra.get("endsAt"))
            if extra_starts_at is None:
                continue
            extra_row = await self.upsert_occurrence(
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

    async def fetch_event_image_state(self, event_id: str) -> dict[str, Any]:
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

    async def find_fuzzy_duplicate(
        self,
        *,
        venue_id: str,
        title: str,
        starts_at: Any,
        incoming_booking_url: str,
    ) -> dict[str, Any] | None:
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
                  and similarity(
                    e.normalized_title,
                    lower(regexp_replace(:incoming_title, '\\s+', ' ', 'g'))
                  ) >= 0.85
                  and date_trunc('day', eo.starts_at) =
                    date_trunc('day', cast(:starts_at as timestamptz))
                order by similarity(
                    e.normalized_title,
                    lower(regexp_replace(:incoming_title, '\\s+', ' ', 'g'))
                ) desc
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

    async def merge_into_existing(
        self,
        existing: dict[str, Any],
        event: dict[str, Any],
    ) -> dict[str, Any]:
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
                            then public.events.metadata ||
                              (cast(:metadata_json as jsonb) - 'imageSource' - 'imageUpdatedAt')
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

    async def upsert_venue(self, event: dict[str, Any]) -> dict[str, Any]:
        venue_name = str(event["venueName"]).strip()
        city = str(event["city"]).strip()
        slug_source = event.get("venueSlug") or (
            f"{venue_name}-{city}-{event.get('venueAddress') or ''}"
        )
        slug = slugify(slug_source)
        result = await self.session.execute(
            text(
                """
                insert into public.venues (
                    name, slug, city, state, country, address, latitude, longitude,
                    rating, review_count, booking_domain, metadata, created_at, updated_at
                )
                values (
                    :name, :slug, :city, :state, :country, :address, :latitude, :longitude,
                    :rating, :review_count, :booking_domain, cast(:metadata_json as jsonb),
                    now(), now()
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
                    booking_domain = coalesce(
                      excluded.booking_domain,
                      public.venues.booking_domain
                    ),
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
                "booking_domain": booking_domain(event["bookingUrl"]),
                "metadata_json": json.dumps(event.get("venueMetadata") or {}),
            },
        )
        row = result.mappings().one()
        return dict(row)

    async def upsert_event(self, event: dict[str, Any], *, venue_id: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.events (
                    venue_id, source_event_key, title, description, category, booking_url,
                    image_url, price_label, is_free, dress_code, crowd_age, music_genre,
                    hidden, verification_status, verification_fail_count, last_verified_at,
                    last_verified_active, metadata, created_at, updated_at
                )
                values (
                    :venue_id, :source_event_key, :title, :description, :category, :booking_url,
                    :image_url, :price_label, :is_free, :dress_code, :crowd_age, :music_genre,
                    false, 'pending', 0, null, null, cast(:metadata_json as jsonb), now(), now()
                )
                on conflict (booking_url) do update
                set venue_id = coalesce(excluded.venue_id, public.events.venue_id),
                    source_event_key = coalesce(
                      excluded.source_event_key,
                      public.events.source_event_key
                    ),
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
                            then public.events.metadata ||
                              (excluded.metadata - 'imageSource' - 'imageUpdatedAt')
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

    async def upsert_occurrence(self, event_id: str, event: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                insert into public.event_occurrences (
                    event_id, starts_at, ends_at, timezone, cancelled, created_at, updated_at
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
                "starts_at": event["startsAt"],
                "ends_at": event.get("endsAt"),
                "timezone": event.get("timezone") or "UTC",
            },
        )
        row = result.mappings().one()
        return dict(row)

    async def upsert_ticket_offers(self, event_id: str, event: dict[str, Any]) -> None:
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
                        event_id, provider, url, price_label, is_free, sort_order,
                        created_at, updated_at
                    )
                    values (
                        :event_id, :provider, :url, :price_label, :is_free, :sort_order,
                        now(), now()
                    )
                    on conflict (event_id, url) do update
                    set provider = coalesce(excluded.provider, public.ticket_offers.provider),
                        price_label = coalesce(
                          excluded.price_label,
                          public.ticket_offers.price_label
                        ),
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

    async def upsert_tags(self, event_id: str, event: dict[str, Any]) -> None:
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
