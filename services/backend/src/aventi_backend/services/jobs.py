from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import boto3
from botocore.exceptions import EndpointConnectionError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

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


class JobQueueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue_job(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        *,
        run_at: datetime | None = None,
        max_attempts: int = 5,
    ) -> JobRecord:
        settings = get_settings()

        if not settings.sqs_worker_queue_url:
            raise RuntimeError("SQS_WORKER_QUEUE_URL must be configured to enqueue jobs.")

        job_id = f"job-{uuid.uuid4()}"
        client_kwargs = {}
        if settings.aws_endpoint_url:
            client_kwargs["endpoint_url"] = settings.aws_endpoint_url
        sqs_client = boto3.client("sqs", **client_kwargs)
        message_body = {
            "format": "v1",
            "job_id": job_id,
            "job_type": str(job_type),
            "payload": payload or {},
            "attempts": 0,
            "max_attempts": max_attempts,
        }
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
            await asyncio.to_thread(
                sqs_client.send_message,
                QueueUrl=settings.sqs_worker_queue_url,
                MessageBody=json.dumps(message_body),
                DelaySeconds=delay_seconds,
            )
        except EndpointConnectionError as exc:
            raise RuntimeError(
                f"SQS endpoint unreachable ({settings.aws_endpoint_url}). "
                "Start your LocalStack Docker container and try again."
            ) from exc
        return JobRecord(
            id=job_id,
            type=job_type,
            payload=payload or {},
            run_at=run_at or datetime.now(tz=UTC),
            attempts=0,
            max_attempts=max_attempts,
        )


def build_manual_job(job_type: JobType, payload: dict[str, Any]) -> JobRecord:
    now = datetime.now(tz=UTC)
    return JobRecord(
        id=f"local-{job_type.lower()}-{int(now.timestamp())}",
        type=job_type,
        payload=payload,
        run_at=now,
    )
