from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import AuthenticatedUser, require_admin_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.feed_assembly import FeedAssemblyService
from aventi_backend.db.session import get_db_session
from aventi_backend.db.user_identity import canonical_user_uuid
from aventi_backend.services.jobs import JobQueueRepository, JobType
from aventi_backend.services.market_inventory import MarketWarmupService
from aventi_backend.services.verification import VerificationService
from aventi_backend.worker import scheduler as scheduler_worker

router = APIRouter(dependencies=[Depends(require_admin_user)])
admin_user_dep = Depends(require_admin_user)
db_session_dep = Depends(get_db_session)
settings_dep = Depends(get_settings)


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _health_status(*, needs_attention: bool, has_data: bool, setup_needed: bool = False) -> str:
    if setup_needed:
        return "Setup needed"
    if needs_attention:
        return "Needs attention"
    if not has_data:
        return "No data yet"
    return "Healthy"


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
                   center_latitude, center_longitude,
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
            "centerLatitude": row["center_latitude"],
            "centerLongitude": row["center_longitude"],
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
    app_health = await _app_health_dashboard(session)
    worker_jobs = await _worker_jobs_dashboard(session)

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
        "workerJobs": worker_jobs,
        "appHealth": app_health,
    }


async def _app_health_dashboard(session: AsyncSession) -> dict:
    result = await session.execute(
        text(
            """
            select
              (select count(*)::int
               from public.events e
               join public.event_occurrences eo on eo.event_id = e.id
               where e.hidden = false
                 and eo.cancelled = false
                 and eo.starts_at >= now()
                 and eo.starts_at < now() + interval '7 days') as events_this_week,
              (select count(distinct e.id)::int
               from public.events e
               join public.event_occurrences eo on eo.event_id = e.id
               where eo.cancelled = false
                 and eo.starts_at >= now()) as upcoming_events,
              (select count(*)::int from public.market_inventory_state) as markets_total,
              (select count(*)::int
               from public.market_inventory_state
               where active_user_count_7d > 0 or heat_tier in ('hot', 'warm')) as active_markets,
              (select count(distinct user_id)::int
               from public.feed_impressions
               where served_at >= now() - interval '7 days') as active_users_7d,
              (select count(*)::int
               from public.feed_impressions
               where served_at >= now() - interval '7 days') as feed_views_7d,
              (select count(*)::int
               from public.favorites
               where created_at >= now() - interval '7 days') as saves_7d,
              (select count(*)::int
               from public.market_inventory_state
               where visible_event_count_7d = 0) as empty_markets,
              (select count(*)::int
               from public.events
               where hidden = true) as hidden_events,
              (select count(*)::int
               from public.events
               where image_url is null) as missing_images,
              (select count(*)::int
               from public.events
               where verification_status in ('pending', 'suspect', 'inactive')) as needs_attention,
              (select count(*)::int
               from public.event_reports
               where created_at >= now() - interval '30 days') as reported_events_30d,
              (select coalesce(sum(discovered_count), 0)::int
               from public.ingest_runs
               where started_at >= now() - interval '7 days') as events_found_7d,
              (select coalesce(sum(inserted_count), 0)::int
               from public.ingest_runs
               where started_at >= now() - interval '7 days') as events_inserted_7d,
              (select max(finished_at)
               from public.ingest_runs
               where status = 'done') as last_successful_import_at,
              (select max(finished_at)
               from public.ingest_runs
               where status = 'failed') as last_failed_import_at
            """
        )
    )
    row = result.mappings().one()
    events_this_week = int(row["events_this_week"] or 0)
    active_markets = int(row["active_markets"] or 0)
    empty_markets = int(row["empty_markets"] or 0)
    missing_images = int(row["missing_images"] or 0)
    needs_attention = int(row["needs_attention"] or 0)
    events_found_7d = int(row["events_found_7d"] or 0)
    feed_views_7d = int(row["feed_views_7d"] or 0)

    return {
        "summary": {
            "status": _health_status(
                needs_attention=empty_markets > 0 or needs_attention > 0,
                has_data=events_this_week > 0 or active_markets > 0,
            ),
            "eventsAvailableThisWeek": events_this_week,
            "upcomingEvents": row["upcoming_events"],
            "activeMarkets": active_markets,
            "activeUsers7d": row["active_users_7d"],
            "feedViews7d": feed_views_7d,
            "saves7d": row["saves_7d"],
        },
        "events": {
            "status": _health_status(
                needs_attention=missing_images > 0 or needs_attention > 0,
                has_data=events_this_week > 0,
            ),
            "hidden": row["hidden_events"],
            "missingImages": missing_images,
            "needsAttention": needs_attention,
            "reported30d": row["reported_events_30d"],
        },
        "discovery": {
            "status": _health_status(
                needs_attention=bool(row["last_failed_import_at"]),
                has_data=events_found_7d > 0,
            ),
            "eventsFound7d": events_found_7d,
            "eventsInserted7d": row["events_inserted_7d"],
            "lastSuccessfulImportAt": _iso(row["last_successful_import_at"]),
            "lastFailedImportAt": _iso(row["last_failed_import_at"]),
        },
        "people": {
            "status": _health_status(needs_attention=False, has_data=feed_views_7d > 0),
            "activeUsers7d": row["active_users_7d"],
            "feedViews7d": feed_views_7d,
            "saves7d": row["saves_7d"],
        },
        "attention": {
            "status": _health_status(
                needs_attention=empty_markets > 0 or needs_attention > 0 or missing_images > 0,
                has_data=active_markets > 0 or events_this_week > 0,
            ),
            "emptyMarkets": empty_markets,
            "eventsNeedingAttention": needs_attention,
            "missingImages": missing_images,
            "reportedEvents30d": row["reported_events_30d"],
        },
    }


