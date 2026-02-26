import asyncio
import socket

import structlog

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import open_db_session
from aventi_backend.services.jobs import JobQueueRepository
from aventi_backend.worker.handlers import process_job

logger = structlog.get_logger(__name__)


async def worker_loop() -> None:
    settings = get_settings()
    worker_name = f"aventi-worker@{socket.gethostname()}"

    logger.info("worker.started", poll_seconds=settings.worker_poll_seconds, worker_name=worker_name)
    while True:
        try:
            async with open_db_session() as session:
                repo = JobQueueRepository(session)
                jobs = await repo.claim_due_jobs(worker_name=worker_name, limit=5)
                if not jobs:
                    await asyncio.sleep(settings.worker_poll_seconds)
                    continue

                for job in jobs:
                    logger.info(
                        "worker.job.claimed",
                        job_id=job.id,
                        job_type=job.type,
                        attempts=job.attempts,
                        max_attempts=job.max_attempts,
                    )
                    try:
                        result = await process_job(job, session)
                        await repo.mark_complete(job.id, run_id=job.run_id)
                        logger.info("worker.job.completed", job_id=job.id, job_type=job.type, result=result)
                    except Exception as exc:  # noqa: BLE001
                        await repo.mark_failed(job.id, str(exc), run_id=job.run_id)
                        logger.exception("worker.job.failed", job_id=job.id, job_type=job.type)
        except RuntimeError as exc:
            logger.error("worker.misconfigured", error=str(exc))
            await asyncio.sleep(settings.worker_poll_seconds)


def main() -> None:
    configure_logging(get_settings().log_level)
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
