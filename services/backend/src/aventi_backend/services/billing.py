from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings


class BillingConfigurationError(RuntimeError):
    pass


class BillingIdentityError(ValueError):
    pass


class RevenueCatError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EntitlementState:
    is_premium: bool
    plan: str
    product_identifier: str | None = None
    valid_until: datetime | None = None
    status: str = "inactive"
    management_url: str | None = None

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "isPremium": self.is_premium,
            "plan": self.plan,
            "unlimitedSwipes": self.is_premium,
            "advancedFilters": self.is_premium,
            "travelMode": self.is_premium,
            "insiderTips": self.is_premium,
            "validUntil": self.valid_until,
            "productIdentifier": self.product_identifier,
            "status": self.status,
            "managementUrl": self.management_url,
        }


def require_permanent_user_id(value: str) -> str:
    """RevenueCat app user IDs are always the authenticated Supabase UUID.

    This intentionally rejects RevenueCat anonymous IDs and aliases. Allowing either
    would make purchases transferable between accounts outside Aventi's auth model.
    """
    if value.startswith("$RCAnonymousID:"):
        raise BillingIdentityError("Anonymous RevenueCat customers are not supported")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as exc:
        raise BillingIdentityError("RevenueCat appUserId must be a Supabase user UUID") from exc
    canonical = str(parsed)
    if value.lower() != canonical:
        raise BillingIdentityError("RevenueCat appUserId must be a canonical UUID")
    return canonical


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        # RevenueCat webhook timestamps are milliseconds.
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        if not cleaned:
            return None
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _latest(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if value is not None]
    return max(candidates) if candidates else None


