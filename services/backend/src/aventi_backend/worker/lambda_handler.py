from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.budgets import BudgetError
from aventi_backend.services.jobs import JobQueueRepository, worker_identity
from aventi_backend.worker.handlers import process_job

logger = structlog.get_logger(__name__)
configure_logging(get_settings().log_level)


def handler(event, context) -> dict:
    records = event.get("Records", [])
    logger.info("lambda.handler.invoked", record_count=len(records))
    if not records:
        return {"status": "ok", "message": "No records to process", "batchItemFailures": []}
    return asyncio.run(_process_records(records))


async def _process_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    processed = 0
    failures: list[dict[str, str]] = []
    worker_id = worker_identity("lambda")
    for record in records:
        message_id = str(record.get("messageId") or "")
        try:
            data = json.loads(record.get("body", "{}"))
            job_id = data.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise ValueError("job_id missing")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error("worker.lambda.malformed", message_id=message_id, error=str(exc))
            failures.append({"itemIdentifier": message_id})
            continue

        async with open_db_session() as session:
            repo = JobQueueRepository(session)
            claim = await repo.claim_job(job_id, worker_id=worker_id)
            if claim.outcome != "claimed" or claim.job is None:
                logger.info(
                    "worker.lambda.duplicate",
                    message_id=message_id,
                    job_id=job_id,
                    outcome=claim.outcome,
                )
                if claim.outcome != "completed":
                    failures.append({"itemIdentifier": message_id})
                continue
            job = claim.job
            try:
                result = await process_job(job, session)
            except BudgetError as exc:
                # A budget decision is terminal for this job/day. A new job may
                # be admitted later; retrying this delivery would only churn.
                result = {"skipped": True, "reason": type(exc).__name__, "detail": str(exc)}
                completed = await repo.complete_job(job.id, worker_id=worker_id, result=result)
                if completed:
                    processed += 1
                else:
                    failures.append({"itemIdentifier": message_id})
                logger.info("worker.lambda.budget_skipped", job_id=job.id, result=result)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                lease_owned = await repo.fail_job(job.id, exc, worker_id=worker_id)
                logger.exception(
                    "worker.lambda.error",
                    job_id=job.id,
                    message_id=message_id,
                    lease_owned=lease_owned,
                    error=str(exc),
                )
                failures.append({"itemIdentifier": message_id})
            else:
                completed = await repo.complete_job(job.id, worker_id=worker_id, result=result)
                if completed:
                    processed += 1
                    logger.info("worker.lambda.success", job_id=job.id, result=result)
                else:
                    failures.append({"itemIdentifier": message_id})
                    logger.warning("worker.lambda.lease_lost", job_id=job.id)
    return {"status": "ok", "processed": processed, "batchItemFailures": failures}
