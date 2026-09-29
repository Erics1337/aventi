from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.session import get_db_session
from aventi_backend.services.accounts import AccountDeletionError, AccountDeletionService
from aventi_backend.services.billing import BillingIdentityError
from aventi_backend.services.destinations import (
    DestinationConfigurationError,
    DestinationPremiumRequiredError,
    DestinationProviderError,
    DestinationService,
)
from aventi_backend.services.insights import (
    InsightsService,
    InsightUnavailableError,
    PremiumRequiredError,
)

router = APIRouter()

UserDependency = Annotated[AuthenticatedUser, Depends(require_user)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/destinations")
async def search_destinations(
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> dict[str, Any]:
    try:
        service = DestinationService(session, settings=settings)
        await service.require_premium(user.id)
        return await service.search(q, limit=limit)
    except DestinationPremiumRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except DestinationConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except DestinationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/events/{event_id}/insights")
async def get_event_insights(
    event_id: str,
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    radius_miles: Annotated[float | None, Query(alias="radiusMiles", ge=1, le=100)] = None,
    destination_id: Annotated[UUID | None, Query(alias="destinationId")] = None,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
    age_restriction: Annotated[str | None, Query(alias="ageRestriction", max_length=30)] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    vibes: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    try:
        return await InsightsService(session, settings=settings).get_or_enqueue(
            user_id=user.id,
            event_id=event_id,
            filters={
                "radiusMiles": radius_miles,
                "destinationId": str(destination_id) if destination_id else None,
                "startDate": start_date.isoformat() if start_date else None,
                "endDate": end_date.isoformat() if end_date else None,
                "ageRestriction": age_restriction,
                "categories": sorted(categories or []),
                "vibes": sorted(vibes or []),
            },
        )
    except PremiumRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except InsightUnavailableError as exc:
        return {"status": "unavailable", "reason": str(exc), "retryAfterSeconds": 300}


@router.delete("/me", status_code=status.HTTP_202_ACCEPTED)
async def delete_me(
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    try:
        return await AccountDeletionService(session, settings=settings).request_deletion(user.id)
    except BillingIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": str(exc), "retryable": True},
        ) from exc


@router.get("/me/deletion")
async def get_my_deletion(
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    try:
        deletion = await AccountDeletionService(session, settings=settings).get_status(user.id)
    except BillingIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return deletion or {"status": "not_requested"}
