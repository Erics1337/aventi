from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings
from aventi_backend.db.repository import PostgresAventiRepository
from aventi_backend.models.schemas import FeedImpressionPayload, SwipePayload
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobRecord
from aventi_backend.services.market_inventory import MarketDescriptor, MarketWarmupService

pytestmark = pytest.mark.integration


async def _cleanup_feed(
    session: AsyncSession,
    source_name: str,
    booking_prefix: str,
    user_id: str | list[str],
) -> None:
    user_ids = [user_id] if isinstance(user_id, str) else user_id
    for current_user_id in user_ids:
        await session.execute(
            text("delete from public.profiles where id = :user_id"),
            {"user_id": current_user_id},
        )
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


async def _feed_for_denver(
    repository: PostgresAventiRepository,
    *,
    user_id: str,
    settings: Settings,
) -> dict:
    return await repository.get_feed(
        user_id=user_id,
        settings=settings,
        date="week",
        latitude=39.7392,
        longitude=-104.9903,
        limit=10,
        time_of_day=None,
        price=None,
        radius_miles=5,
        selected_vibes=["social"],
        categories=["concerts"],
        cursor=None,
        market_city="Denver",
        market_state="CO",
        market_country="US",
    )


async def test_feed_repository_filters_saved_seen_items_and_updates_swipe_weights(
    db_session: AsyncSession,
    fake_job_queue: list[JobRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:feed:{suffix}"
    booking_prefix = f"https://tickets.example/{suffix}"
    user_id = str(uuid4())
    starts_at = datetime.now(tz=UTC) + timedelta(days=2)
    warmups: list[MarketDescriptor] = []

    async def fake_request_warmup(
        self: MarketWarmupService,
        market: MarketDescriptor,
        *,
        force_refresh: bool = False,
        visible_count: int | None = None,
    ) -> tuple[str, str, bool]:
        warmups.append(market)
        return market.key, "warming", True

    monkeypatch.setattr(MarketWarmupService, "request_warmup", fake_request_warmup)

    try:
        summary = await ManualIngestService(db_session).ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Feed Jazz One",
                    "bookingUrl": f"{booking_prefix}/one",
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Feed Venue",
                    "venueLatitude": 39.7392,
                    "venueLongitude": -104.9903,
                    "category": "concerts",
                    "vibes": ["social", "live-music"],
                    "tags": ["jazz"],
                },
                {
                    "title": "Integration Feed Jazz Two",
                    "bookingUrl": f"{booking_prefix}/two",
                    "startsAt": (starts_at + timedelta(hours=1)).isoformat(),
                    "venueName": "Integration Feed Venue",
                    "venueLatitude": 39.7392,
                    "venueLongitude": -104.9903,
                    "category": "concerts",
                    "vibes": ["social"],
                    "tags": ["jazz"],
                },
            ],
        )
        repository = PostgresAventiRepository(db_session)
        settings = Settings(AVENTI_FREE_SWIPE_LIMIT=10)

        feed = await repository.get_feed(
            user_id=user_id,
            settings=settings,
            date="week",
            latitude=39.7392,
            longitude=-104.9903,
            limit=10,
            time_of_day=None,
            price=None,
            radius_miles=5,
            selected_vibes=["social"],
            categories=["concerts"],
            cursor=None,
            market_city="Denver",
            market_state="CO",
            market_country="US",
        )

        assert {item["id"] for item in feed["items"]} == set(summary.event_ids)
        assert feed["warmupTriggered"] is False

        await repository.save_favorite(user_id, summary.event_ids[0])
        await repository.record_swipe(
            user_id=user_id,
            email=None,
            payload=SwipePayload(
                eventId=summary.event_ids[1],
                action="pass",
                surfacedAt=datetime.now(tz=UTC),
                position=1,
                vibes=["social"],
            ),
            settings=settings,
        )

        filtered_feed = await repository.get_feed(
            user_id=user_id,
            settings=settings,
            date="week",
            latitude=39.7392,
            longitude=-104.9903,
            limit=10,
            time_of_day=None,
            price=None,
            radius_miles=5,
            selected_vibes=["social"],
            categories=["concerts"],
            cursor=None,
            market_city="Denver",
            market_state="CO",
            market_country="US",
        )
        weight = (
            await db_session.execute(
                text(
                    """
                    select weight
                    from public.user_vibe_weights
                    where user_id = :user_id and vibe = 'social'
                    """
                ),
                {"user_id": user_id},
            )
        ).scalar_one()

        assert filtered_feed["items"] == []
        assert filtered_feed["warmupTriggered"] is True
        assert warmups and warmups[-1].key == "denver|co|us"
        assert float(weight) < 1

        await repository.report_event(
            user_id=user_id,
            event_id=summary.event_ids[0],
            reason="other",
            details="integration coverage",
        )
        entitlements = await repository.get_entitlements(user_id, None)
        assert entitlements.unlimited_swipes is False
    finally:
        await _cleanup_feed(db_session, source_name, booking_prefix, user_id)


