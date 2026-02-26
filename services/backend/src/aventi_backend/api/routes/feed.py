from fastapi import APIRouter, Depends, HTTPException, Query, status

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import FeedImpressionPayload, FeedResponse

router = APIRouter()


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    date: str = Query(default="today"),
    latitude: float = Query(...),
    longitude: float = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
    timeOfDay: str | None = Query(default=None),
    price: str | None = Query(default=None),
    radiusMiles: float | None = Query(default=None),
    cursor: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
    repo: AventiRepository = Depends(get_repository),
    ) -> FeedResponse:
    payload = await repo.get_feed(
        user_id=user.id,
        settings=settings,
        date=date,
        latitude=latitude,
        longitude=longitude,
        limit=limit,
        time_of_day=timeOfDay,
        price=price,
        radius_miles=radiusMiles,
        cursor=cursor,
    )
    return FeedResponse.model_validate(payload)


@router.post("/feed/impressions")
async def post_feed_impression(
    payload: FeedImpressionPayload,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.record_feed_impression(user_id=user.id, email=user.email, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
