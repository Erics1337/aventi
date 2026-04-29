from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import AuthenticatedUser, require_admin_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.session import get_db_session

router = APIRouter(dependencies=[Depends(require_admin_user)])
admin_user_dep = Depends(require_admin_user)
db_session_dep = Depends(get_db_session)
settings_dep = Depends(get_settings)


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


@router.get("/dashboard")
async def get_admin_dashboard(
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
    settings: Settings = settings_dep,
) -> dict:
    market_result = await session.execute(
        text(
            """
            select market_key, city, state, country, heat_tier,
                   visible_event_count_7d, active_user_count_7d, active_user_count_14d,
                   last_requested_at, last_scan_requested_at, last_scan_started_at,
                   last_scan_completed_at, last_scan_succeeded_at, scan_lock_until,
                   last_targeted_requested_at, last_targeted_completed_at,
                   last_targeted_filter_signature, last_error, updated_at,
                   last_user_active_at
            from public.market_inventory_state
            order by case heat_tier when 'hot' then 0 when 'warm' then 1 else 2 end,
                     coalesce(last_user_active_at, last_requested_at, updated_at) desc
            limit 50
            """
        )
    )
    markets = [
        {
            "marketKey": row["market_key"],
            "city": row["city"],
            "state": row["state"],
            "country": row["country"],
            "heatTier": row["heat_tier"],
            "visibleEventCount7d": row["visible_event_count_7d"],
            "activeUserCount7d": row["active_user_count_7d"],
            "activeUserCount14d": row["active_user_count_14d"],
            "lastRequestedAt": _iso(row["last_requested_at"]),
            "lastScanRequestedAt": _iso(row["last_scan_requested_at"]),
            "lastScanStartedAt": _iso(row["last_scan_started_at"]),
            "lastScanCompletedAt": _iso(row["last_scan_completed_at"]),
            "lastScanSucceededAt": _iso(row["last_scan_succeeded_at"]),
            "scanLockUntil": _iso(row["scan_lock_until"]),
            "lastTargetedRequestedAt": _iso(row["last_targeted_requested_at"]),
            "lastTargetedCompletedAt": _iso(row["last_targeted_completed_at"]),
            "lastTargetedFilterSignature": row["last_targeted_filter_signature"],
            "lastError": row["last_error"],
            "updatedAt": _iso(row["updated_at"]),
        }
        for row in market_result.mappings().all()
    ]

    ingest_result = await session.execute(
        text(
            """
            select ir.id::text as id, ir.city, ir.status, ir.started_at, ir.finished_at,
                   ir.discovered_count, ir.inserted_count, ir.error_message, ir.metadata,
                   src.name as source_name, src.source_type
            from public.ingest_runs ir
            left join public.ingest_sources src on src.id = ir.source_id
            order by coalesce(ir.started_at, ir.created_at) desc
            limit 25
            """
        )
    )
    ingest_runs = [
        {
            "id": row["id"],
            "city": row["city"],
            "status": row["status"],
            "sourceName": row["source_name"],
            "sourceType": row["source_type"],
            "startedAt": _iso(row["started_at"]),
            "finishedAt": _iso(row["finished_at"]),
            "discoveredCount": row["discovered_count"],
            "insertedCount": row["inserted_count"],
            "errorMessage": row["error_message"],
            "metadata": row["metadata"] or {},
        }
        for row in ingest_result.mappings().all()
    ]

    verification_result = await session.execute(
        text(
            """
            select status, active, count(*)::int as count,
                   max(verified_at) as latest_verified_at
            from public.verification_runs
            where verified_at >= now() - interval '7 days'
            group by status, active
            order by count desc
            """
        )
    )
    verification = [
        {
            "status": row["status"],
            "active": row["active"],
            "count": row["count"],
            "latestVerifiedAt": _iso(row["latest_verified_at"]),
        }
        for row in verification_result.mappings().all()
    ]

    rollup_result = await session.execute(
        text(
            """
            select
              (
                select count(*)::int
                from public.market_inventory_state
              ) as markets_total,
              (
                select count(*)::int
                from public.market_inventory_state
                where heat_tier = 'hot'
              ) as hot_markets,
              (
                select count(*)::int
                from public.market_inventory_state
                where scan_lock_until > now()
              ) as active_scans,
              (
                select coalesce(sum(visible_event_count_7d), 0)::int
                from public.market_inventory_state
              ) as visible_events_7d,
              (
                select count(*)::int
                from public.ingest_runs
                where status = 'running'
              ) as running_ingests,
              (
                select count(*)::int
                from public.ingest_runs
                where status = 'failed'
              ) as failed_ingests,
              (
                select count(*)::int
                from public.events
                where verification_status in ('pending', 'suspect')
              ) as verification_backlog
            """
        )
    )
    rollup = dict(rollup_result.mappings().one())

    return {
        "rollup": {
            "marketsTotal": rollup["markets_total"],
            "hotMarkets": rollup["hot_markets"],
            "activeScans": rollup["active_scans"],
            "visibleEvents7d": rollup["visible_events_7d"],
            "runningIngests": rollup["running_ingests"],
            "failedIngests": rollup["failed_ingests"],
            "verificationBacklog": rollup["verification_backlog"],
        },
        "markets": markets,
        "ingestRuns": ingest_runs,
        "verification": verification,
        "workerQueue": {
            "configured": bool(settings.sqs_worker_queue_url),
            "pollSeconds": settings.worker_poll_seconds,
            "endpointUrl": settings.aws_endpoint_url,
        },
    }