async def _worker_jobs_dashboard(session: AsyncSession) -> dict:
    summary_result = await session.execute(
        text(
            """
            select
              count(*) filter (where status = 'queued')::int as queued,
              count(*) filter (where status = 'sent')::int as sent,
              count(*) filter (where status = 'processing')::int as processing,
              count(*) filter (
                where status = 'succeeded' and finished_at >= now() - interval '24 hours'
              )::int as succeeded_24h,
              count(*) filter (
                where status = 'failed' and finished_at >= now() - interval '24 hours'
              )::int as failed_24h,
              count(*) filter (where status = 'dead')::int as dead,
              min(queued_at) filter (where status in ('queued', 'sent')) as oldest_queued_at,
              max(finished_at) filter (where status = 'succeeded') as last_success_at,
              max(finished_at) filter (where status in ('failed', 'dead')) as last_failure_at
            from public.worker_jobs
            """
        )
    )
    summary_row = summary_result.mappings().one()

    by_type_result = await session.execute(
        text(
            """
            select
              job_type,
              count(*) filter (where status = 'queued')::int as queued,
              count(*) filter (where status = 'sent')::int as sent,
              count(*) filter (where status = 'processing')::int as processing,
              count(*) filter (
                where status = 'succeeded' and finished_at >= now() - interval '24 hours'
              )::int as succeeded_24h,
              count(*) filter (
                where status = 'failed' and finished_at >= now() - interval '24 hours'
              )::int as failed_24h,
              count(*) filter (where status = 'dead')::int as dead
            from public.worker_jobs
            where queued_at >= now() - interval '30 days'
               or status in ('queued', 'sent', 'processing', 'failed', 'dead')
            group by job_type
            order by dead desc, failed_24h desc, queued desc, processing desc, job_type
            limit 20
            """
        )
    )
    by_type = [
        {
            "jobType": row["job_type"],
            "queued": row["queued"],
            "sent": row["sent"],
            "processing": row["processing"],
            "succeeded24h": row["succeeded_24h"],
            "failed24h": row["failed_24h"],
            "dead": row["dead"],
        }
        for row in by_type_result.mappings().all()
    ]

    recent_result = await session.execute(
        text(
            """
            select id, job_type, status, market_key,
                   scheduler_run_id::text as scheduler_run_id,
                   ingest_run_id::text as ingest_run_id,
                   payload_summary, result,
                   attempts, max_attempts, queued_at, sent_at, started_at, finished_at,
                   last_error, run_id
            from public.worker_jobs
            order by
              case status
                when 'dead' then 0
                when 'failed' then 1
                when 'processing' then 2
                when 'queued' then 3
                when 'sent' then 4
                else 5
              end,
              coalesce(finished_at, started_at, sent_at, queued_at) desc
            limit 30
            """
        )
    )
    recent = [
        {
            "id": row["id"],
            "jobType": row["job_type"],
            "status": row["status"],
            "marketKey": row["market_key"],
            "schedulerRunId": row["scheduler_run_id"],
            "ingestRunId": row["ingest_run_id"],
            "payloadSummary": row["payload_summary"] or {},
            "result": row["result"] or {},
            "attempts": row["attempts"],
            "maxAttempts": row["max_attempts"],
            "queuedAt": _iso(row["queued_at"]),
            "sentAt": _iso(row["sent_at"]),
            "startedAt": _iso(row["started_at"]),
            "finishedAt": _iso(row["finished_at"]),
            "lastError": row["last_error"],
            "runId": row["run_id"],
        }
        for row in recent_result.mappings().all()
    ]

    return {
        "summary": {
            "queued": summary_row["queued"],
            "sent": summary_row["sent"],
            "processing": summary_row["processing"],
            "succeeded24h": summary_row["succeeded_24h"],
            "failed24h": summary_row["failed_24h"],
            "dead": summary_row["dead"],
            "oldestQueuedAt": _iso(summary_row["oldest_queued_at"]),
            "lastSuccessAt": _iso(summary_row["last_success_at"]),
            "lastFailureAt": _iso(summary_row["last_failure_at"]),
        },
        "byType": by_type,
        "recent": recent,
    }


class EnqueueMarketScanBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_key: str = Field(alias="marketKey")


class SmokeLimitBody(BaseModel):
    limit: int = Field(default=1, ge=1, le=5)


class FeedSmokeBody(BaseModel):
    market_key: str | None = Field(default=None, alias="marketKey")


class _FeedSmokeWarmupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def request_warmup(
        self,
        market: object,
        *,
        force_refresh: bool = False,
    ) -> tuple[str, str, bool]:
        market_key = getattr(market, "key", None) or "unknown"
        return str(market_key), "smoke_fetch_only", False


async def _remaining_free_swipes_for_smoke(
    user_id: str,
    settings: Settings,
    now: object,
) -> int | None:
    return None


def _pipeline_trace_steps(job: dict) -> list[dict]:
    status = str(job.get("status") or "")
    ingest_id = job.get("ingest_run_id")
    discovered = int(job.get("discovered_count") or 0)
    inserted = int(job.get("inserted_count") or 0)
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    ingest_result = result.get("ingest") if isinstance(result.get("ingest"), dict) else {}

    def state_for(step: str) -> str:
        if step == "Queued":
            return "complete" if status in {"sent", "processing", "succeeded"} else "current"
        if step == "Processing":
            if status == "processing":
                return "current"
            return "complete" if status == "succeeded" else "pending"
        if step == "Scan complete":
            if status == "succeeded":
                return "complete"
            return "failed" if status in {"failed", "dead"} else "pending"
        if step == "Ingest run created":
            return "complete" if ingest_id else "pending"
        if step == "Events discovered":
            return "complete" if discovered > 0 else "pending"
        if step == "Events inserted":
            return "complete" if inserted > 0 else "pending"
        if step == "Verification jobs queued":
            return "complete" if int(result.get("verificationJobsEnqueued") or 0) > 0 else "pending"
        if step == "Image jobs queued":
            enqueued = int(
                result.get("imageJobsEnqueued") or ingest_result.get("imageJobsEnqueued") or 0
            )
            return "complete" if enqueued > 0 else "pending"
        if step == "Feed inventory updated":
            return "complete" if status == "succeeded" else "pending"
        return "pending"

    return [
        {"label": label, "status": state_for(label)}
        for label in [
            "Queued",
            "Processing",
            "Scan complete",
            "Ingest run created",
            "Events discovered",
            "Events inserted",
            "Verification jobs queued",
            "Image jobs queued",
            "Feed inventory updated",
        ]
    ]


