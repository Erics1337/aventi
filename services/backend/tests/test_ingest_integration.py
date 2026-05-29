from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.ingest import ManualIngestService

pytestmark = pytest.mark.integration


async def _cleanup_ingest(session: AsyncSession, source_name: str, booking_prefix: str) -> None:
    await session.execute(
        text("delete from public.events where booking_url like :prefix"),
        {"prefix": f"{booking_prefix}%"},
    )
    await session.execute(
        text(
            """
            delete from public.ingest_runs
            where source_id in (select id from public.ingest_sources where name = :source_name)
            """
        ),
        {"source_name": source_name},
    )
    await session.execute(
        text("delete from public.ingest_sources where name = :source_name"),
        {"source_name": source_name},
    )
    await session.commit()


async def test_manual_ingest_persists_bundle_and_dedupes_booking_url(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:ingest:{suffix}"
    booking_url = f"https://tickets.example/{suffix}/jazz"
    starts_at = datetime.now(tz=UTC) + timedelta(days=2)

    try:
        service = ManualIngestService(db_session)
        first = await service.ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Jazz Night",
                    "bookingUrl": booking_url,
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Blue Room",
                    "venueLatitude": 39.7392,
                    "venueLongitude": -104.9903,
                    "category": "live music",
                    "vibes": ["social", "live-music"],
                    "tags": ["jazz"],
                    "ticketOffers": [
                        {
                            "url": f"{booking_url}/vip",
                            "provider": "venue",
                            "priceLabel": "$25",
                            "isFree": False,
                        }
                    ],
                    "extraOccurrences": [
                        {
                            "startsAt": (starts_at + timedelta(days=1)).isoformat(),
                            "endsAt": (starts_at + timedelta(days=1, hours=2)).isoformat(),
                        }
                    ],
                }
            ],
        )
        second = await service.ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Jazz Night Updated",
                    "bookingUrl": booking_url,
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Blue Room",
                    "category": "concerts",
                    "vibes": ["social"],
                }
            ],
        )

        assert first.inserted_events == 1
        assert second.inserted_events == 0
        assert second.updated_events == 1
        assert first.event_ids == second.event_ids

        counts = (
            await db_session.execute(
                text(
                    """
                    select
                      (
                        select count(*)
                        from public.events
                        where booking_url = :booking_url
                      ) as events,
                      (
                        select count(*)
                        from public.event_occurrences
                        where event_id = :event_id
                      ) as occurrences,
                      (select count(*) from public.event_tags where event_id = :event_id) as tags,
                      (
                        select count(*)
                        from public.ticket_offers
                        where event_id = :event_id
                      ) as ticket_offers,
                      (
                        select metadata->>'imageJobsEnqueued'
                        from public.ingest_runs
                        where id = :ingest_run_id
                      ) as image_jobs_enqueued
                    """
                ),
                {
                    "booking_url": booking_url,
                    "event_id": first.event_ids[0],
                    "ingest_run_id": first.ingest_run_id,
                },
            )
        ).mappings().one()

        assert counts["events"] == 1
        assert counts["occurrences"] == 2
        assert counts["tags"] >= 2
        assert counts["ticket_offers"] == 1
        assert counts["image_jobs_enqueued"] == "0"
    finally:
        await _cleanup_ingest(db_session, source_name, f"https://tickets.example/{suffix}")


async def test_manual_ingest_merges_fuzzy_duplicate_same_venue_and_day(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:fuzzy:{suffix}"
    booking_prefix = f"https://tickets.example/{suffix}"
    starts_at = datetime.now(tz=UTC) + timedelta(days=3)

    try:
        summary = await ManualIngestService(db_session).ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Rooftop Jazz Night",
                    "bookingUrl": f"{booking_prefix}/venue",
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Duplicate Room",
                    "category": "concerts",
                },
                {
                    "title": "Integration Rooftop Jazz Night!",
                    "bookingUrl": f"{booking_prefix}/ticketing",
                    "startsAt": (starts_at + timedelta(minutes=30)).isoformat(),
                    "venueName": "Integration Duplicate Room",
                    "category": "concerts",
                },
            ],
        )

        run_metadata = (
            await db_session.execute(
                text("select metadata from public.ingest_runs where id = :id"),
                {"id": summary.ingest_run_id},
            )
        ).scalar_one()

        assert summary.inserted_events == 1
        assert run_metadata["nearDuplicatesSkipped"] == 1
    finally:
        await _cleanup_ingest(db_session, source_name, booking_prefix)
