from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from pydantic import BaseModel

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import ReportReason

router = APIRouter()


class EventReportPayload(BaseModel):
    reason: ReportReason
    details: str | None = None


@router.post("/events/{event_id}/report")
async def report_event(
    event_id: str,
    payload: EventReportPayload,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.report_event(user.id, event_id, payload.reason, payload.details)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
