"""Weekly market-scan scheduler Lambda.

Invoked by an EventBridge cron (cron(0 9 ? * MON *)). Recomputes heat tiers
for every market, lists the hot + warm subset, and fans out one MARKET_SCAN
SQS job per (market, scan-window) pair. The existing worker Lambda consumes
those jobs via the normal SQS event source mapping.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.market_inventory import MarketWarmupService

logger = structlog.get_logger(__name__)

# Initialize logging during cold start (same pattern as worker/lambda_handler.py).
configure_logging(get_settings().log_level)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
WarmupServiceFactory = Callable[[AsyncSession], MarketWarmupService]


def _parse_limit(event: dict[str, Any]) -> int:
    limit_raw = event.get("limit")
    try:
        return int(limit_raw) if limit_raw is not None else 200
    except (TypeError, ValueError):
        return 200


def _parse_trigger_type(event: dict[str, Any]) -> str:
    trigger_type = str(event.get("triggerType") or event.get("trigger_type") or "cron")
    return trigger_type if trigger_type in {"cron", "admin", "smoke"} else "cron"


async def _create_scheduler_run(
    session: AsyncSession,
    *,
    trigger_type: str,
    limit: int,
) -> str:
    result = await session.execute(
        text(
            """
            insert into public.scheduler_runs (
              trigger_type, status, started_at, "limit"
            )
            values (:trigger_type, 'running', now(), :limit)
            returning id::text as id
            """
        ),
        {"trigger_type": trigger_type, "limit": limit},
    )
    await session.commit()
    return str(result.mappings().one()["id"])


async def _mark_scheduler_run_succeeded(
    session: AsyncSession,
    *,
    scheduler_run_id: str,
    result: dict[str, Any],
) -> None:
    await session.execute(
        text(
            """
            update public.scheduler_runs
            set status = 'succeeded',
                finished_at = now(),
                markets_considered = :markets_considered,
                markets_enqueued = :markets_enqueued,
                jobs_enqueued = :jobs_enqueued,
                result = cast(:result_json as jsonb)
            where id = cast(:id as uuid)
            """
        ),
        {
            "id": scheduler_run_id,
            "markets_considered": int(result.get("markets", 0) or result.get("requested", 0) or 0),
            "markets_enqueued": int(result.get("markets", 0) or result.get("triggered", 0) or 0),
            "jobs_enqueued": int(
                result.get("jobs_enqueued", 0) or result.get("jobsEnqueued", 0) or 0
            ),
            "result_json": json.dumps(result),
        },
    )
    await session.commit()


async def _mark_scheduler_run_failed(
    session: AsyncSession,
    *,
    scheduler_run_id: str,
    error: str,
    result: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            """
            update public.scheduler_runs
            set status = 'failed',
                finished_at = now(),
                error = :error,
                result = cast(:result_json as jsonb)
            where id = cast(:id as uuid)
            """
        ),
        {
            "id": scheduler_run_id,
            "error": error[:2000],
            "result_json": json.dumps(result or {}),
        },
    )
    await session.commit()


async def _run(
    limit: int,
    *,
    trigger_type: str = "cron",
    session_factory: SessionFactory = open_db_session,
    warmup_service_factory: WarmupServiceFactory = MarketWarmupService,
) -> dict[str, Any]:
    async with session_factory() as session:
        scheduler_run_id = await _create_scheduler_run(
            session,
            trigger_type=trigger_type,
            limit=limit,
        )
        try:
            service = warmup_service_factory(session)
            result = await service.enqueue_weekly_scans(
                limit=limit,
                scheduler_run_id=scheduler_run_id,
            )
            await _mark_scheduler_run_succeeded(
                session,
                scheduler_run_id=scheduler_run_id,
                result=result,
            )
        except Exception as exc:  # noqa: BLE001
            await _mark_scheduler_run_failed(
                session,
                scheduler_run_id=scheduler_run_id,
                error=str(exc),
            )
            raise
    logger.info("scheduler.fanout.complete", **result)
    return {**result, "schedulerRunId": scheduler_run_id, "status": "ok"}


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Lambda entry point for EventBridge weekly trigger."""
    event = event or {}
    limit = _parse_limit(event)
    trigger_type = _parse_trigger_type(event)
    logger.info("scheduler.invoked", limit=limit, trigger_type=trigger_type)
    return asyncio.run(_run(limit=limit, trigger_type=trigger_type))
