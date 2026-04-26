import asyncio
import socket
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

import structlog
from watchfiles import run_process
from watchfiles.filters import PythonFilter

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings, Settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.jobs import JobRecord, JobType
from aventi_backend.worker.handlers import process_job

logger = structlog.get_logger(__name__)


def _extract_queue_name_from_url(queue_url: str) -> str:
    """Extract queue name from SQS queue URL."""
    # URL format: http://sqs.region.localhost.localstack.cloud:4566/000000000000/queue-name
    # or https://sqs.region.amazonaws.com/123456789012/queue-name
    parsed = urlparse(queue_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) >= 2:
        return path_parts[-1]
    raise ValueError(f"Cannot extract queue name from URL: {queue_url}")


async def _ensure_queue_exists(settings: Settings) -> boto3.client:
    """Ensure SQS queue exists, creating it if necessary (local dev only)."""
    client_kwargs = {}
    if settings.aws_endpoint_url:
        client_kwargs["endpoint_url"] = settings.aws_endpoint_url
    sqs_client = boto3.client("sqs", **client_kwargs)

    if not settings.sqs_worker_queue_url:
        return sqs_client

    try:
        # Try to get queue URL (validates it exists)
        await asyncio.to_thread(
            sqs_client.get_queue_attributes,
            QueueUrl=settings.sqs_worker_queue_url,
            AttributeNames=["QueueArn"],
        )
        logger.debug("worker.queue.exists", queue_url=settings.sqs_worker_queue_url)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "AWS.SimpleQueueService.NonExistentQueue":
            # Queue doesn't exist - create it (local dev only)
            if settings.env not in ("dev", "development", "test", "staging"):
                logger.error(
                    "worker.queue.not_found_production",
                    queue_url=settings.sqs_worker_queue_url,
                    env=settings.env,
                    error="Queue auto-creation disabled in production"
                )
                raise
            queue_name = _extract_queue_name_from_url(settings.sqs_worker_queue_url)
            logger.info("worker.queue.creating", queue_name=queue_name, queue_url=settings.sqs_worker_queue_url)
            try:
                await asyncio.to_thread(
                    sqs_client.create_queue,
                    QueueName=queue_name,
                )
                logger.info("worker.queue.created", queue_name=queue_name)
            except ClientError as create_exc:
                logger.error("worker.queue.create_failed", queue_name=queue_name, error=str(create_exc))
                raise
        else:
            raise
    return sqs_client


async def worker_loop() -> None:
    settings = get_settings()
    worker_name = f"aventi-worker@{socket.gethostname()}"

    logger.info("worker.started", sqs_enabled=True, worker_name=worker_name)

    # Ensure queue exists (creates if missing in local dev)
    sqs_client = await _ensure_queue_exists(settings)

    try:
        while True:
            try:
                if not settings.sqs_worker_queue_url:
                    logger.error("worker.misconfigured", error="SQS_WORKER_QUEUE_URL missing")
                    await asyncio.sleep(settings.worker_poll_seconds)
                    continue

                # Poll SQS (this is a blocking synchronous call, we wrap in asyncio thread)
                # Max time 20s long polling
                response = await asyncio.to_thread(
                    sqs_client.receive_message,
                    QueueUrl=settings.sqs_worker_queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,
                    VisibilityTimeout=300, # 5 minutes before message becomes visible again
                    AttributeNames=["ApproximateReceiveCount"],
                )

                messages = response.get("Messages", [])
                if not messages:
                    # no messages, poll_seconds is meant as the sleep when idle but wait_time acts as that
                    continue

                for message in messages:
                    receipt_handle = message["ReceiptHandle"]
                    raw_body = message["Body"]

                    try:
                        body = json.loads(raw_body)
                        # We handle basic validation (it could be an unformatted message in prod if manually pushed via AWS CLI, assuming our format is "v1")
                        job_id = body.get("job_id", "unknown")
                        job_type_str = body.get("job_type")
                        if not job_type_str:
                            raise ValueError("job_type missing")
                        job_type = JobType(job_type_str)
                        payload = body.get("payload", {})
                        attempts = int(message.get("Attributes", {}).get("ApproximateReceiveCount", body.get("attempts", 0)))
                        max_attempts = body.get("max_attempts", 5)

                        job = JobRecord(
                            id=job_id,
                            type=job_type,
                            payload=payload,
                            run_at=datetime.now(tz=UTC),
                            attempts=attempts,
                            max_attempts=max_attempts,
                        )

                        logger.info(
                            "worker.job.claimed",
                            job_id=job.id,
                            job_type=job.type,
                            attempts=job.attempts,
                            max_attempts=job.max_attempts,
                        )
                    except Exception as exe:
                        logger.error("worker.job.malformed", body=raw_body, error=str(exe))
                        # If malformed, delete it to not poison queue
                        await asyncio.to_thread(
                            sqs_client.delete_message,
                            QueueUrl=settings.sqs_worker_queue_url,
                            ReceiptHandle=receipt_handle,
                        )
                        continue

                    # Execute the job context
                    async with open_db_session() as session:
                        try:
                            result = await process_job(job, session)
                            # On success, delete message from SQS
                            await asyncio.to_thread(
                                sqs_client.delete_message,
                                QueueUrl=settings.sqs_worker_queue_url,
                                ReceiptHandle=receipt_handle,
                            )
                            logger.info(
                                "worker.job.completed",
                                job_id=job.id,
                                job_type=job.type,
                                result=result,
                            )
                        except (asyncio.CancelledError, KeyboardInterrupt):
                            logger.info("worker.job.interrupted", job_id=job.id, job_type=job.type)
                            raise
                        except Exception as exc:  # noqa: BLE001
                            # We let SQS default redelivery visibility timeout handle failures.
                            # Just log it for now
                            logger.exception("worker.job.failed", job_id=job.id, job_type=job.type, error=str(exc))

            except RuntimeError as exc:
                logger.error("worker.misconfigured", error=str(exc))
                await asyncio.sleep(settings.worker_poll_seconds)
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, asyncio.CancelledError):
                    raise
                logger.exception("worker.loop_error", error=str(exc))
                await asyncio.sleep(settings.worker_poll_seconds)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("worker.stopped", worker_name=worker_name)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.env == "development":
        logger.info("worker.reload_enabled", watch_path="src")
        run_process("src", target=_run_worker_process, watch_filter=PythonFilter())
        return

    _run_worker_process()


def _run_worker_process() -> None:
    configure_logging(get_settings().log_level)
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("worker.shutdown_complete")


if __name__ == "__main__":
    main()