async def test_feed_impressions_exclude_seen_until_reset(
    db_session: AsyncSession,
    fake_job_queue: list[JobRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:seen:{suffix}"
    booking_prefix = f"https://tickets.example/{suffix}"
    user_id = str(uuid4())
    starts_at = datetime.now(tz=UTC) + timedelta(days=2)

    async def fake_request_warmup(
        self: MarketWarmupService,
        market: MarketDescriptor,
        *,
        force_refresh: bool = False,
        visible_count: int | None = None,
    ) -> tuple[str, str, bool]:
        return market.key, "warming", False

    monkeypatch.setattr(MarketWarmupService, "request_warmup", fake_request_warmup)

    try:
        summary = await ManualIngestService(db_session).ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Seen Reset",
                    "bookingUrl": f"{booking_prefix}/seen",
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Seen Venue",
                    "venueLatitude": 39.7392,
                    "venueLongitude": -104.9903,
                    "category": "concerts",
                    "vibes": ["social"],
                    "tags": ["jazz"],
                }
            ],
        )
        repository = PostgresAventiRepository(db_session)
        settings = Settings(AVENTI_FREE_SWIPE_LIMIT=10)

        feed = await _feed_for_denver(repository, user_id=user_id, settings=settings)
        assert [item["id"] for item in feed["items"]] == summary.event_ids

        await repository.record_feed_impression(
            user_id=user_id,
            email=None,
            payload=FeedImpressionPayload(
                eventId=summary.event_ids[0],
                servedAt=datetime.now(tz=UTC),
                position=0,
                affinityScore=1.0,
                filters={"date": "week"},
            ),
        )
        seen_feed = await _feed_for_denver(repository, user_id=user_id, settings=settings)
        assert seen_feed["items"] == []

        reset = await repository.reset_seen_events(user_id)
        assert reset["deleted"] == 1

        restored_feed = await _feed_for_denver(repository, user_id=user_id, settings=settings)
        assert [item["id"] for item in restored_feed["items"]] == summary.event_ids
    finally:
        await _cleanup_feed(db_session, source_name, booking_prefix, user_id)


async def test_premium_entitlement_bypasses_free_swipe_limit(
    db_session: AsyncSession,
    fake_job_queue: list[JobRecord],
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:premium:{suffix}"
    booking_prefix = f"https://tickets.example/{suffix}"
    user_id = str(uuid4())
    starts_at = datetime.now(tz=UTC) + timedelta(days=2)

    try:
        summary = await ManualIngestService(db_session).ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Premium One",
                    "bookingUrl": f"{booking_prefix}/one",
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Premium Venue",
                    "category": "concerts",
                    "vibes": ["social"],
                },
                {
                    "title": "Integration Premium Two",
                    "bookingUrl": f"{booking_prefix}/two",
                    "startsAt": (starts_at + timedelta(hours=1)).isoformat(),
                    "venueName": "Integration Premium Venue",
                    "category": "concerts",
                    "vibes": ["social"],
                },
            ],
        )
        repository = PostgresAventiRepository(db_session)
        settings = Settings(AVENTI_FREE_SWIPE_LIMIT=1)

        first = await repository.record_swipe(
            user_id=user_id,
            email=None,
            payload=SwipePayload(
                eventId=summary.event_ids[0],
                action="pass",
                surfacedAt=datetime.now(tz=UTC),
                position=0,
                vibes=["social"],
            ),
            settings=settings,
        )
        assert first["remainingFreeSwipes"] == 0

        with pytest.raises(PermissionError):
            await repository.record_swipe(
                user_id=user_id,
                email=None,
                payload=SwipePayload(
                    eventId=summary.event_ids[1],
                    action="pass",
                    surfacedAt=datetime.now(tz=UTC),
                    position=1,
                    vibes=["social"],
                ),
                settings=settings,
            )

        await db_session.execute(
            text(
                """
                update public.premium_entitlements
                set is_premium = true, plan = 'integration'
                where user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        await db_session.commit()

        premium = await repository.record_swipe(
            user_id=user_id,
            email=None,
            payload=SwipePayload(
                eventId=summary.event_ids[1],
                action="pass",
                surfacedAt=datetime.now(tz=UTC),
                position=1,
                vibes=["social"],
            ),
            settings=settings,
        )
        assert premium["remainingFreeSwipes"] is None
    finally:
        await _cleanup_feed(db_session, source_name, booking_prefix, user_id)


async def test_report_threshold_hides_event_from_feed(
    db_session: AsyncSession,
    fake_job_queue: list[JobRecord],
) -> None:
    suffix = uuid4().hex
    source_name = f"integration:reports:{suffix}"
    booking_prefix = f"https://tickets.example/{suffix}"
    reporter_ids = [str(uuid4()) for _ in range(3)]
    viewer_id = str(uuid4())
    starts_at = datetime.now(tz=UTC) + timedelta(days=2)

    try:
        summary = await ManualIngestService(db_session).ingest_manual(
            source_name,
            "Denver",
            [
                {
                    "title": "Integration Reported Event",
                    "bookingUrl": f"{booking_prefix}/reported",
                    "startsAt": starts_at.isoformat(),
                    "venueName": "Integration Report Venue",
                    "venueLatitude": 39.7392,
                    "venueLongitude": -104.9903,
                    "category": "concerts",
                    "vibes": ["social"],
                }
            ],
        )
        repository = PostgresAventiRepository(db_session)
        settings = Settings(AVENTI_FREE_SWIPE_LIMIT=10)

        before = await _feed_for_denver(repository, user_id=viewer_id, settings=settings)
        assert [item["id"] for item in before["items"]] == summary.event_ids

        hidden = False
        for reporter_id in reporter_ids:
            report = await repository.report_event(
                user_id=reporter_id,
                event_id=summary.event_ids[0],
                reason="spam",
                details="integration threshold coverage",
            )
            hidden = bool(report["hidden"])

        assert hidden is True

        after = await _feed_for_denver(repository, user_id=viewer_id, settings=settings)
        assert after["items"] == []
    finally:
        await _cleanup_feed(
            db_session,
            source_name,
            booking_prefix,
            [*reporter_ids, viewer_id],
        )
