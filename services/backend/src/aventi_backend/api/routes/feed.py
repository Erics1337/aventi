from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.models.schemas import FeedImpressionPayload, FeedRequest, FeedResponse

router = APIRouter()


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    request: Request,
    date: str = Query(default="today"),
    latitude: float = Query(...),
    longitude: float = Query(...),
    limit: int = Query(default=20, ge=1, le=50),
    marketCity: str | None = Query(default=None),
    marketState: str | None = Query(default=None),
    marketCountry: str | None = Query(default=None),
    timeOfDay: str | None = Query(default=None),
    price: str | None = Query(default=None),
    radiusMiles: float | None = Query(default=None),
    vibes: list[str] = Query(default=[]),
    categories: list[str] = Query(default=[]),
    cursor: str | None = Query(default=None),
    destinationId: str | None = Query(default=None),
    startDate: Date | None = Query(default=None),
    endDate: Date | None = Query(default=None),
    premiumAgeRestriction: str = Query(default="all", pattern=r"^(all|18\+|21\+)$"),
    query: str | None = Query(default=None, max_length=120),
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
    repo: AventiRepository = Depends(get_repository),
) -> FeedResponse:
    payload = await repo.get_feed(
        user_id=user.id,
        request_ip=request.client.host if request.client else None,
        settings=settings,
        date=date,
        latitude=latitude,
        longitude=longitude,
        limit=limit,
        time_of_day=timeOfDay,
        price=price,
        radius_miles=radiusMiles,
        selected_vibes=vibes,
        categories=categories,
        cursor=cursor,
        market_city=marketCity,
        market_state=marketState,
        market_country=marketCountry,
        destination_id=destinationId,
        start_date=startDate,
        end_date=endDate,
        premium_age_restriction=premiumAgeRestriction,
        query=query,
    )
    return FeedResponse.model_validate(payload)


@router.post("/feed/refresh", response_model=FeedResponse)
async def refresh_feed(
    payload: FeedRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
    repo: AventiRepository = Depends(get_repository),
) -> FeedResponse:
    response = await repo.get_feed(
        user_id=user.id,
        request_ip=request.client.host if request.client else None,
        settings=settings,
        date=payload.filters.date,
        latitude=payload.latitude,
        longitude=payload.longitude,
        limit=payload.limit,
        time_of_day=payload.filters.time_of_day,
        price=payload.filters.price,
        radius_miles=payload.filters.radius_miles,
        selected_vibes=list(payload.filters.vibes),
        categories=list(payload.filters.categories),
        cursor=None,
        market_city=payload.market_city,
        market_state=payload.market_state,
        market_country=payload.market_country,
        destination_id=str(payload.destination_id) if payload.destination_id else None,
        start_date=payload.filters.start_date,
        end_date=payload.filters.end_date,
        premium_age_restriction=payload.filters.premium_age_restriction,
        query=payload.filters.query,
        force_refresh=True,
    )
    return FeedResponse.model_validate(response)


@router.post("/feed/impressions")
async def post_feed_impression(
    payload: FeedImpressionPayload,
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    try:
        return await repo.record_feed_impression(user_id=user.id, email=user.email, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
