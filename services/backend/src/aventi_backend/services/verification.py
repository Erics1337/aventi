from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.providers import MockVerifier, VerificationProvider
from aventi_backend.core.settings import get_settings

VERIFY_EVENT_COOLDOWN = timedelta(hours=6)


class VerificationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        verifier: VerificationProvider | None = None,
    ) -> None:
        self.session = session
        if verifier is None:
            settings = get_settings()
            if settings.google_api_key:
                from aventi_backend.services.gemini import GeminiVerifier
                self.verifier = GeminiVerifier()
            else:
                self.verifier = MockVerifier()
        else:
            self.verifier = verifier

    async def enqueue_verification_jobs(self, limit: int = 20, *, event_ids: list[str] | None = None) -> int:
        now = datetime.now(tz=UTC)
        ids = event_ids
        if ids is None:
            result = await self.session.execute(
                text(
                    """
                    select distinct e.id::text as event_id
                    from public.events e
                    join public.event_occurrences eo on eo.event_id = e.id
                    where e.hidden = false
                      and e.verification_status in ('pending', 'verified', 'suspect')
                      and eo.cancelled = false
                      and eo.starts_at >= now()
                      and (
                        e.last_verified_at is null
                        or e.last_verified_at <= :verify_cutoff
                      )
                    order by min(eo.starts_at) over (partition by e.id) asc
                    limit :limit_rows
                    """
                ),
                {"limit_rows": limit, "verify_cutoff": now - VERIFY_EVENT_COOLDOWN},
            )
            ids = [str(row[0]) for row in result.all()]
        else:
            ids = ids[:limit]

        repo = JobQueueRepository(self.session)
        count = 0
        for event_id in ids:
            latest_verification = await self.session.scalar(
                text(
                    """
                    select max(verified_at)
                    from public.verification_runs
                    where event_id = :event_id
                    """
                ),
                {"event_id": event_id},
            )
            if isinstance(latest_verification, datetime) and latest_verification >= now - VERIFY_EVENT_COOLDOWN:
                continue
            await repo.enqueue_job(JobType.VERIFY_EVENT, {"eventId": event_id})
            count += 1
        return count

    async def verify_event(self, event_id: str) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                """
                select id::text as id, booking_url, hidden, verification_status,
                       verification_fail_count, last_verified_at, last_verified_active
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
        verdict = await self.verifier.verify_booking_url(booking_url)
        verified_at = datetime.now(tz=UTC)
        if verdict is None:
            current_status = str(row["verification_status"] or "pending")
            await self.session.execute(
                text(
                    """
                    insert into public.verification_runs (event_id, status, verified_at, active, details)
                    values (:event_id, 'indeterminate', :verified_at, null, cast(:details_json as jsonb))
                    """
                ),
                {
                    "event_id": event_id,
                    "verified_at": verified_at,
                    "details_json": json.dumps(
                        {
                            "provider": self.verifier.__class__.__name__,
                            "bookingUrl": booking_url,
                            "reason": "indeterminate_verification_response",
                        }
                    ),
                },
            )
            await self.session.execute(
                text(
                    """
                    update public.events
                    set last_verified_at = :last_verified_at,
                        last_verified_active = null,
                        updated_at = now()
                    where id = :event_id
                    """
                ),
                {
                    "event_id": event_id,
                    "last_verified_at": verified_at,
                },
            )
            await self.session.commit()
            return {
                "eventId": event_id,
                "active": None,
                "status": current_status,
                "skipped": True,
            }

        is_active = bool(verdict)
        existing_fail_count = int(row["verification_fail_count"] or 0)
        last_verified_at = row.get("last_verified_at")
        last_verified_active = row.get("last_verified_active")
        recent_inactive_failure = (
            isinstance(last_verified_at, datetime)
            and last_verified_active is False
            and last_verified_at >= verified_at - timedelta(hours=24)
        )
        if is_active:
            status = "verified"
            next_fail_count = 0
        else:
            next_fail_count = existing_fail_count + 1 if recent_inactive_failure else 1
            status = "inactive" if next_fail_count >= 2 else "suspect"

        await self.session.execute(
            text(
                """
                insert into public.verification_runs (event_id, status, verified_at, active, details)
                values (:event_id, :status, :verified_at, :active, cast(:details_json as jsonb))
                """
            ),
            {
                "event_id": event_id,
                "status": status,
                "active": is_active,
                "verified_at": verified_at,
                "details_json": json.dumps(
                    {"provider": self.verifier.__class__.__name__, "bookingUrl": booking_url}
                ),
            },
        )
        await self.session.execute(
            text(
                """
                update public.events
                set verification_status = :verification_status,
                    verification_fail_count = :verification_fail_count,
                    last_verified_at = :last_verified_at,
                    last_verified_active = :last_verified_active,
                    updated_at = now(),
                    metadata = metadata || jsonb_build_object(
                      'verificationStatus',
                      cast(:metadata_status as text)
                    )
                where id = :event_id
                """
            ),
            {
                "event_id": event_id,
                "verification_status": status,
                "verification_fail_count": next_fail_count,
                "last_verified_at": verified_at,
                "last_verified_active": is_active,
                "metadata_status": status,
            },
        )

        await self.session.commit()
        return {"eventId": event_id, "active": is_active, "status": status}
