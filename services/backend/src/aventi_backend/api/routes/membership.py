from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.auth import AuthenticatedUser, require_user
from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.db.session import get_db_session
from aventi_backend.services.billing import (
    BillingConfigurationError,
    BillingIdentityError,
    BillingService,
    RevenueCatError,
)

router = APIRouter()

UserDependency = Annotated[AuthenticatedUser, Depends(require_user)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class RevenueCatCustomerInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original_app_user_id: str | None = Field(default=None, alias="originalAppUserId")
    active_entitlement_ids: list[str] = Field(default_factory=list, alias="activeEntitlementIds")
    latest_expiration_date: str | None = Field(default=None, alias="latestExpirationDate")
    management_url: str | None = Field(default=None, alias="managementUrl")


class MembershipReconcilePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_user_id: str = Field(alias="appUserId")
    customer_info: RevenueCatCustomerInfo | None = Field(default=None, alias="customerInfo")


@router.get("/membership/entitlements")
async def get_entitlements(
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    try:
        return await BillingService(session, settings=settings).get_entitlements(user_id=user.id)
    except BillingIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (BillingConfigurationError, RevenueCatError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.post("/membership/reconcile")
async def reconcile_membership(
    payload: MembershipReconcilePayload,
    request: Request,
    user: UserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    # Device customerInfo is a display hint, never an authority for premium access.
    _ = payload.customer_info
    claims = getattr(request.state, "auth_claims", {})
    if isinstance(claims, dict) and claims.get("is_anonymous") is True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anonymous Supabase users cannot own or reconcile purchases",
        )
    try:
        return await BillingService(session, settings=settings).reconcile(
            authenticated_user_id=user.id,
            app_user_id=payload.app_user_id,
        )
    except BillingIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (BillingConfigurationError, RevenueCatError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.get("/membership/products")
async def membership_products(
    _user: UserDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    """Return store identifiers only; localized prices come from the store SDK."""
    products = [
        {"period": "monthly", "productId": settings.revenuecat_monthly_product_id},
        {"period": "annual", "productId": settings.revenuecat_annual_product_id},
    ]
    return {
        "purchasesEnabled": settings.purchases_enabled,
        "entitlementId": settings.revenuecat_entitlement_id,
        "products": [product for product in products if product["productId"]],
    }


@router.post("/membership/webhooks/revenuecat")
@router.post("/membership/revenuecat/webhook", include_in_schema=False)
async def revenuecat_webhook(
    payload: dict[str, Any],
    session: SessionDependency,
    settings: SettingsDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    service = BillingService(session, settings=settings)
    try:
        service.verify_webhook_authorization(authorization)
        return await service.process_webhook(payload)
    except BillingIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except (BillingConfigurationError, RevenueCatError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
