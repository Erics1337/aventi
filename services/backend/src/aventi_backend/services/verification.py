from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.providers import MockVerifier, VerificationProvider


class VerificationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        verifier: VerificationProvider | None = None,
    ) -> None:
        self.session = session
        self.verifier = verifier or MockVerifier()

    async def enqueue_verification_jobs(self, limit: int = 20, *, event_ids: list[str] | None = None) -> int:
        ids = event_ids
        if ids is None:
            result = await self.session.execute(
                text(
                    """
                    select distinct e.id::text as event_id
                    from public.events e
                    join public.event_occurrences eo on eo.event_id = e.id
                    where e.hidden = false
                      and eo.cancelled = false
                      and eo.starts_at >= now()
                    order by min(eo.starts_at) over (partition by e.id) asc
                    limit :limit_rows
                    """
                ),
                {"limit_rows": limit},
            )
            ids = [str(row[0]) for row in result.all()]
        else:
            ids = ids[:limit]

        repo = JobQueueRepository(self.session)
        count = 0
        for event_id in ids:
            await repo.enqueue_job(JobType.VERIFY_EVENT, {"eventId": event_id})
            count += 1
        return count

    async def verify_event(self, event_id: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                select id::text as id, booking_url, hidden
                from public.events
                where id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        row = result.mappings().first()
        if not row:
            raise ValueError(f"Event not found for verification: {event_id}")

        booking_url = str(row["booking_url"])
        is_active = bool(await self.verifier.verify_booking_url(booking_url))
        status = "active" if is_active else "inactive"

        await self.session.execute(
            text(
                """
                insert into public.verification_runs (event_id, status, verified_at, active, details)
                values (:event_id, :status, now(), :active, cast(:details_json as jsonb))
                """
            ),
            {
                "event_id": event_id,
                "status": status,
                "active": is_active,
                "details_json": json.dumps(
                    {"provider": self.verifier.__class__.__name__, "bookingUrl": booking_url}
                ),
            },
        )
        if not is_active:
            await self.session.execute(
                text(
                    """
                    update public.events
                    set hidden = true,
                        updated_at = now(),
                        metadata = metadata || jsonb_build_object('verificationStatus', 'inactive')
                    where id = :event_id
                    """
                ),
                {"event_id": event_id},
            )
        else:
            await self.session.execute(
                text(
                    """
                    update public.events
                    set updated_at = now(),
                        metadata = metadata || jsonb_build_object('verificationStatus', 'active')
                    where id = :event_id
                    """
                ),
                {"event_id": event_id},
            )

        await self.session.commit()
        return {"eventId": event_id, "active": is_active, "status": status}