async def _recent_raw_errors(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        text(
            """
            select source, id, occurred_at, error
            from (
              select 'worker_job' as source, id, finished_at as occurred_at, last_error as error
              from public.worker_jobs
              where last_error is not null

              union all

              select 'ingest_run' as source, id::text, finished_at as occurred_at,
                     error_message as error
              from public.ingest_runs
              where error_message is not null
            ) errors
            order by occurred_at desc nulls last
            limit 25
            """
        )
    )
    return [
        {
            "source": row["source"],
            "id": row["id"],
            "occurredAt": _iso(row["occurred_at"]),
            "error": row["error"],
        }
        for row in result.mappings().all()
    ]


async def _retention_dashboard(session: AsyncSession) -> dict:
    result = await session.execute(
        text(
            """
            select
              (select count(*)::int
               from public.worker_jobs
               where status = 'succeeded'
                 and finished_at < now() - interval '30 days') as succeeded_jobs_eligible,
              (select count(*)::int
               from public.worker_jobs
               where status in ('failed', 'dead')
                 and finished_at < now() - interval '90 days') as failed_dead_jobs_eligible,
              (select count(*)::int
               from public.scheduler_runs
               where started_at < now() - interval '90 days') as scheduler_runs_eligible
            """
        )
    )
    row = result.mappings().one()
    return {
        "succeededJobsDays": 30,
        "failedDeadJobsDays": 90,
        "schedulerRunsDays": 90,
        "automaticCleanupEnabled": False,
        "candidates": {
            "succeededJobs": row["succeeded_jobs_eligible"],
            "failedDeadJobs": row["failed_dead_jobs_eligible"],
            "schedulerRuns": row["scheduler_runs_eligible"],
        },
    }


async def _create_admin_scheduler_run(
    session: AsyncSession,
    *,
    trigger_type: str,
    limit: int,
) -> str:
    return await scheduler_worker._create_scheduler_run(
        session,
        trigger_type=trigger_type,
        limit=limit,
    )


async def _mark_admin_scheduler_succeeded(
    session: AsyncSession,
    *,
    scheduler_run_id: str,
    result: dict,
) -> None:
    await scheduler_worker._mark_scheduler_run_succeeded(
        session,
        scheduler_run_id=scheduler_run_id,
        result=result,
    )


async def _mark_admin_scheduler_failed(
    session: AsyncSession,
    *,
    scheduler_run_id: str,
    error: str,
    result: dict | None = None,
) -> None:
    await scheduler_worker._mark_scheduler_run_failed(
        session,
        scheduler_run_id=scheduler_run_id,
        error=error,
        result=result,
    )


