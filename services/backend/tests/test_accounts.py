import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aventi_backend.services.accounts import (
    AccountDeletionError,
    AccountDeletionService,
    SupabaseAdminClient,
)
from aventi_backend.services.billing import RevenueCatClient, RevenueCatError

DATABASE_URL = os.environ.get("AVENTI_TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_supabase_delete_is_idempotent_for_missing_user():
    user_id = str(uuid4())

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "service-secret"
        assert request.headers["authorization"] == "Bearer service-secret"
        assert request.url.path.endswith(user_id)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SupabaseAdminClient(
            url="https://project.supabase.co",
            secret_key="service-secret",
            client=client,
        )
        await service.delete_user(user_id)


@pytest.mark.asyncio
async def test_supabase_delete_surfaces_provider_failure():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = SupabaseAdminClient(
            url="https://project.supabase.co",
            secret_key="service-secret",
            client=client,
        )
        with pytest.raises(AccountDeletionError):
            await service.delete_user(str(uuid4()))


@pytest.mark.asyncio
async def test_revenuecat_delete_accepts_already_deleted_customer():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.headers["authorization"] == "Bearer rc-secret"
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await RevenueCatClient("rc-secret", client=client).delete_subscriber(str(uuid4()))


@pytest.mark.asyncio
async def test_revenuecat_delete_rejects_unexpected_status():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RevenueCatError):
            await RevenueCatClient("bad", client=client).delete_subscriber(str(uuid4()))


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_account_deletion_resumes_after_external_stage_failure():
    user_id = str(uuid4())

    class FakeRevenueCat:
        def __init__(self):
            self.calls = 0

        async def delete_subscriber(self, requested_user_id):
            assert requested_user_id == user_id
            self.calls += 1

    class FakeSupabase:
        def __init__(self):
            self.fail = True
            self.calls = 0

        async def delete_user(self, requested_user_id):
            assert requested_user_id == user_id
            self.calls += 1
            if self.fail:
                raise AccountDeletionError("temporary auth failure")

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    revenuecat = FakeRevenueCat()
    supabase = FakeSupabase()
    try:
        async with sessions() as session:
            await session.execute(
                text("insert into public.profiles (id, email) values (:id, :email)"),
                {"id": user_id, "email": "deletion-test@example.com"},
            )
            await session.execute(
                text("insert into public.user_preferences (user_id) values (:id)"),
                {"id": user_id},
            )
            await session.commit()
            service = AccountDeletionService(
                session,
                settings=SimpleNamespace(
                    revenuecat_secret_key=None,
                    supabase_url=None,
                    supabase_secret_key=None,
                    purchases_enabled=True,
                ),
                revenuecat=revenuecat,
                supabase=supabase,
            )
            with pytest.raises(AccountDeletionError):
                await service.request_deletion(user_id)
            failed = await service.get_status(user_id)
            assert failed["status"] == "failed"
            assert (
                await session.execute(
                    text("select count(*) from public.profiles where id=:id"), {"id": user_id}
                )
            ).scalar_one() == 0

            supabase.fail = False
            completed = await service.request_deletion(user_id)
            assert completed["status"] == "completed"
            assert revenuecat.calls == 2
            assert supabase.calls == 2

            # Tombstone survives profile cascade and the trigger blocks bootstrap.
            with pytest.raises(DBAPIError):
                await session.execute(
                    text("insert into public.profiles (id, email) values (:id, :email)"),
                    {"id": user_id, "email": "should-not-return@example.com"},
                )
            await session.rollback()
            await session.execute(
                text("delete from public.account_deletions where user_id=:id"), {"id": user_id}
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL, reason="Requires disposable migrated database")
async def test_concurrent_deletion_and_stale_failure_cannot_overwrite_completion():
    import asyncio

    user_id = str(uuid4())
    entered, release = asyncio.Event(), asyncio.Event()

    class RevenueCat:
        calls = 0

        async def delete_subscriber(self, _user_id):
            self.calls += 1
            entered.set()
            await release.wait()

    class Supabase:
        async def delete_user(self, _user_id):
            pass

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    provider = RevenueCat()
    settings = SimpleNamespace(
        revenuecat_secret_key=None,
        supabase_url=None,
        supabase_secret_key=None,
        purchases_enabled=True,
    )
    try:
        async with sessions() as first, sessions() as second:
            a = AccountDeletionService(
                first, settings=settings, revenuecat=provider, supabase=Supabase()
            )
            b = AccountDeletionService(
                second, settings=settings, revenuecat=provider, supabase=Supabase()
            )
            pending = asyncio.create_task(a.request_deletion(user_id))
            await asyncio.wait_for(entered.wait(), timeout=5)
            try:
                duplicate = await b.request_deletion(user_id)
                assert duplicate["status"] == "processing"
                assert provider.calls == 1
            finally:
                release.set()
            assert (await pending)["status"] == "completed"
            await b._set_failed(user_id, "late stale failure", run_token=str(uuid4()))
            assert (await b.get_status(user_id))["status"] == "completed"
            await second.execute(
                text("delete from public.account_deletions where user_id=:id"), {"id": user_id}
            )
            await second.commit()
    finally:
        await engine.dispose()
