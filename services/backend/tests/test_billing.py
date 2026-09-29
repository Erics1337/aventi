import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from aventi_backend.api.routes.membership import (
    MembershipReconcilePayload,
    reconcile_membership,
)
from aventi_backend.core.auth import AuthenticatedUser
from aventi_backend.services.billing import (
    BillingIdentityError,
    BillingService,
    RevenueCatError,
    require_permanent_user_id,
)


class UnusedSession:
    pass


DATABASE_URL = os.environ.get("AVENTI_TEST_DATABASE_URL")


def service(**settings):
    defaults = {
        "revenuecat_secret_key": None,
        "revenuecat_entitlement_id": "premium",
        "revenuecat_webhook_secret": "webhook-secret",
    }
    defaults.update(settings)
    return BillingService(UnusedSession(), settings=SimpleNamespace(**defaults))


def test_permanent_identity_rejects_anonymous_and_non_uuid_ids():
    user_id = str(uuid4())
    assert require_permanent_user_id(user_id) == user_id
    with pytest.raises(BillingIdentityError):
        require_permanent_user_id("$RCAnonymousID:abc")
    with pytest.raises(BillingIdentityError):
        require_permanent_user_id("dev-user")


def test_subscriber_state_uses_only_explicit_provider_grace():
    now = datetime.now(tz=UTC)
    billing = service()
    expired = (now - timedelta(minutes=1)).isoformat()
    grace = (now + timedelta(hours=2)).isoformat()

    without_grace = billing.state_from_subscriber(
        {
            "subscriber": {
                "entitlements": {
                    "premium": {"product_identifier": "monthly", "expires_date": expired}
                }
            }
        },
        now=now,
    )
    assert without_grace.is_premium is False
    assert without_grace.status == "expired"

    with_grace = billing.state_from_subscriber(
        {
            "subscriber": {
                "entitlements": {
                    "premium": {
                        "product_identifier": "monthly",
                        "expires_date": expired,
                        "grace_period_expires_date": grace,
                    }
                }
            }
        },
        now=now,
    )
    assert with_grace.is_premium is True
    assert with_grace.status == "grace_period"
    assert with_grace.valid_until == datetime.fromisoformat(grace)


def test_subscriber_without_expiration_fails_closed():
    state = service(
        revenuecat_monthly_product_id="monthly",
        revenuecat_annual_product_id="annual",
    ).state_from_subscriber(
        {"subscriber": {"entitlements": {"premium": {"product_identifier": "monthly"}}}}
    )
    assert state.is_premium is False
    assert state.valid_until is None


def test_webhook_authorization_uses_configured_header():
    billing = service()
    billing.verify_webhook_authorization("Bearer webhook-secret")
    billing.verify_webhook_authorization("webhook-secret")
    with pytest.raises(BillingIdentityError):
        billing.verify_webhook_authorization("Bearer wrong")