async def _scheduler_runs_dashboard(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        text(
            """
            select id::text as id, trigger_type, status, started_at, finished_at,
                   markets_considered, markets_enqueued, jobs_enqueued, "limit",
                   error, result
            from public.scheduler_runs
            order by started_at desc
            limit 20
            """
        )
    )
    scheduler_runs = []
    for row in result.mappings().all():
        jobs_result = await session.execute(
            text(
                """
                select wj.id, wj.job_type, wj.status, wj.market_key, wj.attempts,
                       wj.max_attempts, wj.queued_at, wj.started_at, wj.finished_at,
                       wj.payload_summary, wj.result,
                       wj.last_error, ir.id::text as ingest_run_id, ir.status as ingest_status,
                       ir.discovered_count, ir.inserted_count
                from public.worker_jobs wj
                left join public.ingest_runs ir on ir.job_id = wj.id
                where wj.scheduler_run_id = cast(:id as uuid)
                order by wj.queued_at asc
                limit 50
                """
            ),
            {"id": row["id"]},
        )
        jobs = [
            {
                "id": job["id"],
                "jobType": job["job_type"],
                "status": job["status"],
                "marketKey": job["market_key"],
                "attempts": job["attempts"],
                "maxAttempts": job["max_attempts"],
                "queuedAt": _iso(job["queued_at"]),
                "startedAt": _iso(job["started_at"]),
                "finishedAt": _iso(job["finished_at"]),
                "lastError": job["last_error"],
                "payloadSummary": job["payload_summary"] or {},
                "result": job["result"] or {},
                "ingestRunId": job["ingest_run_id"],
                "ingestStatus": job["ingest_status"],
                "discoveredCount": job["discovered_count"],
                "insertedCount": job["inserted_count"],
            }
            for job in jobs_result.mappings().all()
        ]
        for job in jobs:
            job["traceSteps"] = _pipeline_trace_steps(
                {
                    "status": job["status"],
                    "ingest_run_id": job["ingestRunId"],
                    "discovered_count": job["discoveredCount"],
                    "inserted_count": job["insertedCount"],
                    "result": job["result"],
                }
            )
        scheduler_runs.append(
            {
                "id": row["id"],
                "triggerType": row["trigger_type"],
                "status": row["status"],
                "startedAt": _iso(row["started_at"]),
                "finishedAt": _iso(row["finished_at"]),
                "marketsConsidered": row["markets_considered"],
                "marketsEnqueued": row["markets_enqueued"],
                "jobsEnqueued": row["jobs_enqueued"],
                "limit": row["limit"],
                "error": row["error"],
                "result": row["result"] or {},
                "jobs": jobs,
            }
        )
    return scheduler_runs


async def _queue_attributes(settings: Settings, queue_url: str | None) -> dict:
    if not queue_url:
        return {"configured": False, "reason": "Queue URL is not configured."}
    client_kwargs: dict[str, Any] = {
        "config": Config(connect_timeout=5, read_timeout=10),
    }
    if settings.aws_endpoint_url:
        client_kwargs["endpoint_url"] = settings.aws_endpoint_url
    try:
        client = boto3.client("sqs", **client_kwargs)
        response = await asyncio.to_thread(
            client.get_queue_attributes,
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateAgeOfOldestMessage",
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "reachable": False, "error": str(exc)}

    attrs = response.get("Attributes", {})
    return {
        "configured": True,
        "reachable": True,
        "approximateDepth": int(attrs.get("ApproximateNumberOfMessages", 0)),
        "approximateNotVisible": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
        "oldestMessageAgeSeconds": int(attrs.get("ApproximateAgeOfOldestMessage", 0)),
    }


