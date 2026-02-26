from fastapi import APIRouter, Depends

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import MembershipEntitlements

router = APIRouter()


@router.get("/membership/entitlements", response_model=MembershipEntitlements)
async def get_entitlements(
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> MembershipEntitlements:
    return await repo.get_entitlements(user.id, user.email)
