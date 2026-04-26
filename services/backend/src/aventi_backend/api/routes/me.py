from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.db.deps import get_repository
from aventi_backend.db.repository import AventiRepository
from aventi_backend.db.session import get_db_session
from aventi_backend.models.schemas import (
    MarketSeenPayload,
    ProfileLocationPayload,
    UserPreferences,
)
from aventi_backend.services.market_inventory import (
    MarketWarmupService,
    build_market_descriptor,
)

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


@router.post("/seen-events/reset")
async def reset_seen_events(
    user: AuthenticatedUser = Depends(require_user),
    repo: AventiRepository = Depends(get_repository),
) -> dict:
    return await repo.reset_seen_events(user.id)


@router.post("/market-seen")
async def mark_market_seen(
    payload: MarketSeenPayload,
    user: AuthenticatedUser = Depends(require_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Record that a user is active in a market.

    If the market is not yet tracked, bootstraps a ``market_inventory_state``
    row with ``heat_tier='warm'`` and immediately enqueues a single short-term
    CITY_SCAN job. Idempotent on repeat calls: just bumps
    ``last_user_active_at``.
    """
    market = build_market_descriptor(
        city=payload.city,
        state=payload.state,
        country=payload.country,
        center_latitude=payload.latitude,
        center_longitude=payload.longitude,
    )
    if market is None:
        raise HTTPException(status_code=400, detail="city is required")

    # `user` arg is unused inside the service — we just need auth to pass.
    _ = user

    service = MarketWarmupService(session)
    bootstrapped = await service.bootstrap_market_if_new(market)
    await service.mark_user_active(market)
    return {
        "ok": True,
        "marketKey": market.key,
        "bootstrapped": bootstrapped,
    }
