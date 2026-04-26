from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import require_internal_api_key
from aventi_backend.core.settings import get_settings
from aventi_backend.db.session import get_db_session
from aventi_backend.services.ingest import ManualIngestService
from aventi_backend.services.jobs import JobType
from aventi_backend.services.jobs import JobQueueRepository
from aventi_backend.services.verification import VerificationService

router = APIRouter(dependencies=[Depends(require_internal_api_key)])


class EnqueueJobPayload(BaseModel):
    type: JobType
    payload: dict = Field(default_factory=dict)
    max_attempts: int = 5


class ManualIngestPayload(BaseModel):
    source_name: str
    city: str
    events: list[dict]
    enqueue_verification_jobs: bool = True


class VerificationRunPayload(BaseModel):
    limit: int = 20


@router.post("/jobs/enqueue")
async def enqueue_job(
    payload: EnqueueJobPayload,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        job = await JobQueueRepository(session).enqueue_job(
            payload.type, payload.payload, max_attempts=payload.max_attempts
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return {
        "ok": True,
        "job": {
            "id": job.id,
            "type": str(job.type),
            "runAt": job.run_at.isoformat(),
            "attempts": job.attempts,
            "maxAttempts": job.max_attempts,
        },
    }


@router.post("/ingest/manual")
async def ingest_manual(
    payload: ManualIngestPayload,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        ingest_summary = await ManualIngestService(session).ingest_manual(
            source_name=payload.source_name,
            city=payload.city,
            events=payload.events,
        )
        verification_jobs_enqueued = 0
        settings = get_settings()
        if settings.enable_verification and payload.enqueue_verification_jobs and ingest_summary.event_ids:
            verification_jobs_enqueued = await VerificationService(session).enqueue_verification_jobs(
                limit=len(ingest_summary.event_ids),
                event_ids=ingest_summary.event_ids,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    response = ingest_summary.as_dict()
    response["verificationJobsEnqueued"] = verification_jobs_enqueued
    return response


@router.post("/seen-events/reset")
async def reset_seen_events(
    payload: dict[str, Any] | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Reset seen events for testing. Optional user_id in payload to reset specific user."""
    try:
        user_id = payload.get("user_id") if payload else None
        if user_id:
            result = await session.execute(
                text("delete from public.feed_impressions where user_id = :user_id"),
                {"user_id": user_id}
            )
            await session.commit()
            return {"message": f"Reset seen events for user {user_id}", "deleted": result.rowcount}
        else:
            result = await session.execute(text("delete from public.feed_impressions"))
            await session.commit()
            return {"message": "Reset all seen events", "deleted": result.rowcount}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/verification/run")
async def run_verification(
    payload: VerificationRunPayload,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        enqueued = await VerificationService(session).enqueue_verification_jobs(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return {"ok": True, "requested": payload.limit, "enqueued": enqueued}
