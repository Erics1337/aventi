from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MarketDescriptor:
    key: str
    city: str
    state: str | None
    country: str
    center_latitude: float | None = None
    center_longitude: float | None = None
    heat_tier: str = "cold"


def build_market_key(city: str, state: str | None = None, country: str | None = None) -> str:
    normalized_city = city.strip().lower()
    normalized_state = (state or "").strip().lower()
    normalized_country = (country or "US").strip().lower()
    return f"{normalized_city}|{normalized_state}|{normalized_country}"


def build_market_descriptor(
    *,
    city: str | None,
    state: str | None = None,
    country: str | None = None,
    center_latitude: float | None = None,
    center_longitude: float | None = None,
) -> MarketDescriptor | None:
    if not city or not city.strip():
        return None
    normalized_city = city.strip()
    normalized_state = state.strip() if state and state.strip() else None
    normalized_country = country.strip().upper() if country and country.strip() else "US"
    return MarketDescriptor(
        key=build_market_key(normalized_city, normalized_state, normalized_country),
        city=normalized_city,
        state=normalized_state,
        country=normalized_country,
        center_latitude=center_latitude,
        center_longitude=center_longitude,
    )


def market_from_payload(payload: dict[str, Any]) -> MarketDescriptor | None:
    market_key = payload.get("marketKey")
    market_city = payload.get("marketCity") or payload.get("city")
    if not isinstance(market_city, str) or not market_city.strip():
        return None
    if not isinstance(market_key, str) or not market_key.strip():
        return build_market_descriptor(
            city=market_city,
            state=payload.get("marketState"),
            country=payload.get("marketCountry"),
            center_latitude=coerce_float(payload.get("centerLatitude")),
            center_longitude=coerce_float(payload.get("centerLongitude")),
        )
    return MarketDescriptor(
        key=market_key,
        city=market_city.strip(),
        state=optional_str(payload.get("marketState")),
        country=optional_str(payload.get("marketCountry")) or "US",
        center_latitude=coerce_float(payload.get("centerLatitude")),
        center_longitude=coerce_float(payload.get("centerLongitude")),
    )


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
