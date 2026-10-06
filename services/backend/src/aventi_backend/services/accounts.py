from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings
from aventi_backend.services.billing import (
    BillingConfigurationError,
    RevenueCatClient,
    require_permanent_user_id,
)


class AccountDeletionError(RuntimeError):
    pass


class SupabaseAdminClient:
    def __init__(
        self,
        *,
        url: str,
        secret_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.secret_key = secret_key
        self._client = client

    async def delete_user(self, user_id: str) -> None:
        headers = {
            "apikey": self.secret_key,
            "Authorization": f"Bearer {self.secret_key}",
        }
        target = f"{self.url}/auth/v1/admin/users/{user_id}"
        try:
            if self._client is not None:
                response = await self._client.delete(target, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.delete(target, headers=headers)
        except httpx.HTTPError as exc:
            raise AccountDeletionError("Supabase Auth is unavailable") from exc
        # A missing user means the deletion stage already completed.
        if response.status_code not in {200, 204, 404}:
            raise AccountDeletionError(f"Supabase Auth deletion failed ({response.status_code})")


class AccountDeletionService:
    """Durable, retry-safe account erasure orchestration.

    The request row has no profile foreign key, so it remains as a tombstone after
    application data is removed. The migration's profile trigger then prevents a
    still-valid JWT from bootstrapping the deleted account again.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        revenuecat: RevenueCatClient | None = None,
        supabase: SupabaseAdminClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        revenuecat_key = getattr(self.settings, "revenuecat_secret_key", None)
        self.revenuecat = revenuecat or (
            RevenueCatClient(revenuecat_key) if revenuecat_key else None
        )
        supabase_url = getattr(self.settings, "supabase_url", None)
        supabase_key = getattr(self.settings, "supabase_secret_key", None)
        self.supabase = supabase or (
            SupabaseAdminClient(url=supabase_url, secret_key=supabase_key)
            if supabase_url and supabase_key
            else None
        )

    async def get_status(self, user_id: str) -> dict[str, Any] | None:
        user_id = require_permanent_user_id(user_id)
        result = await self.session.execute(
            text(
                """
                select status, current_stage, stages, last_error, requested_at,
                       updated_at, completed_at
                from public.account_deletions where user_id=:user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        return self._serialize(row) if row else None

    async def request_deletion(self, user_id: str) -> dict[str, Any]:
        user_id = require_permanent_user_id(user_id)
        await self.session.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"account-deletion:{user_id}"},
        )
        await self.session.execute(
            text(
                """
                insert into public.account_deletions
                  (user_id, status, current_stage, stages, requested_at, updated_at)
                values (:user_id, 'pending', 'revenuecat', '{}'::jsonb, now(), now())
                on conflict (user_id) do nothing
                """
            ),
            {"user_id": user_id},
        )
        await self.session.commit()

        run_token = str(uuid4())
        claimed = await self.session.execute(
            text("""
                update public.account_deletions
                set status='processing', current_stage='revenuecat', run_token=:run_token,
                    updated_at=now(), last_error=null
                where user_id=:user_id and (
                    status in ('pending', 'failed') or
                    (status='processing' and updated_at < now() - interval '10 minutes'))
                returning user_id
            """),
            {"user_id": user_id, "run_token": run_token},
        )
        owns_run = claimed.scalar_one_or_none() is not None
        await self.session.commit()
        if not owns_run:
            current = await self.get_status(user_id)
            if current is None:
                raise AccountDeletionError("Deletion status was unexpectedly lost")
            return current

        try:
            await self._run_revenuecat_stage(user_id)
            await self._mark_stage(
                user_id, "revenuecat", "completed", next_stage="app_data", run_token=run_token
            )

            await self.session.execute(
                text("delete from public.profiles where id=:user_id"), {"user_id": user_id}
            )
            await self.session.commit()
            await self._mark_stage(
                user_id, "app_data", "completed", next_stage="supabase_auth", run_token=run_token
            )

            if self.supabase is None:
                raise BillingConfigurationError("Supabase admin credentials are not configured")
            await self.supabase.delete_user(user_id)
            await self._mark_stage(
                user_id, "supabase_auth", "completed", next_stage="done", run_token=run_token
            )
            await self.session.execute(
                text(
                    """
                    update public.account_deletions
                    set status='completed', current_stage='done', completed_at=now(),
                        updated_at=now(), last_error=null
                    where user_id=:user_id and run_token=:run_token and status='processing'
                    """
                ),
                {"user_id": user_id, "run_token": run_token},
            )
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            await self._set_failed(user_id, str(exc), run_token=run_token)
            raise AccountDeletionError(str(exc)) from exc

        result = await self.get_status(user_id)
        if result is None:  # pragma: no cover - protected by durable request row
            raise AccountDeletionError("Deletion status was unexpectedly lost")
        return result

    async def _run_revenuecat_stage(self, user_id: str) -> None:
        if self.revenuecat is None:
            if getattr(self.settings, "purchases_enabled", False):
                raise BillingConfigurationError("RevenueCat is not configured")
            return
        await self.revenuecat.delete_subscriber(user_id)

    async def _mark_stage(
        self, user_id: str, stage: str, stage_status: str, *, next_stage: str, run_token: str
    ) -> None:
        result = await self.session.execute(
            text("select stages from public.account_deletions where user_id=:user_id"),
            {"user_id": user_id},
        )
        stages = dict(result.scalar_one_or_none() or {})
        stages[stage] = {
            "status": stage_status,
            "completedAt": datetime.now(tz=UTC).isoformat(),
        }
        updated = await self.session.execute(
            text(
                """
                update public.account_deletions
                set stages=cast(:stages as jsonb), current_stage=:next_stage,
                    updated_at=now(), last_error=null
                where user_id=:user_id and run_token=:run_token and status='processing'
                returning user_id
                """
            ),
            {
                "user_id": user_id,
                "stages": json.dumps(stages),
                "next_stage": next_stage,
                "run_token": run_token,
            },
        )
        if updated.scalar_one_or_none() is None:
            raise AccountDeletionError("Deletion processing lease was lost")
        await self.session.commit()

    async def _set_failed(self, user_id: str, error: str, *, run_token: str) -> None:
        await self.session.execute(
            text(
                """
                update public.account_deletions
                set status='failed', last_error=:error, updated_at=now()
                where user_id=:user_id and run_token=:run_token and status='processing'
                """
            ),
            {"user_id": user_id, "error": error[:1000], "run_token": run_token},
        )
        await self.session.commit()

    @staticmethod
    def _serialize(row: Any) -> dict[str, Any]:
        def iso(value: Any) -> str | None:
            return value.isoformat() if isinstance(value, datetime) else None

        return {
            "status": row["status"],
            "currentStage": row["current_stage"],
            "stages": dict(row["stages"] or {}),
            "lastError": row["last_error"],
            "requestedAt": iso(row["requested_at"]),
            "updatedAt": iso(row["updated_at"]),
            "completedAt": iso(row["completed_at"]),
        }
