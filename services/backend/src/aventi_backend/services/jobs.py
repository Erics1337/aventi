from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

import boto3
from botocore.exceptions import EndpointConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings

logger = logging.getLogger(__name__)


class JobType(StrEnum):
    HEALTH_CHECK = "HEALTH_CHECK"
    RETRY_ACCOUNT_DELETION = "RETRY_ACCOUNT_DELETION"
    RECONCILE_SUBSCRIPTION = "RECONCILE_SUBSCRIPTION"
    MARKET_WARMUP = "MARKET_WARMUP"
    MARKET_SCAN = "MARKET_SCAN"
    VERIFY_EVENT = "VERIFY_EVENT"
    ENRICH_EVENT = "ENRICH_EVENT"
    GENERATE_IMAGE = "GENERATE_IMAGE"
    GENERATE_INSIGHTS = "GENERATE_INSIGHTS"


@dataclass(slots=True)
class JobRecord:
    id: str
    type: JobType
    payload: dict[str, Any]
    run_at: datetime
    attempts: int = 0
    max_attempts: int = 5
    run_id: str | None = None
    locked_by: str | None = None
    status: str = "queued"


@dataclass(slots=True)
class JobClaim:
    outcome: Literal["claimed", "completed", "busy", "missing", "exhausted"]
    job: JobRecord | None = None


async def expire_exhausted_jobs(session: AsyncSession, job_id: str | None = None) -> None:
    await session.execute(
        text("""
            update public.jobs set status='dead', dedup_key=null, locked_by=null,
                lease_expires_at=null, completed_at=now(), updated_at=now(),
                last_error='Processing lease expired after final attempt'
            where attempts >= max_attempts
              and (cast(:job_id as text) is null or id=:job_id)
              and (status in ('queued', 'retry') or
                   (status='processing' and lease_expires_at <= now()))
        """),
        {"job_id": job_id},
    )
    await session.commit()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def default_dedup_key(job_type: JobType, payload: dict[str, Any]) -> str:
    """Return a stable active-job key without retaining user-controlled text."""
    identity: Any = payload
    if job_type in {JobType.VERIFY_EVENT, JobType.ENRICH_EVENT, JobType.GENERATE_IMAGE}:
        identity = {"eventId": payload.get("eventId")}
    elif job_type in {JobType.RETRY_ACCOUNT_DELETION, JobType.RECONCILE_SUBSCRIPTION}:
        identity = {"userId": payload.get("userId")}
    elif job_type == JobType.GENERATE_INSIGHTS:
        identity = {
            "eventId": payload.get("eventId"),
            "contextHash": payload.get("contextHash") or "default",
        }
    elif job_type == JobType.MARKET_WARMUP:
        identity = {
            "marketKey": payload.get("marketKey"),
            "force": bool(payload.get("forceDiscovery")),
        }
    digest = hashlib.sha256(_canonical_json([job_type.value, identity]).encode()).hexdigest()
    return f"{job_type.value.lower()}:{digest}"