@pytest.mark.asyncio
async def test_anonymous_supabase_user_cannot_reconcile_purchase():
    user_id = str(uuid4())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/membership/reconcile",
            "headers": [],
            "state": {"auth_claims": {"sub": user_id, "is_anonymous": True}},
        }
    )
    with pytest.raises(HTTPException) as caught:
        await reconcile_membership(
            MembershipReconcilePayload(appUserId=user_id),
            request,
            AuthenticatedUser(id=user_id),
            UnusedSession(),
            SimpleNamespace(),
        )
    assert caught.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_reconcile_persists_server_authoritative_subscriber_state():
    user_id = str(uuid4())
    expires_at = datetime.now(tz=UTC) + timedelta(days=30)

    class FakeRevenueCat:
        async def get_subscriber(self, requested_user_id):
            assert requested_user_id == user_id
            return {
                "subscriber": {
                    "original_app_user_id": user_id,
                    "management_url": "https://apps.apple.com/account/subscriptions",
                    "entitlements": {
                        "premium": {
                            "product_identifier": "aventi.monthly",
                            "expires_date": expires_at.isoformat(),
                        }
                    },
                    "subscriptions": {},
                }
            }

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.execute(
                text("insert into public.profiles (id, email) values (:id, :email)"),
                {"id": user_id, "email": "billing-test@example.com"},
            )
            await session.commit()
            settings = SimpleNamespace(
                revenuecat_secret_key=None,
                revenuecat_entitlement_id="premium",
                revenuecat_monthly_product_id="aventi.monthly",
                revenuecat_annual_product_id="aventi.annual",
                purchases_enabled=False,
            )
            result = await BillingService(
                session, settings=settings, revenuecat=FakeRevenueCat()
            ).reconcile(authenticated_user_id=user_id, app_user_id=user_id)
            assert result["isPremium"] is True
            assert result["purchasesEnabled"] is False
            row = (
                (
                    await session.execute(
                        text(
                            "select is_premium, product_identifier, source "
                            "from public.premium_entitlements where user_id=:id"
                        ),
                        {"id": user_id},
                    )
                )
                .mappings()
                .one()
            )
            assert dict(row) == {
                "is_premium": True,
                "product_identifier": "aventi.monthly",
                "source": "revenuecat_api",
            }
            await session.execute(text("delete from public.profiles where id=:id"), {"id": user_id})
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_reordered_webhooks_always_use_current_provider_state():
    user_id = str(uuid4())
    expires_at = datetime.now(tz=UTC) + timedelta(days=30)

    class FakeRevenueCat:
        async def get_subscriber(self, _requested_user_id):
            return {
                "subscriber": {
                    "original_app_user_id": user_id,
                    "entitlements": {
                        "premium": {
                            "product_identifier": "aventi.monthly",
                            "expires_date": expires_at.isoformat(),
                        }
                    },
                    "subscriptions": {},
                }
            }

    settings = SimpleNamespace(
        revenuecat_secret_key=None,
        revenuecat_entitlement_id="premium",
        revenuecat_monthly_product_id="aventi.monthly",
        revenuecat_annual_product_id="aventi.annual",
        purchases_enabled=True,
    )
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.execute(
                text("insert into public.profiles (id, email) values (:id, :email)"),
                {"id": user_id, "email": "webhook-order@example.com"},
            )
            await session.commit()
            service = BillingService(session, settings=settings, revenuecat=FakeRevenueCat())
            now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
            newer = {
                "event": {
                    "id": f"newer-{uuid4()}",
                    "type": "REFUND",
                    "app_user_id": user_id,
                    "original_app_user_id": user_id,
                    "event_timestamp_ms": now_ms,
                }
            }
            older = {
                "event": {
                    "id": f"older-{uuid4()}",
                    "type": "EXPIRATION",
                    "app_user_id": user_id,
                    "original_app_user_id": user_id,
                    "event_timestamp_ms": now_ms - 60_000,
                }
            }
            assert (await service.process_webhook(newer))["entitlements"]["isPremium"] is True
            assert (await service.process_webhook(older))["entitlements"]["isPremium"] is True
            row = (
                (
                    await session.execute(
                        text(
                            "select is_premium, source from public.premium_entitlements "
                            "where user_id=:id"
                        ),
                        {"id": user_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row["is_premium"] is True
            assert row["source"] == "revenuecat_webhook_reconcile"
            await session.execute(text("delete from public.profiles where id=:id"), {"id": user_id})
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_provider_outage_cache_is_time_bounded_and_null_expiry_fails_closed():
    user_id = str(uuid4())

    class UnavailableRevenueCat:
        async def get_subscriber(self, _requested_user_id):
            raise RevenueCatError("temporary outage")

    settings = SimpleNamespace(
        revenuecat_secret_key=None,
        revenuecat_entitlement_id="premium",
        revenuecat_monthly_product_id="aventi.monthly",
        revenuecat_annual_product_id="aventi.annual",
        purchases_enabled=True,
    )
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.execute(
                text("insert into public.profiles (id, email) values (:id, :email)"),
                {"id": user_id, "email": "outage-cache@example.com"},
            )
            await session.execute(
                text(
                    """
                    insert into public.premium_entitlements
                      (user_id, plan, is_premium, source, valid_until,
                       product_identifier, entitlement_status)
                    values (:id, 'unlimited', true, 'revenuecat_api', :valid_until,
                            'aventi.monthly', 'active')
                    """
                ),
                {"id": user_id, "valid_until": datetime.now(tz=UTC) + timedelta(hours=1)},
            )
            await session.commit()
            service = BillingService(session, settings=settings, revenuecat=UnavailableRevenueCat())
            assert (await service.get_entitlements(user_id=user_id))["isPremium"] is True

            await session.execute(
                text("update public.premium_entitlements set valid_until=null where user_id=:id"),
                {"id": user_id},
            )
            await session.commit()
            null_expiry = await service.get_entitlements(user_id=user_id)
            assert null_expiry["isPremium"] is False
            assert null_expiry["status"] == "invalid_expiration"

            await session.execute(text("delete from public.profiles where id=:id"), {"id": user_id})
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_deleted_user_webhook_is_acknowledged_with_minimal_dedup_record():
    user_id = str(uuid4())
    event_id = f"deleted-{uuid4()}"

    class MustNotFetchRevenueCat:
        async def get_subscriber(self, _requested_user_id):
            raise AssertionError("deleted users must not call RevenueCat")

    settings = SimpleNamespace(
        revenuecat_secret_key=None,
        revenuecat_entitlement_id="premium",
        revenuecat_monthly_product_id="aventi.monthly",
        revenuecat_annual_product_id="aventi.annual",
        purchases_enabled=True,
    )
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.execute(
                text(
                    "insert into public.account_deletions (user_id, status) "
                    "values (:id, 'completed')"
                ),
                {"id": user_id},
            )
            await session.commit()
            service = BillingService(
                session, settings=settings, revenuecat=MustNotFetchRevenueCat()
            )
            result = await service.process_webhook(
                {
                    "event": {
                        "id": event_id,
                        "type": "EXPIRATION",
                        "app_user_id": user_id,
                        "original_app_user_id": user_id,
                    }
                }
            )
            assert result["ignored"] == "account_unavailable"
            row = (
                (
                    await session.execute(
                        text(
                            "select user_id, payload, processing_status "
                            "from public.revenuecat_events where event_id=:event_id"
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row["user_id"] is None
            assert row["payload"] == {}
            assert row["processing_status"] == "rejected"
            await session.execute(
                text("delete from public.revenuecat_events where event_id=:event_id"),
                {"event_id": event_id},
            )
            await session.execute(
                text("delete from public.account_deletions where user_id=:id"), {"id": user_id}
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_webhook_provider_failure_rolls_back_dedup_for_retry():
    user_id = str(uuid4())
    event_id = f"retry-{uuid4()}"
    expires_at = datetime.now(tz=UTC) + timedelta(days=30)

    class FlakyRevenueCat:
        def __init__(self):
            self.calls = 0

        async def get_subscriber(self, _requested_user_id):
            self.calls += 1
            if self.calls == 1:
                raise RevenueCatError("temporary outage")
            return {
                "subscriber": {
                    "original_app_user_id": user_id,
                    "entitlements": {
                        "premium": {
                            "product_identifier": "aventi.monthly",
                            "expires_date": expires_at.isoformat(),
                        }
                    },
                    "subscriptions": {},
                }
            }

    settings = SimpleNamespace(
        revenuecat_secret_key=None,
        revenuecat_entitlement_id="premium",
        revenuecat_monthly_product_id="aventi.monthly",
        revenuecat_annual_product_id="aventi.annual",
        purchases_enabled=True,
    )
    payload = {
        "event": {
            "id": event_id,
            "type": "RENEWAL",
            "app_user_id": user_id,
            "original_app_user_id": user_id,
        }
    }
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.execute(
                text("insert into public.profiles (id, email) values (:id, :email)"),
                {"id": user_id, "email": "webhook-retry@example.com"},
            )
            await session.commit()
            service = BillingService(session, settings=settings, revenuecat=FlakyRevenueCat())
            with pytest.raises(RevenueCatError):
                await service.process_webhook(payload)
            assert (
                await session.execute(
                    text("select count(*) from public.revenuecat_events where event_id=:event_id"),
                    {"event_id": event_id},
                )
            ).scalar_one() == 0

            retried = await service.process_webhook(payload)
            assert retried["entitlements"]["isPremium"] is True
            assert (
                await session.execute(
                    text(
                        "select processing_status from public.revenuecat_events "
                        "where event_id=:event_id"
                    ),
                    {"event_id": event_id},
                )
            ).scalar_one() == "processed"
            await session.execute(text("delete from public.profiles where id=:id"), {"id": user_id})
            await session.commit()
    finally:
        await engine.dispose()
