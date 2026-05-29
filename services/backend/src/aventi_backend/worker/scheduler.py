"""Weekly market-scan scheduler Lambda.

Invoked by an EventBridge cron (cron(0 9 ? * MON *)). Recomputes heat tiers
for every market, lists the hot + warm subset, and fans out one MARKET_SCAN
SQS job per (market, scan-window) pair. The existing worker Lambda consumes
those jobs via the normal SQS event source mapping.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import structlog
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


async def _run(
    limit: int,
    *,
    session_factory: SessionFactory = open_db_session,
    warmup_service_factory: WarmupServiceFactory = MarketWarmupService,
) -> dict[str, Any]:
    async with session_factory() as session:
        service = warmup_service_factory(session)
        result = await service.enqueue_weekly_scans(limit=limit)
    logger.info("scheduler.fanout.complete", **result)
    return {**result, "status": "ok"}


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Lambda entry point for EventBridge weekly trigger."""
    event = event or {}
    limit = _parse_limit(event)
    logger.info("scheduler.invoked", limit=limit)
    return asyncio.run(_run(limit=limit))
