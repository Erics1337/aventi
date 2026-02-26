from fastapi import APIRouter, Depends
from fastapi import HTTPException, status

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository

router = APIRouter()


@router.get("/favorites")
async def get_favorites(
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.list_favorites(user.id)


@router.put("/favorites/{event_id}")
async def save_favorite(
    event_id: str,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.save_favorite(user.id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/favorites/{event_id}")
async def delete_favorite(
    event_id: str,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.delete_favorite(user.id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
