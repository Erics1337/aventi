"""EventBridge entry point for weekly scans and minute maintenance."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import text

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.budgets import BudgetManager
from aventi_backend.services.jobs import JobQueueRepository, JobType, OutboxPublisher
from aventi_backend.services.market_inventory import MarketWarmupService
from aventi_backend.services.verification import VerificationService

logger = structlog.get_logger(__name__)
configure_logging(get_settings().log_level)


async def _run(limit: int, *, mode: str = "weekly") -> dict[str, Any]:
    async with open_db_session() as session:
        if mode == "maintenance":
            durable_maintenance = await _enqueue_durable_maintenance(session, limit=limit)
            verification_capacity = await BudgetManager(session).remaining("gemini")
            verification_enqueued = 0
            if verification_capacity:
                verification_enqueued = await VerificationService(
                    session
                ).enqueue_verification_jobs(limit=min(limit, 100, verification_capacity))
                await session.commit()
            else:
                await session.commit()
            outbox = await OutboxPublisher(session).publish(limit=limit)
            result: dict[str, Any] = {
                **durable_maintenance,
                "verificationJobsEnqueued": verification_enqueued,
                "outbox": outbox,
            }
        elif await BudgetManager(session).remaining("serpapi"):
            result = await MarketWarmupService(session).enqueue_weekly_scans(limit=limit)
            await session.commit()
        else:
            result = {"marketsQueued": 0, "budgetPaused": True}
    logger.info("scheduler.complete", mode=mode, **result)
    return {**result, "mode": mode, "status": "ok"}


async def _enqueue_durable_maintenance(session, *, limit: int) -> dict[str, int]:
    await session.execute(text("delete from public.feed_sessions where expires_at < now()"))
    await session.execute(text("delete from public.request_limits where window_start < now() - interval '1 day'"))
    repo = JobQueueRepository(session)
    deletion_rows = await session.execute(
        text(
            """
            select d.user_id::text as user_id
            from public.account_deletions d
            where d.status in ('pending', 'failed', 'processing')
              and d.updated_at <= now() - interval '15 minutes'
              and not exists (
                select 1 from public.jobs j
                where j.job_type = 'RETRY_ACCOUNT_DELETION'
                  and j.payload ->> 'userId' = d.user_id::text
                  and j.created_at >= now() - interval '1 hour'
              )
            order by d.updated_at
            limit :limit_rows
            """
        ),
        {"limit_rows": min(limit, 100)},
    )
    deletions = [str(row[0]) for row in deletion_rows.all()]
    for user_id in deletions:
        await repo.enqueue_job(JobType.RETRY_ACCOUNT_DELETION, {"userId": user_id})

    subscription_rows = await session.execute(
        text(
            """
            select p.user_id::text as user_id
            from public.premium_entitlements p
            join public.subscription_accounts a on a.user_id = p.user_id
              and a.revenuecat_app_user_id = p.user_id::text
              and a.original_app_user_id = p.user_id::text
            where p.is_premium is true
              and p.valid_until is not null
              and (p.valid_until <= now() + interval '24 hours' or p.updated_at <= now() - interval '6 hours')
              and not exists (
                select 1 from public.jobs j
                where j.job_type = 'RECONCILE_SUBSCRIPTION'
                  and j.payload ->> 'userId' = p.user_id::text
                  and j.created_at >= now() - interval '1 hour'
              )
            order by p.valid_until
            limit :limit_rows
            """
        ),
        {"limit_rows": min(limit, 100)},
    )
    subscriptions = [str(row[0]) for row in subscription_rows.all()]
    for user_id in subscriptions:
        await repo.enqueue_job(JobType.RECONCILE_SUBSCRIPTION, {"userId": user_id})
    return {
        "accountDeletionJobsEnqueued": len(deletions),
        "subscriptionJobsEnqueued": len(subscriptions),
    }


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    try:
        limit = int(event.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    mode = str(event.get("mode") or "weekly").lower()
    if mode not in {"weekly", "maintenance"}:
        raise ValueError("scheduler mode must be weekly or maintenance")
    logger.info("scheduler.invoked", limit=limit, mode=mode)
    return asyncio.run(_run(limit=max(1, min(limit, 500)), mode=mode))
