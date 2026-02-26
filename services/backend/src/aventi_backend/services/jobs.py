from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class JobType(StrEnum):
    CITY_SCAN = "CITY_SCAN"
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
        result = await self.session.execute(
            text(
                """
                insert into public.job_queue (
                    job_type,
                    payload,
                    status,
                    attempts,
                    max_attempts,
                    run_at,
                    created_at,
                    updated_at
                )
                values (
                    :job_type,
                    cast(:payload_json as jsonb),
                    'queued',
                    0,
                    :max_attempts,
                    coalesce(:run_at, now()),
                    now(),
                    now()
                )
                returning id::text as id, job_type, payload, run_at, attempts, max_attempts
                """
            ),
            {
                "job_type": str(job_type),
                "payload_json": json.dumps(payload or {}),
                "max_attempts": max_attempts,
                "run_at": run_at,
            },
        )
        row = result.mappings().one()
        await self.session.commit()
        return JobRecord(
            id=str(row["id"]),
            type=JobType(str(row["job_type"])),
            payload=dict(row["payload"] or {}),
            run_at=row["run_at"],
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def claim_due_jobs(self, worker_name: str, limit: int = 5) -> list[JobRecord]:
        result = await self.session.execute(
            text(
                """
                with due as (
                    select jq.id
                    from public.job_queue jq
                    where jq.status = 'queued'
                      and jq.run_at <= now()
                    order by jq.run_at asc, jq.created_at asc
                    for update skip locked
                    limit :limit_rows
                ), claimed as (
                    update public.job_queue jq
                    set status = 'running',
                        locked_at = now(),
                        locked_by = :worker_name,
                        attempts = jq.attempts + 1,
                        updated_at = now()
                    from due
                    where jq.id = due.id
                    returning jq.id::text as id, jq.job_type, jq.payload, jq.run_at, jq.attempts, jq.max_attempts, jq.locked_by
                )
                select * from claimed
                order by run_at asc
                """
            ),
            {"worker_name": worker_name, "limit_rows": limit},
        )
        rows = result.mappings().all()

        claimed_jobs: list[JobRecord] = []
        for row in rows:
            run_result = await self.session.execute(
                text(
                    """
                    insert into public.job_runs (job_id, status, worker_name, started_at)
                    values (:job_id, 'running', :worker_name, now())
                    returning id::text as id
                    """
                ),
                {"job_id": row["id"], "worker_name": worker_name},
            )
            run_row = run_result.mappings().one()
            claimed_jobs.append(
                JobRecord(
                    id=str(row["id"]),
                    type=JobType(str(row["job_type"])),
                    payload=dict(row["payload"] or {}),
                    run_at=row["run_at"],
                    attempts=int(row["attempts"]),
                    max_attempts=int(row["max_attempts"]),
                    run_id=str(run_row["id"]),
                    locked_by=str(row["locked_by"] or worker_name),
                )
            )

        await self.session.commit()
        return claimed_jobs

    async def mark_complete(self, job_id: str, *, run_id: str | None = None) -> None:
        await self.session.execute(
            text(
                """
                update public.job_queue
                set status = 'done',
                    locked_at = null,
                    locked_by = null,
                    last_error = null,
                    updated_at = now()
                where id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        if run_id:
            await self.session.execute(
                text(
                    """
                    update public.job_runs
                    set status = 'completed',
                        finished_at = now()
                    where id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
        await self.session.commit()

    async def mark_failed(self, job_id: str, error: str, *, run_id: str | None = None) -> None:
        result = await self.session.execute(
            text(
                """
                update public.job_queue
                set status = case when attempts >= max_attempts then 'failed' else 'queued' end,
                    run_at = case
                        when attempts >= max_attempts then run_at
                        else now() + make_interval(secs => least(300, greatest(10, attempts * 15)))
                    end,
                    locked_at = null,
                    locked_by = null,
                    last_error = :error,
                    updated_at = now()
                where id = :job_id
                returning status
                """
            ),
            {"job_id": job_id, "error": error[:2000]},
        )
        row = result.first()
        run_status = "failed" if (row and row[0] == "failed") else "retrying"
        if run_id:
            await self.session.execute(
                text(
                    """
                    update public.job_runs
                    set status = :status,
                        error_message = :error,
                        finished_at = now()
                    where id = :run_id
                    """
                ),
                {"run_id": run_id, "status": run_status, "error": error[:2000]},
            )
        await self.session.commit()

    async def list_jobs(self, *, statuses: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if statuses:
            query = text(
                """
                select id::text as id, job_type, status, attempts, max_attempts, run_at, locked_by, last_error
                from public.job_queue
                where status = any(:statuses)
                order by created_at desc
                limit :limit_rows
                """
            )
            params = {"statuses": statuses, "limit_rows": limit}
        else:
            query = text(
                """
                select id::text as id, job_type, status, attempts, max_attempts, run_at, locked_by, last_error
                from public.job_queue
                order by created_at desc
                limit :limit_rows
                """
            )
            params = {"limit_rows": limit}
        result = await self.session.execute(query, params)
        return [dict(row) for row in result.mappings().all()]


def build_manual_job(job_type: JobType, payload: dict[str, Any]) -> JobRecord:
    now = datetime.now(tz=UTC)
    return JobRecord(
        id=f"local-{job_type.lower()}-{int(now.timestamp())}",
        type=job_type,
        payload=payload,
        run_at=now,
    )
