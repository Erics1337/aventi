from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings


class DestinationConfigurationError(RuntimeError):
    pass


class DestinationProviderError(RuntimeError):
    pass


class DestinationPremiumRequiredError(PermissionError):
    pass


def normalize_destination_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _component(components: list[dict[str, Any]], *types: str, short: bool = False) -> str | None:
    for wanted in types:
        for component in components:
            component_types = component.get("types")
            if isinstance(component_types, list) and wanted in component_types:
                key = "short_name" if short else "long_name"
                value = component.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


class GoogleDestinationClient:
    def __init__(
        self,
        *,
        geocoding_key: str,
        timezone_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.geocoding_key = geocoding_key
        self.timezone_key = timezone_key
        self._client = client

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DestinationProviderError("Google location services are unavailable") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise DestinationProviderError("Google location services returned invalid data")
        return payload

    async def geocode(self, query: str) -> list[dict[str, Any]]:
        payload = await self._get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            {
                "address": query,
                "components": "country:US",
                "region": "us",
                "key": self.geocoding_key,
            },
        )
        status = payload.get("status")
        if status == "ZERO_RESULTS":
            return []
        if status != "OK":
            raise DestinationProviderError(f"Google Geocoding failed ({status or 'unknown'})")
        results = payload.get("results")
        return (
            [item for item in results if isinstance(item, dict)]
            if isinstance(results, list)
            else []
        )

    async def timezone(self, latitude: float, longitude: float) -> str:
        payload = await self._get(
            "https://maps.googleapis.com/maps/api/timezone/json",
            {
                "location": f"{latitude},{longitude}",
                "timestamp": int(datetime.now(tz=UTC).timestamp()),
                "key": self.timezone_key,
            },
        )
        if payload.get("status") != "OK" or not isinstance(payload.get("timeZoneId"), str):
            raise DestinationProviderError("Google Time Zone could not resolve this destination")
        return str(payload["timeZoneId"])


class DestinationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        google: GoogleDestinationClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        geocoding_key = getattr(self.settings, "google_geocoding_api_key", None)
        timezone_key = getattr(self.settings, "google_timezone_api_key", None)
        self.google = google or (
            GoogleDestinationClient(
                geocoding_key=geocoding_key,
                timezone_key=timezone_key,
            )
            if geocoding_key and timezone_key
            else None
        )

    async def require_premium(self, user_id: str) -> None:
        result = await self.session.execute(
            text(
                """
                select coalesce(is_premium, false)
                  and valid_until > now()
                from public.premium_entitlements where user_id=:user_id
                """
            ),
            {"user_id": user_id},
        )
        if result.scalar_one_or_none() is not True:
            raise DestinationPremiumRequiredError(
                "Aventi Unlimited is required for destination search"
            )

    async def search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        normalized = normalize_destination_query(query)
        if len(normalized) < 2:
            raise ValueError("Destination query must contain at least 2 characters")
        limit = max(1, min(limit, 10))
        cached = await self._cached_search(normalized, limit)
        if cached:
            return {"items": cached, "cached": True}
        if self.google is None:
            raise DestinationConfigurationError(
                "Separate Google Geocoding and Time Zone API keys are required"
            )

        await self._reserve_budget(normalized)
        raw_results = await self.google.geocode(query)
        items: list[dict[str, Any]] = []
        for raw in raw_results:
            item = await self._canonicalize(raw)
            if item is None:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        await self._store(normalized, items)
        return {"items": items, "cached": False}

    async def get(self, destination_id: str) -> dict[str, Any] | None:
        result = await self.session.execute(
            text(
                """
                select id::text, label, city, state, country, latitude, longitude, timezone
                from public.destinations where id=:id and country='US'
                """
            ),
            {"id": destination_id},
        )
        row = result.mappings().first()
        return self._row_to_item(row) if row else None

    async def _cached_search(self, normalized: str, limit: int) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                select d.id::text, d.label, d.city, d.state, d.country,
                       d.latitude, d.longitude, d.timezone
                from public.destination_queries q
                join public.destinations d on d.id=q.destination_id
                where q.normalized_query=:query
                  and q.updated_at > now() - interval '30 days'
                  and d.country='US'
                order by q.rank
                limit :limit
                """
            ),
            {"query": normalized, "limit": limit},
        )
        return [self._row_to_item(row) for row in result.mappings().all()]

    async def _canonicalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        place_id = raw.get("place_id")
        components = raw.get("address_components")
        geometry = raw.get("geometry")
        if (
            not isinstance(place_id, str)
            or not isinstance(components, list)
            or not isinstance(geometry, dict)
        ):
            return None
        country = _component(components, "country", short=True)
        if country != "US":
            return None
        location = geometry.get("location")
        if not isinstance(location, dict):
            return None
        try:
            latitude = float(location["lat"])
            longitude = float(location["lng"])
        except (KeyError, TypeError, ValueError):
            return None
        city = _component(
            components,
            "locality",
            "postal_town",
            "administrative_area_level_2",
            "administrative_area_level_1",
        )
        state = _component(components, "administrative_area_level_1", short=True)
        if not city or not state:
            return None
        await self._reserve_budget(f"timezone:{place_id}")
        timezone = await self.google.timezone(latitude, longitude) if self.google else None
        label = raw.get("formatted_address")
        if not isinstance(label, str) or not label.strip():
            label = f"{city}, {state}, USA"
        return {
            "id": str(uuid5(NAMESPACE_URL, f"aventi:google-destination:{place_id}")),
            "providerPlaceId": place_id,
            "label": label,
            "city": city,
            "state": state,
            "country": "US",
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
        }

    async def _store(self, normalized: str, items: list[dict[str, Any]]) -> None:
        await self.session.execute(
            text("delete from public.destination_queries where normalized_query=:query"),
            {"query": normalized},
        )
        for rank, item in enumerate(items):
            await self.session.execute(
                text(
                    """
                    insert into public.destinations
                      (id, provider, provider_place_id, label, city, state, country,
                       latitude, longitude, timezone, updated_at)
                    values (:id, 'google', :provider_place_id, :label, :city, :state, 'US',
                            :latitude, :longitude, :timezone, now())
                    on conflict (provider, provider_place_id) do update set
                      label=excluded.label, city=excluded.city, state=excluded.state,
                      latitude=excluded.latitude, longitude=excluded.longitude,
                      timezone=excluded.timezone, updated_at=now()
                    """
                ),
                {
                    "id": item["id"],
                    "provider_place_id": item["providerPlaceId"],
                    "label": item["label"],
                    "city": item["city"],
                    "state": item["state"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "timezone": item["timezone"],
                },
            )
            await self.session.execute(
                text(
                    """
                    insert into public.destination_queries
                      (normalized_query, destination_id, rank, updated_at)
                    values (:query, :destination_id, :rank, now())
                    on conflict (normalized_query, destination_id) do update set
                      rank=excluded.rank, updated_at=now()
                    """
                ),
                {"query": normalized, "destination_id": item["id"], "rank": rank},
            )
        await self.session.commit()

    async def _reserve_budget(self, operation: str) -> None:
        # BudgetManager is shared with discovery/jobs. Importing lazily keeps this
        # service usable in migrations and unit tests before provider configuration.
        try:
            from aventi_backend.services.budgets import BudgetManager
        except ImportError:  # pragma: no cover - only during staggered deployments
            return
        try:
            await BudgetManager(self.session).reserve(
                "geocoding", units=1, operation=f"destination:{operation}"
            )
        except Exception as exc:
            from aventi_backend.services.budgets import BudgetError

            if isinstance(exc, BudgetError):
                raise DestinationConfigurationError(str(exc)) from exc
            raise

    @staticmethod
    def _row_to_item(row: Any) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "label": row["label"],
            "city": row["city"],
            "state": row["state"],
            "country": row["country"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "timezone": row["timezone"],
        }
