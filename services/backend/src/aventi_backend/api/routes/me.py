from fastapi import APIRouter, Depends

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import ProfileLocationPayload, UserPreferences

router = APIRouter()


@router.post("/bootstrap")
async def bootstrap_me(
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.bootstrap_user(user.id, user.email)


@router.get("")
async def get_me(
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.get_me(user.id, user.email)


@router.put("/preferences")
async def update_preferences(
    payload: UserPreferences,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.update_preferences(user.id, payload)


@router.put("/location")
async def update_profile_location(
    payload: ProfileLocationPayload,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.update_profile_location(user.id, user.email, payload)
