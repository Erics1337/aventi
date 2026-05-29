from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings
from aventi_backend.db.user_identity import (
    canonical_event_uuid,
    canonical_user_uuid,
    utc_day_bounds,
)
from aventi_backend.models.schemas import FeedImpressionPayload, SwipePayload
from aventi_backend.services.personalization import apply_vibe_update


class PreferenceActionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_premium(self, user_id: str) -> bool:
        db_user_id = canonical_user_uuid(user_id)
        result = await self.session.execute(
            text("select is_premium from public.premium_entitlements where user_id = :user_id"),
            {"user_id": db_user_id},
        )
        row = result.first()
        return bool(row[0]) if row else False

    async def count_swipes_today(self, user_id: str, now: datetime) -> int:
        db_user_id = canonical_user_uuid(user_id)
        start, end = utc_day_bounds(now)
        result = await self.session.execute(
            text(
                """
                select count(*)
                from public.swipe_actions
                where user_id = :user_id
                  and created_at >= :start_ts
                  and created_at < :end_ts
                """
            ),
            {"user_id": db_user_id, "start_ts": start, "end_ts": end},
        )
        return int(result.scalar_one())

    async def remaining_free_swipes(
        self,
        user_id: str,
        settings: Settings,
        now: datetime,
    ) -> int | None:
        if await self.is_premium(user_id):
            return None
        count = await self.count_swipes_today(user_id, now)
        return max(0, settings.free_swipe_limit - count)

    async def record_swipe(
        self,
        *,
        user_id: str,
        payload: SwipePayload,
        settings: Settings,
    ) -> dict[str, Any]:
        now = datetime.now(tz=UTC)
        remaining = await self.remaining_free_swipes(user_id, settings, now)
        if remaining is not None and remaining <= 0:
            raise PermissionError("Free preference action limit reached")

        db_user_id = canonical_user_uuid(user_id)
        event_uuid = canonical_event_uuid(payload.event_id)

        await self.session.execute(
            text(
                """
                insert into public.swipe_actions (
                    user_id, event_id, action, surfaced_at, position, market_key
                )
                select :user_id, :event_id, :action, :surfaced_at, :position,
                       lower(v.city) || '|' || lower(coalesce(v.state, '')) || '|' ||
                       lower(coalesce(v.country, 'us'))
                  from public.events e
                  join public.venues v on v.id = e.venue_id
                 where e.id = :event_id
                """
            ),
            {
                "user_id": db_user_id,
                "event_id": event_uuid,
                "action": payload.action,
                "surfaced_at": payload.surfaced_at,
                "position": payload.position,
            },
        )

        if payload.vibes:
            existing_result = await self.session.execute(
                text(
                    """
                    select vibe, weight
                    from public.user_vibe_weights
                    where user_id = :user_id
                      and vibe in :vibes
                    """
                ).bindparams(bindparam("vibes", expanding=True)),
                {"user_id": db_user_id, "vibes": list(payload.vibes)},
            )
            existing = {str(row[0]): float(row[1]) for row in existing_result.all()}
            updated = apply_vibe_update(existing, payload.vibes, payload.action)
            for vibe, weight in updated.items():
                await self.session.execute(
                    text(
                        """
                        insert into public.user_vibe_weights (user_id, vibe, weight, updated_at)
                        values (:user_id, :vibe, :weight, now())
                        on conflict (user_id, vibe) do update
                        set weight = excluded.weight,
                            updated_at = now()
                        """
                    ),
                    {"user_id": db_user_id, "vibe": vibe, "weight": weight},
                )

        await self.session.commit()
        remaining_after = await self.remaining_free_swipes(user_id, settings, now)
        return {
            "accepted": True,
            "remainingFreeSwipes": remaining_after,
            "remainingFreePreferenceActions": remaining_after,
        }

    async def record_feed_impression(
        self,
        *,
        user_id: str,
        payload: FeedImpressionPayload,
    ) -> dict[str, Any]:
        db_user_id = canonical_user_uuid(user_id)
        event_uuid = canonical_event_uuid(payload.event_id)
        await self.session.execute(
            text(
                """
                insert into public.feed_impressions (
                  user_id, event_id, served_at, position, affinity_score, filters, market_key
                )
                select :user_id, :event_id,
                       coalesce(:served_at, now()),
                       :position, :affinity_score, cast(:filters as jsonb),
                       lower(v.city) || '|' || lower(coalesce(v.state, '')) || '|' ||
                       lower(coalesce(v.country, 'us'))
                  from public.events e
                  join public.venues v on v.id = e.venue_id
                 where e.id = :event_id
                """
            ),
            {
                "user_id": db_user_id,
                "event_id": event_uuid,
                "served_at": payload.served_at,
                "position": payload.position,
                "affinity_score": payload.affinity_score,
                "filters": json.dumps(payload.filters or {}),
            },
        )
        await self.session.commit()
        return {"ok": True}