class JobQueueRepository:
    """Transactional durable queue.

    ``enqueue_job`` deliberately does not commit or talk to SQS. The job and
    outbox row become visible together when the caller transaction commits.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue_job(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        *,
        run_at: datetime | None = None,
        max_attempts: int = 5,
        dedup_key: str | None = None,
    ) -> JobRecord:
        if not 1 <= max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        body = payload or {}
        serialized_body = _canonical_json(body)
        if len(serialized_body.encode()) > 200_000:
            raise ValueError("Job payload exceeds 200,000 bytes")
        scheduled_at = run_at or datetime.now(tz=UTC)
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=UTC)
        key = (
            None
            if job_type == JobType.HEALTH_CHECK
            else (dedup_key or default_dedup_key(job_type, body))
        )
        job_id = f"job-{uuid.uuid4()}"

        result = await self.session.execute(
            text(
                """
                insert into public.jobs (
                  id, job_type, payload, status, run_at, attempts, max_attempts,
                  dedup_key, created_at, updated_at
                ) values (
                  :id, :job_type, cast(:payload as jsonb), 'queued', :run_at, 0,
                  :max_attempts, :dedup_key, now(), now()
                )
                on conflict (dedup_key) where dedup_key is not null
                  and status in ('queued', 'processing', 'retry') do nothing
                returning id, job_type, payload, status, run_at, attempts, max_attempts,
                          locked_by
                """
            ),
            {
                "id": job_id,
                "job_type": job_type.value,
                "payload": serialized_body,
                "run_at": scheduled_at,
                "max_attempts": max_attempts,
                "dedup_key": key,
            },
        )
        row = result.mappings().first()
        if row is None:
            existing = await self.session.execute(
                text(
                    """
                    select id, job_type, payload, status, run_at, attempts,
                           max_attempts, locked_by
                    from public.jobs
                    where dedup_key = :dedup_key
                      and status in ('queued', 'processing', 'retry')
                    order by created_at desc
                    limit 1
                    """
                ),
                {"dedup_key": key},
            )
            row = existing.mappings().one()
        else:
            await self.session.execute(
                text(
                    """
                    insert into public.job_outbox (job_id, available_at, created_at)
                    values (:job_id, :available_at, now())
                    on conflict (job_id) do nothing
                    """
                ),
                {"job_id": row["id"], "available_at": scheduled_at},
            )
        return _record_from_row(row)

    async def claim_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 960,
    ) -> JobClaim:
        await expire_exhausted_jobs(self.session, job_id)
        now = datetime.now(tz=UTC)
        result = await self.session.execute(
            text(
                """
                update public.jobs
                set status = 'processing', attempts = attempts + 1,
                    locked_by = :worker_id,
                    lease_expires_at = :lease_expires_at,
                    started_at = coalesce(started_at, :now), updated_at = :now
                where id = :job_id
                  and attempts < max_attempts
                  and run_at <= :now
                  and (
                    status in ('queued', 'retry')
                    or (status = 'processing' and lease_expires_at <= :now)
                  )
                returning id, job_type, payload, status, run_at, attempts,
                          max_attempts, locked_by
                """
            ),
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "now": now,
                "lease_expires_at": now + timedelta(seconds=max(30, lease_seconds)),
            },
        )
        row = result.mappings().first()
        if row:
            await self.session.commit()
            return JobClaim("claimed", _record_from_row(row))

        state_result = await self.session.execute(
            text("select status, attempts, max_attempts from public.jobs where id = :job_id"),
            {"job_id": job_id},
        )
        state = state_result.mappings().first()
        await self.session.rollback()
        if state is None:
            return JobClaim("missing")
        if state["status"] in {"completed", "cancelled", "dead"}:
            if state["status"] == "completed":
                return JobClaim("completed")
            return JobClaim("exhausted")
        if int(state["attempts"]) >= int(state["max_attempts"]):
            return JobClaim("exhausted")
        return JobClaim("busy")

    async def complete_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        result: dict[str, Any] | None = None,
    ) -> bool:
        completed = await self.session.execute(
            text(
                """
                update public.jobs set status = 'completed', result = cast(:result as jsonb),
                    completed_at = now(), lease_expires_at = null, locked_by = null,
                    dedup_key = null, last_error = null, updated_at = now()
                where id = :job_id and status = 'processing' and locked_by = :worker_id
                returning id
                """
            ),
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "result": _canonical_json(result or {}),
            },
        )
        await self.session.commit()
        return completed.first() is not None

    async def fail_job(self, job_id: str, error: BaseException, *, worker_id: str) -> bool:
        """Record a fenced failure. Return whether this worker still owned the lease."""
        error_text = f"{type(error).__name__}: {error}"[:4000]
        result = await self.session.execute(
            text(
                """
                update public.jobs
                set status = case when attempts >= max_attempts then 'dead' else 'retry' end,
                    last_error = :error, lease_expires_at = null, locked_by = null,
                    dedup_key = case when attempts >= max_attempts then null else dedup_key end,
                    completed_at = case when attempts >= max_attempts then now() else completed_at end,
                    updated_at = now()
                where id = :job_id and status = 'processing' and locked_by = :worker_id
                returning status
                """
            ),
            {"job_id": job_id, "worker_id": worker_id, "error": error_text},
        )
        row = result.mappings().first()
        await self.session.commit()
        return row is not None


class OutboxPublisher:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish(self, *, limit: int = 100) -> dict[str, int]:
        settings = get_settings()
        if not settings.sqs_worker_queue_url:
            raise RuntimeError("SQS_WORKER_QUEUE_URL must be configured to publish jobs")
        kwargs: dict[str, str] = {}
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
        client = boto3.client("sqs", **kwargs)
        await expire_exhausted_jobs(self.session)
        rows_result = await self.session.execute(
            text(
                """
                select o.id, o.job_id, j.job_type, j.payload, j.max_attempts
                from public.job_outbox o join public.jobs j on j.id = o.job_id
                where (o.published_at is null or o.published_at <= now() - interval '15 minutes')
                  and o.available_at <= now()
                  and j.attempts < j.max_attempts
                  and (
                    j.status in ('queued', 'retry')
                    or (j.status = 'processing' and j.lease_expires_at <= now())
                  )
                order by o.available_at, o.id
                for update of o skip locked
                limit :limit_rows
                """
            ),
            {"limit_rows": max(1, min(limit, 500))},
        )
        rows = rows_result.mappings().all()
        published = 0
        for row in rows:
            body = {
                "format": "v2",
                "job_id": row["job_id"],
                "job_type": row["job_type"],
                "payload": row["payload"] or {},
                "max_attempts": row["max_attempts"],
            }
            try:
                response = await asyncio.to_thread(
                    client.send_message,
                    QueueUrl=settings.sqs_worker_queue_url,
                    MessageBody=_canonical_json(body),
                )
            except EndpointConnectionError as exc:
                await self.session.rollback()
                raise RuntimeError(
                    f"SQS endpoint unreachable ({settings.aws_endpoint_url})"
                ) from exc
            await self.session.execute(
                text(
                    """
                    update public.job_outbox
                    set published_at = now(), publish_attempts = publish_attempts + 1,
                        sqs_message_id = :message_id, last_error = null
                    where id = :id
                    """
                ),
                {"id": row["id"], "message_id": response.get("MessageId")},
            )
            published += 1
        await self.session.commit()
        return {"selected": len(rows), "published": published}


def _record_from_row(row: Any) -> JobRecord:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return JobRecord(
        id=str(row["id"]),
        type=JobType(row["job_type"]),
        payload=dict(payload or {}),
        status=str(row["status"]),
        run_at=row["run_at"],
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        locked_by=row.get("locked_by"),
    )


def worker_identity(prefix: str = "worker") -> str:
    return f"{prefix}@{socket.gethostname()}:{uuid.uuid4().hex[:10]}"


def build_manual_job(job_type: JobType, payload: dict[str, Any]) -> JobRecord:
    now = datetime.now(tz=UTC)
    return JobRecord(
        id=f"local-{job_type.lower()}-{int(now.timestamp())}",
        type=job_type,
        payload=payload,
        run_at=now,
    )
