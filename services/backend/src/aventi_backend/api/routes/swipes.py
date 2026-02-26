from fastapi import APIRouter, Depends, HTTPException, status

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import SwipePayload

router = APIRouter()


@router.post("/swipes")
async def post_swipe(
    payload: SwipePayload,
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.record_swipe(user_id=user.id, email=user.email, payload=payload, settings=settings)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
