import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.worker.handlers import process_job

logger = structlog.get_logger(__name__)

# Initialize logging during cold start
configure_logging(get_settings().log_level)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
JobProcessor = Callable[[JobRecord, AsyncSession], Awaitable[Any]]


def handler(event, context) -> dict:
    """AWS Lambda entry point for SQS events"""

    records = event.get("Records", [])
    logger.info("lambda.handler.invoked", record_count=len(records))

    if not records:
        return {"status": "ok", "message": "No records to process"}

    # Run the async execution loop
    return asyncio.run(_process_records(records))


async def _process_records(
    records: list[dict],
    *,
    session_factory: SessionFactory = open_db_session,
    job_processor: JobProcessor = process_job,
) -> dict:
    processed = 0
    failures = []

    for record in records:
        # Each record gets its own session/transaction for isolation
        async with session_factory() as session:
            try:
                body = record.get("body", "{}")
                data = json.loads(body)

                job_id = data.get("job_id") or f"sqs-{uuid.uuid4()}"
                job_type = JobType(data.get("job_type"))
                payload = data.get("payload", {})
                attempts = int(record.get("attributes", {}).get("ApproximateReceiveCount", 1))
                max_attempts = data.get("max_attempts", 5)

                job = JobRecord(
                    id=job_id,
                    type=job_type,
                    payload=payload,
                    run_at=datetime.now(tz=UTC),
                    attempts=attempts,
                    max_attempts=max_attempts,
                    run_id=record.get("messageId")
                )

                logger.info(
                    "worker.lambda.processing",
                    job_id=job.id,
                    job_type=job.type.value,
                    attempts=attempts
                )

                # Process the job
                result = await job_processor(job, session)
                logger.info("worker.lambda.success", job_id=job.id, result=result)
                processed += 1

            except Exception as exc: # noqa: BLE001
                # If an explicit failure happens, we catch it per record.
                # However, since Lambda integrates with SQS natively,
                # if you are processing a batch of records, you should return
                # a 'batchItemFailures' payload so SQS only retries the failed ones.
                logger.exception(
                    "worker.lambda.error",
                    message_id=record.get("messageId"),
                    error=str(exc),
                )
                failures.append({"itemIdentifier": record.get("messageId")})

    return {
        "status": "ok",
        "processed": processed,
        "batchItemFailures": failures
    }