async def _feed_diagnostic(session: AsyncSession, market_key: str) -> dict:
    result = await session.execute(
        text(
            """
            select
              mis.market_key, mis.city, mis.state, mis.country,
              mis.visible_event_count_7d, mis.active_user_count_7d,
              mis.last_scan_completed_at, mis.last_scan_succeeded_at, mis.last_error,
              (select count(*)::int
               from public.events e
               join public.venues v on v.id = e.venue_id
               join public.event_occurrences eo on eo.event_id = e.id
               where lower(v.city) = lower(mis.city)
                 and coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')
                 and lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))
                 and eo.cancelled = false
                 and eo.starts_at >= now()) as upcoming_occurrences,
              (select count(*)::int
               from public.events e
               join public.venues v on v.id = e.venue_id
               where lower(v.city) = lower(mis.city)
                 and coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')
                 and lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))
                 and e.hidden = true) as hidden_events,
              (select count(*)::int
               from public.events e
               join public.venues v on v.id = e.venue_id
               where lower(v.city) = lower(mis.city)
                 and coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')
                 and lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))
                 and e.verification_status = 'pending') as pending_verification,
              (select count(*)::int
               from public.events e
               join public.venues v on v.id = e.venue_id
               where lower(v.city) = lower(mis.city)
                 and coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')
                 and lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))
                 and e.verification_status in ('suspect', 'inactive')) as suspect_or_inactive,
              (select count(*)::int
               from public.events e
               join public.venues v on v.id = e.venue_id
               where lower(v.city) = lower(mis.city)
                 and coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')
                 and lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))
                 and e.image_url is null) as missing_images,
              (select max(finished_at)
               from public.ingest_runs
               where city = mis.city and status = 'done') as last_successful_scan,
              (select max(finished_at)
               from public.ingest_runs
               where city = mis.city and status = 'failed') as last_failed_scan
            from public.market_inventory_state mis
            where mis.market_key = :market_key
            """
        ),
        {"market_key": market_key},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown market_key: {market_key}")

    zero_filters = []
    if int(row["visible_event_count_7d"] or 0) == 0:
        zero_filters.append("This week")
    if int(row["missing_images"] or 0) > 0:
        zero_filters.append("Image-heavy views may look sparse")
    if int(row["pending_verification"] or 0) + int(row["suspect_or_inactive"] or 0) > 0:
        zero_filters.append("Strict verification filters")

    return {
        "marketKey": row["market_key"],
        "city": row["city"],
        "state": row["state"],
        "country": row["country"],
        "visibleEvents7d": row["visible_event_count_7d"],
        "upcomingOccurrences": row["upcoming_occurrences"],
        "hiddenEvents": row["hidden_events"],
        "pendingVerification": row["pending_verification"],
        "suspectOrInactive": row["suspect_or_inactive"],
        "missingImages": row["missing_images"],
        "lastSuccessfulScan": _iso(row["last_successful_scan"]),
        "lastFailedScan": _iso(row["last_failed_scan"]),
        "lastScanCompletedAt": _iso(row["last_scan_completed_at"]),
        "lastScanSucceededAt": _iso(row["last_scan_succeeded_at"]),
        "lastError": row["last_error"],
        "activeUsers": row["active_user_count_7d"],
        "filtersProducingZeroResults": zero_filters,
    }


@router.get("/system")
async def get_admin_system(
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
    settings: Settings = settings_dep,
) -> dict:
    worker_jobs = await _worker_jobs_dashboard(session)
    scheduler_runs = await _scheduler_runs_dashboard(session)
    raw_recent_errors = await _recent_raw_errors(session)
    retention = await _retention_dashboard(session)
    main_queue = await _queue_attributes(settings, settings.sqs_worker_queue_url)
    dlq = await _queue_attributes(settings, settings.sqs_worker_dlq_url)
    return {
        "workerJobs": worker_jobs,
        "schedulerRuns": scheduler_runs,
        "rawRecentErrors": raw_recent_errors,
        "queues": {"main": main_queue, "dlq": dlq},
        "eventBridge": {
            "configured": bool(settings.market_scan_cron_expression),
            "enabled": bool(settings.market_scan_cron_expression),
            "scheduleExpression": settings.market_scan_cron_expression,
            "lastRun": scheduler_runs[0] if scheduler_runs else None,
        },
        "providers": {
            "googleApiKeyConfigured": bool(settings.google_api_key),
            "serpApiKeyConfigured": bool(settings.serpapi_api_key),
            "pollinationsApiKeyConfigured": bool(settings.pollinations_api_key),
        },
        "retention": retention,
    }


@router.get("/markets/{market_key}/feed-diagnostic")
async def get_admin_market_feed_diagnostic(
    market_key: str,
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
) -> dict:
    return await _feed_diagnostic(session, market_key)


@router.post("/system/scheduler-runs/smoke")
async def post_admin_scheduler_smoke(
    body: SmokeLimitBody | None = None,
    _: AuthenticatedUser = admin_user_dep,
) -> dict:
    limit = body.limit if body else 1
    return await scheduler_worker._run(limit=limit, trigger_type="smoke")


@router.post("/system/verification/smoke")
async def post_admin_verification_smoke(
    body: SmokeLimitBody | None = None,
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
) -> dict:
    limit = body.limit if body else 5
    scheduler_run_id = await _create_admin_scheduler_run(
        session,
        trigger_type="smoke",
        limit=limit,
    )
    try:
        enqueued = await VerificationService(session).enqueue_verification_jobs(
            limit=limit,
            scheduler_run_id=scheduler_run_id,
        )
        result = {"jobs_enqueued": enqueued, "limit": limit}
        await _mark_admin_scheduler_succeeded(
            session,
            scheduler_run_id=scheduler_run_id,
            result=result,
        )
    except Exception as exc:  # noqa: BLE001
        await _mark_admin_scheduler_failed(
            session,
            scheduler_run_id=scheduler_run_id,
            error=str(exc),
        )
        raise
    return {"ok": True, "jobsEnqueued": enqueued, "schedulerRunId": scheduler_run_id}


@router.post("/system/images/smoke")
async def post_admin_image_smoke(
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
) -> dict:
    scheduler_run_id = await _create_admin_scheduler_run(
        session,
        trigger_type="smoke",
        limit=1,
    )
    event_id = await session.scalar(
        text(
            """
            select id::text
            from public.events
            where image_url is null
              and hidden = false
            order by updated_at desc
            limit 1
            """
        )
    )
    if not event_id:
        result = {"jobs_enqueued": 0, "reason": "No missing-image event found."}
        await _mark_admin_scheduler_succeeded(
            session,
            scheduler_run_id=scheduler_run_id,
            result=result,
        )
        return {
            "ok": True,
            "jobsEnqueued": 0,
            "reason": result["reason"],
            "schedulerRunId": scheduler_run_id,
        }
    try:
        job = await JobQueueRepository(session).enqueue_job(
            JobType.GENERATE_IMAGE,
            {"eventId": str(event_id)},
            scheduler_run_id=scheduler_run_id,
        )
        result = {"jobs_enqueued": 1, "eventId": str(event_id), "jobId": job.id}
        await _mark_admin_scheduler_succeeded(
            session,
            scheduler_run_id=scheduler_run_id,
            result=result,
        )
    except Exception as exc:  # noqa: BLE001
        await _mark_admin_scheduler_failed(
            session,
            scheduler_run_id=scheduler_run_id,
            error=str(exc),
        )
        raise
    return {
        "ok": True,
        "jobsEnqueued": 1,
        "jobId": job.id,
        "eventId": str(event_id),
        "schedulerRunId": scheduler_run_id,
    }


@router.post("/system/feed/smoke")
async def post_admin_feed_smoke(
    body: FeedSmokeBody | None = None,
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
    settings: Settings = settings_dep,
) -> dict:
    market_key = body.market_key if body else None
    scheduler_run_id = await _create_admin_scheduler_run(
        session,
        trigger_type="smoke",
        limit=1,
    )
    market_result = await session.execute(
        text(
            """
            select market_key, city, state, country, center_latitude, center_longitude
            from public.market_inventory_state
            where (:market_key is null or market_key = :market_key)
            order by active_user_count_7d desc, visible_event_count_7d desc, updated_at desc
            limit 1
            """
        ),
        {"market_key": market_key},
    )
    market = market_result.mappings().first()
    try:
        smoke_user_id = "admin-feed-smoke-user"
        feed = await FeedAssemblyService(
            session,
            remaining_free_swipes=_remaining_free_swipes_for_smoke,
            warmup_service_factory=_FeedSmokeWarmupService,
        ).get_feed(
            user_id=smoke_user_id,
            db_user_id=canonical_user_uuid(smoke_user_id),
            settings=settings,
            date="week",
            latitude=float(market["center_latitude"] or 30.2672) if market else 30.2672,
            longitude=float(market["center_longitude"] or -97.7431) if market else -97.7431,
            limit=10,
            time_of_day=None,
            price=None,
            radius_miles=None,
            selected_vibes=[],
            categories=[],
            cursor=None,
            market_city=str(market["city"]) if market else None,
            market_state=str(market["state"]) if market and market["state"] else None,
            market_country=str(market["country"]) if market else None,
            force_refresh=True,
        )
        result = {
            "feedItemsReturned": len(feed.get("items", [])),
            "hasMore": bool(feed.get("nextCursor")),
            "marketKey": market["market_key"] if market else None,
        }
        await _mark_admin_scheduler_succeeded(
            session,
            scheduler_run_id=scheduler_run_id,
            result=result,
        )
    except Exception as exc:  # noqa: BLE001
        await _mark_admin_scheduler_failed(
            session,
            scheduler_run_id=scheduler_run_id,
            error=str(exc),
        )
        raise
    return {
        "ok": True,
        "schedulerRunId": scheduler_run_id,
        "marketKey": result["marketKey"],
        "feedItemsReturned": result["feedItemsReturned"],
        "hasMore": result["hasMore"],
    }


@router.get("/user-locations")
async def get_admin_user_locations(
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
) -> dict:
    """Last synced device coordinates from ``profiles`` (mobile location gate). Admin-only."""
    result = await session.execute(
        text(
            """
            select id::text as user_id, city, latitude, longitude, updated_at
            from public.profiles
            where latitude is not null
              and longitude is not null
            order by updated_at desc nulls last
            limit 500
            """
        )
    )
    users = [
        {
            "userId": row["user_id"],
            "city": row["city"],
            "state": None,
            "country": None,
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "updatedAt": _iso(row["updated_at"]),
        }
        for row in result.mappings().all()
    ]
    return {"users": users}


@router.post("/import-markets-from-catalog")
async def post_admin_import_markets_from_catalog(
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
) -> dict:
    summary = await MarketWarmupService(session).sync_market_inventory_from_event_venues()
    return {"ok": True, **summary}


@router.post("/markets/enqueue-scan")
async def post_admin_markets_enqueue_scan(
    body: EnqueueMarketScanBody,
    _: AuthenticatedUser = admin_user_dep,
    session: AsyncSession = db_session_dep,
    settings: Settings = settings_dep,
) -> dict:
    if not settings.sqs_worker_queue_url:
        raise HTTPException(
            status_code=503,
            detail="Worker queue is not configured (SQS_WORKER_QUEUE_URL). Cannot enqueue scans.",
        )
    scheduler_run_id = await _create_admin_scheduler_run(
        session,
        trigger_type="admin",
        limit=1,
    )
    try:
        job = await MarketWarmupService(session).enqueue_admin_short_market_scan(
            body.market_key,
            scheduler_run_id=scheduler_run_id,
        )
        await _mark_admin_scheduler_succeeded(
            session,
            scheduler_run_id=scheduler_run_id,
            result={
                "markets": 1,
                "jobs_enqueued": 1,
                "marketKey": body.market_key,
                "jobId": job.id,
            },
        )
    except ValueError as exc:
        await _mark_admin_scheduler_failed(
            session,
            scheduler_run_id=scheduler_run_id,
            error=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        await _mark_admin_scheduler_failed(
            session,
            scheduler_run_id=scheduler_run_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "jobId": job.id,
        "marketKey": body.market_key,
        "schedulerRunId": scheduler_run_id,
    }