class RevenueCatClient:
    base_url = "https://api.revenuecat.com/v1"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self._client = client

    async def _request(self, method: str, path: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.request(
                    method, f"{self.base_url}{path}", headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.request(
                        method, f"{self.base_url}{path}", headers=headers
                    )
        except httpx.HTTPError as exc:
            raise RevenueCatError("RevenueCat is unavailable") from exc
        return response

    async def get_subscriber(self, app_user_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/subscribers/{app_user_id}")
        if response.status_code == 404:
            return {"subscriber": {}}
        if response.is_error:
            raise RevenueCatError(f"RevenueCat subscriber lookup failed ({response.status_code})")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RevenueCatError("RevenueCat returned an invalid subscriber response")
        return payload

    async def delete_subscriber(self, app_user_id: str) -> None:
        response = await self._request("DELETE", f"/subscribers/{app_user_id}")
        if response.status_code not in {200, 201, 204, 404}:
            raise RevenueCatError(f"RevenueCat customer deletion failed ({response.status_code})")


class BillingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        revenuecat: RevenueCatClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        api_key = getattr(self.settings, "revenuecat_secret_key", None)
        self.revenuecat = revenuecat or (RevenueCatClient(api_key) if api_key else None)

    @property
    def entitlement_id(self) -> str:
        return str(getattr(self.settings, "revenuecat_entitlement_id", "premium") or "premium")

    def _product_is_allowed(self, product_id: str | None) -> bool:
        configured = {
            value
            for value in (
                getattr(self.settings, "revenuecat_monthly_product_id", None),
                getattr(self.settings, "revenuecat_annual_product_id", None),
            )
            if isinstance(value, str) and value
        }
        return not configured or product_id in configured

    def verify_webhook_authorization(self, authorization: str | None) -> None:
        expected = getattr(self.settings, "revenuecat_webhook_secret", None)
        if not expected:
            raise BillingConfigurationError("RevenueCat webhook authorization is not configured")
        supplied = authorization or ""
        # Accept the exact configured Authorization value. Also accept Bearer <secret>
        # when only the token itself was configured, which matches RevenueCat's UI.
        candidates = {str(expected), f"Bearer {expected}"}
        if not any(hmac.compare_digest(supplied, candidate) for candidate in candidates):
            raise BillingIdentityError("Invalid RevenueCat webhook authorization")

    def state_from_subscriber(
        self, payload: dict[str, Any], *, now: datetime | None = None
    ) -> EntitlementState:
        now = now or datetime.now(tz=UTC)
        subscriber = payload.get("subscriber")
        if not isinstance(subscriber, dict):
            subscriber = {}
        entitlements = subscriber.get("entitlements")
        if not isinstance(entitlements, dict):
            entitlements = {}
        entitlement = entitlements.get(self.entitlement_id)
        if not isinstance(entitlement, dict):
            entitlement = {}

        product_id = entitlement.get("product_identifier")
        if not isinstance(product_id, str):
            product_id = None
        expires_at = _parse_datetime(entitlement.get("expires_date"))
        explicit_grace_at = _parse_datetime(entitlement.get("grace_period_expires_date"))

        subscriptions = subscriber.get("subscriptions")
        if not isinstance(subscriptions, dict):
            subscriptions = {}
        subscription = subscriptions.get(product_id) if product_id else None
        if isinstance(subscription, dict):
            expires_at = _latest(expires_at, _parse_datetime(subscription.get("expires_date")))
            explicit_grace_at = _latest(
                explicit_grace_at,
                _parse_datetime(subscription.get("grace_period_expires_date")),
            )

        valid_until = _latest(expires_at, explicit_grace_at)
        # Aventi sells only expiring monthly/annual products. A missing expiration
        # is malformed provider state, never a lifetime entitlement.
        active = bool(valid_until and valid_until > now) and self._product_is_allowed(product_id)
        status = "active" if active else "expired"
        if product_id and not self._product_is_allowed(product_id):
            status = "invalid_product"
        if (
            active
            and explicit_grace_at
            and explicit_grace_at > now
            and (expires_at is None or expires_at <= now)
        ):
            status = "grace_period"

        management_url = subscriber.get("management_url")
        return EntitlementState(
            is_premium=active,
            plan="unlimited" if active else "free",
            product_identifier=product_id,
            valid_until=valid_until,
            status=status,
            management_url=management_url if isinstance(management_url, str) else None,
        )

    async def reconcile(self, *, authenticated_user_id: str, app_user_id: str) -> dict[str, Any]:
        user_id = require_permanent_user_id(authenticated_user_id)
        if require_permanent_user_id(app_user_id) != user_id:
            raise BillingIdentityError("Purchases cannot be transferred to another account")
        if self.revenuecat is None:
            raise BillingConfigurationError("RevenueCat is not configured")

        await self.session.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": user_id}
        )
        try:
            await self._ensure_active_profile(user_id)
            state = await self._fetch_authoritative_state(user_id)
            await self._write_state(
                user_id=user_id,
                state=state,
                source="revenuecat_api",
                source_event_at=datetime.now(tz=UTC),
                original_app_user_id=user_id,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        response = state.as_api_dict()
        response["purchasesEnabled"] = bool(getattr(self.settings, "purchases_enabled", False))
        return response

    async def get_entitlements(self, *, user_id: str) -> dict[str, Any]:
        user_id = require_permanent_user_id(user_id)
        if getattr(self.settings, "purchases_enabled", False):
            try:
                return await self.reconcile(authenticated_user_id=user_id, app_user_id=user_id)
            except RevenueCatError:
                # A short provider outage must not revoke a still-time-bounded cached
                # entitlement. Expired or malformed cache entries still fail closed.
                row = await self._cached_state(user_id)
                response = row.as_api_dict()
                response["purchasesEnabled"] = True
                return response
        row = await self._cached_state(user_id)
        response = row.as_api_dict()
        response["purchasesEnabled"] = False
        return response

    async def process_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("RevenueCat webhook payload requires an event")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("RevenueCat webhook event id is required")
        event_type = str(event.get("type") or "UNKNOWN").upper()
        if event_type == "TRANSFER":
            await self._record_rejected_event(event_id, event_type, "transfers_not_supported")
            return {"ok": True, "eventId": event_id, "ignored": "transfers_not_supported"}

        raw_app_user_id = event.get("app_user_id")
        if not isinstance(raw_app_user_id, str):
            await self._record_rejected_event(event_id, event_type, "missing_app_user_id")
            return {"ok": True, "eventId": event_id, "ignored": "missing_app_user_id"}
        try:
            user_id = require_permanent_user_id(raw_app_user_id)
        except BillingIdentityError:
            await self._record_rejected_event(event_id, event_type, "non_permanent_identity")
            return {"ok": True, "eventId": event_id, "ignored": "non_permanent_identity"}
        original_id = event.get("original_app_user_id")
        if isinstance(original_id, str) and original_id != user_id:
            await self._record_rejected_event(event_id, event_type, "original_identity_mismatch")
            return {"ok": True, "eventId": event_id, "ignored": "original_identity_mismatch"}
        event_at = _parse_datetime(event.get("event_timestamp_ms")) or datetime.now(tz=UTC)

        await self.session.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": user_id}
        )
        if not await self._profile_is_active(user_id):
            await self._record_rejected_event(event_id, event_type, "account_unavailable")
            return {"ok": True, "eventId": event_id, "ignored": "account_unavailable"}
        inserted = await self.session.execute(
            text(
                """
                insert into public.revenuecat_events
                  (event_id, user_id, event_type, event_at, payload, processing_status)
                values (
                  :event_id, :user_id, :event_type, :event_at,
                  cast(:payload as jsonb), 'received'
                )
                on conflict (event_id) do nothing
                returning event_id
                """
            ),
            {
                "event_id": event_id,
                "user_id": user_id,
                "event_type": event_type,
                "event_at": event_at,
                "payload": __import__("json").dumps(payload),
            },
        )
        if inserted.scalar_one_or_none() is None:
            await self.session.commit()
            return {"ok": True, "eventId": event_id, "duplicate": True}

        if self.revenuecat is None:
            await self.session.rollback()
            raise BillingConfigurationError("RevenueCat is not configured")
        try:
            # Notification payloads are signals, not entitlement state. Fetching the
            # current customer under the user lock makes cancellation/refund and
            # reordered delivery converge to RevenueCat's present truth.
            state = await self._fetch_authoritative_state(user_id)
            await self._write_state(
                user_id=user_id,
                state=state,
                source="revenuecat_webhook_reconcile",
                source_event_at=datetime.now(tz=UTC),
                original_app_user_id=user_id,
            )
            await self.session.execute(
                text(
                    "update public.revenuecat_events "
                    "set processing_status='processed', processed_at=now() "
                    "where event_id=:event_id"
                ),
                {"event_id": event_id},
            )
            await self.session.commit()
        except BillingIdentityError:
            await self.session.rollback()
            await self._record_rejected_event(
                event_id, event_type, "provider_original_identity_mismatch"
            )
            return {
                "ok": True,
                "eventId": event_id,
                "ignored": "provider_original_identity_mismatch",
            }
        except Exception:
            # Do not retain the dedup row on provider failure. A non-2xx response lets
            # RevenueCat retry this exact event after the transient outage clears.
            await self.session.rollback()
            raise
        return {"ok": True, "eventId": event_id, "entitlements": state.as_api_dict()}

    async def _fetch_authoritative_state(self, user_id: str) -> EntitlementState:
        if self.revenuecat is None:
            raise BillingConfigurationError("RevenueCat is not configured")
        payload = await self.revenuecat.get_subscriber(user_id)
        subscriber = payload.get("subscriber")
        original_id = (
            subscriber.get("original_app_user_id") if isinstance(subscriber, dict) else None
        )
        if isinstance(original_id, str) and original_id != user_id:
            raise BillingIdentityError(
                "RevenueCat customer does not originate from the authenticated account"
            )
        return self.state_from_subscriber(payload)

    async def _profile_is_active(self, user_id: str) -> bool:
        result = await self.session.execute(
            text(
                """
                select exists(select 1 from public.profiles where id=:user_id)
                  and not exists(select 1 from public.account_deletions where user_id=:user_id)
                """
            ),
            {"user_id": user_id},
        )
        return bool(result.scalar_one())

    async def _ensure_active_profile(self, user_id: str) -> None:
        if not await self._profile_is_active(user_id):
            raise BillingIdentityError("The authenticated account is unavailable")

    async def _cached_state(self, user_id: str) -> EntitlementState:
        result = await self.session.execute(
            text(
                """
                select is_premium, plan, product_identifier, valid_until, entitlement_status,
                       management_url
                from public.premium_entitlements where user_id=:user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        if row is None:
            return EntitlementState(False, "free")
        valid_until = row["valid_until"]
        is_premium = bool(
            row["is_premium"]
            and valid_until is not None
            and valid_until > datetime.now(tz=UTC)
            and self._product_is_allowed(row["product_identifier"])
        )
        cached_status = row["entitlement_status"] or "inactive"
        if not is_premium:
            cached_status = "expired" if valid_until is not None else "invalid_expiration"
        return EntitlementState(
            is_premium=is_premium,
            plan="unlimited" if is_premium else "free",
            product_identifier=row["product_identifier"],
            valid_until=valid_until,
            status=cached_status,
            management_url=row["management_url"],
        )

    async def _write_state(
        self,
        *,
        user_id: str,
        state: EntitlementState,
        source: str,
        source_event_at: datetime,
        original_app_user_id: str,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into public.subscription_accounts
                  (user_id, revenuecat_app_user_id, original_app_user_id, updated_at)
                values (:user_id, :app_user_id, :original_app_user_id, now())
                on conflict (user_id) do update set
                  revenuecat_app_user_id=excluded.revenuecat_app_user_id,
                  original_app_user_id=excluded.original_app_user_id,
                  updated_at=now()
                """
            ),
            {
                "user_id": user_id,
                "app_user_id": user_id,
                "original_app_user_id": original_app_user_id,
            },
        )
        await self.session.execute(
            text(
                """
                insert into public.premium_entitlements
                  (user_id, plan, is_premium, source, valid_until, product_identifier,
                   entitlement_status, management_url, last_event_at, updated_at)
                values (:user_id, :plan, :is_premium, :source, :valid_until, :product_identifier,
                        :status, :management_url, :last_event_at, now())
                on conflict (user_id) do update set
                  plan=excluded.plan,
                  is_premium=excluded.is_premium,
                  source=excluded.source,
                  valid_until=excluded.valid_until,
                  product_identifier=excluded.product_identifier,
                  entitlement_status=excluded.entitlement_status,
                  management_url=excluded.management_url,
                  last_event_at=excluded.last_event_at,
                  updated_at=now()
                """
            ),
            {
                "user_id": user_id,
                "plan": state.plan,
                "is_premium": state.is_premium,
                "source": source,
                "valid_until": state.valid_until,
                "product_identifier": state.product_identifier,
                "status": state.status,
                "management_url": state.management_url,
                "last_event_at": source_event_at,
            },
        )

    async def _record_rejected_event(self, event_id: str, event_type: str, reason: str) -> None:
        await self.session.execute(
            text(
                """
                insert into public.revenuecat_events
                  (event_id, event_type, event_at, payload, processing_status,
                   error_message, processed_at)
                values (
                  :event_id, :event_type, now(), cast(:payload as jsonb),
                  'rejected', :reason, now()
                )
                on conflict (event_id) do nothing
                """
            ),
            {
                "event_id": event_id,
                "event_type": event_type,
                # Rejected/unknown identities retain only the provider event ID and
                # type for deduplication. Do not persist aliases or other PII.
                "payload": "{}",
                "reason": reason,
            },
        )
        await self.session.commit()
