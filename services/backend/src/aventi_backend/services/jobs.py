from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import boto3
from botocore.exceptions import EndpointConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import get_settings


class JobType(StrEnum):
    MARKET_WARMUP = "MARKET_WARMUP"
    MARKET_SCAN = "MARKET_SCAN"
    VERIFY_EVENT = "VERIFY_EVENT"
    ENRICH_EVENT = "ENRICH_EVENT"
    GENERATE_IMAGE = "GENERATE_IMAGE"


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
    scheduler_run_id: str | None = None


class JobQueueRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ledger_session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
        | None = None,
    ) -> None:
        self.session = session
        self.ledger_session_factory = ledger_session_factory

    async def enqueue_job(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        *,
        run_at: datetime | None = None,
        max_attempts: int = 5,
        scheduler_run_id: str | None = None,
    ) -> JobRecord:
        settings = get_settings()

        if not settings.sqs_worker_queue_url:
            raise RuntimeError("SQS_WORKER_QUEUE_URL must be configured to enqueue jobs.")

        job_id = f"job-{uuid.uuid4()}"
        client_kwargs = {}
        if settings.aws_endpoint_url:
            client_kwargs["endpoint_url"] = settings.aws_endpoint_url
        sqs_client = boto3.client("sqs", **client_kwargs)
        clean_payload = payload or {}
        message_body = {
            "format": "v1",
            "job_id": job_id,
            "job_type": str(job_type),
            "payload": clean_payload,
            "attempts": 0,
            "max_attempts": max_attempts,
            "scheduler_run_id": scheduler_run_id,
        }
        await self._insert_ledger_row(
            job_id=job_id,
            job_type=job_type,
            payload=clean_payload,
            max_attempts=max_attempts,
            scheduler_run_id=scheduler_run_id,
        )
        if run_at:
            delay_seconds = int(max(0, (run_at - datetime.now(tz=UTC)).total_seconds()))
            if delay_seconds > 900:
                logging.getLogger(__name__).warning(
                    f"Requested delay {delay_seconds}s exceeds SQS max of 900s. "
                    f"run_at={run_at.isoformat()}, capping to 15 minutes."
                )
            delay_seconds = min(delay_seconds, 900)  # SQS max delay is 15 minutes
        else:
            delay_seconds = 0

        try:
            send_result = await asyncio.to_thread(
                sqs_client.send_message,
                QueueUrl=settings.sqs_worker_queue_url,
                MessageBody=json.dumps(message_body),
                DelaySeconds=delay_seconds,
            )
        except EndpointConnectionError as exc:
            error = (
                f"SQS endpoint unreachable ({settings.aws_endpoint_url}). "
                "Start your LocalStack Docker container and try again."
            )
            await self.mark_failed(job_id, error=error, attempts=0)
            raise RuntimeError(error) from exc
        except Exception as exc:  # noqa: BLE001
            await self.mark_failed(job_id, error=str(exc), attempts=0)
            raise

        await self.mark_sent(job_id, sqs_message_id=send_result.get("MessageId"))
        return JobRecord(
            id=job_id,
            type=job_type,
            payload=clean_payload,
            run_at=run_at or datetime.now(tz=UTC),
            attempts=0,
            max_attempts=max_attempts,
            scheduler_run_id=scheduler_run_id,
        )

    async def _insert_ledger_row(
        self,
        *,
        job_id: str,
        job_type: JobType,
        payload: dict[str, Any],
        max_attempts: int,
        scheduler_run_id: str | None,
    ) -> None:
        await self._execute_ledger(
            """
            insert into public.worker_jobs (
              id, job_type, status, payload, payload_summary, market_key,
              scheduler_run_id, ingest_run_id, max_attempts
            )
            values (
              :id, :job_type, 'queued', cast(:payload as jsonb),
              cast(:payload_summary as jsonb), :market_key, cast(:scheduler_run_id as uuid),
              cast(:ingest_run_id as uuid),
              :max_attempts
            )
            """,
            {
                "id": job_id,
                "job_type": str(job_type),
                "payload": json.dumps(payload),
                "payload_summary": json.dumps(_payload_summary(payload)),
                "market_key": _payload_market_key(payload),
                "scheduler_run_id": scheduler_run_id,
                "ingest_run_id": _payload_ingest_run_id(payload),
                "max_attempts": max_attempts,
            },
        )

    async def mark_sent(self, job_id: str, *, sqs_message_id: str | None) -> None:
        await self._execute_ledger(
            """
            update public.worker_jobs
            set status = 'sent',
                sent_at = now(),
                sqs_message_id = :sqs_message_id,
                updated_at = now()
            where id = :id
              and status <> 'dead'
            """,
            {"id": job_id, "sqs_message_id": sqs_message_id},
        )

    async def mark_processing(
        self,
        job: JobRecord,
        *,
        run_id: str | None = None,
        sqs_message_id: str | None = None,
    ) -> None:
        await self._execute_ledger(
            """
            update public.worker_jobs
            set status = 'processing',
                started_at = coalesce(started_at, now()),
                finished_at = null,
                attempts = :attempts,
                max_attempts = :max_attempts,
                run_id = coalesce(:run_id, run_id),
                sqs_message_id = coalesce(:sqs_message_id, sqs_message_id),
                last_error = null,
                updated_at = now()
            where id = :id
              and status <> 'dead'
            """,
            {
                "id": job.id,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "run_id": run_id or job.run_id,
                "sqs_message_id": sqs_message_id,
            },
        )

    async def mark_succeeded(self, job_id: str, *, result: dict[str, Any] | None) -> None:
        await self._execute_ledger(
            """
            update public.worker_jobs
            set status = 'succeeded',
                finished_at = now(),
                last_error = null,
                result = cast(:result as jsonb),
                updated_at = now()
            where id = :id
              and status <> 'dead'
            """,
            {"id": job_id, "result": json.dumps(result or {})},
        )

    async def mark_failed(
        self,
        job_id: str,
        *,
        error: str,
        attempts: int,
        max_attempts: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        status = "dead" if max_attempts is not None and attempts >= max_attempts else "failed"
        await self._execute_ledger(
            """
            update public.worker_jobs
            set status = case when status = 'dead' then 'dead' else :status end,
                finished_at = now(),
                attempts = greatest(attempts, :attempts),
                max_attempts = coalesce(:max_attempts, max_attempts),
                last_error = :error,
                result = coalesce(cast(:result as jsonb), result),
                updated_at = now()
            where id = :id
            """,
            {
                "id": job_id,
                "status": status,
                "error": error,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "result": json.dumps(result) if result is not None else None,
            },
        )

    @asynccontextmanager
    async def _ledger_session(self) -> AsyncIterator[AsyncSession]:
        if self.ledger_session_factory is not None:
            async with self.ledger_session_factory() as session:
                yield session
            return

        from aventi_backend.db.session import open_db_session

        async with open_db_session() as session:
            yield session

    async def _execute_ledger(self, sql: str, params: dict[str, Any]) -> None:
        async with self._ledger_session() as session:
            await session.execute(text(sql), params)
            await session.commit()


def build_manual_job(job_type: JobType, payload: dict[str, Any]) -> JobRecord:
    now = datetime.now(tz=UTC)
    return JobRecord(
        id=f"local-{job_type.lower()}-{int(now.timestamp())}",
        type=job_type,
        payload=payload,
        run_at=now,
    )


def _payload_market_key(payload: dict[str, Any]) -> str | None:
    for key in ("marketKey", "market_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_ingest_run_id(payload: dict[str, Any]) -> str | None:
    for key in ("ingestRunId", "ingest_run_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary_keys = (
        "marketKey",
        "marketCity",
        "marketState",
        "city",
        "eventId",
        "ingestRunId",
        "scanType",
        "filterSignature",
        "sourceName",
        "angle",
    )
    return {key: payload[key] for key in summary_keys if key in payload}
