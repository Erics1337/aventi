from math import asin, cos, radians, sin, sqrt
from typing import NamedTuple

from fastapi import APIRouter

from aventi_backend.models.schemas import LocationResolvePayload, LocationResolveResponse

router = APIRouter()

_MARKET_MATCH_RADIUS_MILES = 50.0


class KnownMarket(NamedTuple):
    city: str
    state: str | None
    country: str
    timezone: str
    latitude: float
    longitude: float


_KNOWN_MARKETS = (
    KnownMarket("New York", "NY", "US", "America/New_York", 40.7128, -74.0060),
    KnownMarket("Los Angeles", "CA", "US", "America/Los_Angeles", 34.0522, -118.2437),
    KnownMarket("San Francisco", "CA", "US", "America/Los_Angeles", 37.7749, -122.4194),
    KnownMarket("Denver", "CO", "US", "America/Denver", 39.7392, -104.9903),
    KnownMarket("Miami", "FL", "US", "America/New_York", 25.7617, -80.1918),
    KnownMarket("Chicago", "IL", "US", "America/Chicago", 41.8781, -87.6298),
    KnownMarket("Austin", "TX", "US", "America/Chicago", 30.2672, -97.7431),
    KnownMarket("Seattle", "WA", "US", "America/Los_Angeles", 47.6062, -122.3321),
    KnownMarket("Toronto", "ON", "CA", "America/Toronto", 43.6532, -79.3832),
    KnownMarket("Vancouver", "BC", "CA", "America/Vancouver", 49.2827, -123.1207),
)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 3958.7613 * 2 * asin(sqrt(a))


def _nearest_known_market(latitude: float, longitude: float) -> KnownMarket | None:
    nearest = min(
        _KNOWN_MARKETS,
        key=lambda market: _haversine_miles(
            latitude,
            longitude,
            market.latitude,
            market.longitude,
        ),
    )
    distance = _haversine_miles(latitude, longitude, nearest.latitude, nearest.longitude)
    return nearest if distance <= _MARKET_MATCH_RADIUS_MILES else None


def _timezone_from_coordinates(latitude: float, longitude: float) -> str | None:
    try:
        from timezonefinder import TimezoneFinder
    except ImportError:
        return None

    return TimezoneFinder().timezone_at(lat=latitude, lng=longitude)


def _format_market(market: KnownMarket | None) -> str | None:
    if market is None:
        return None
    region = f", {market.state}" if market.state else ""
    return f"{market.city}{region}, {market.country}"


@router.post("/resolve", response_model=LocationResolveResponse)
async def resolve_location(payload: LocationResolvePayload) -> LocationResolveResponse:
    market = _nearest_known_market(payload.latitude, payload.longitude)
    timezone = market.timezone if market else _timezone_from_coordinates(
        payload.latitude,
        payload.longitude,
    )

    return LocationResolveResponse(
        latitude=payload.latitude,
        longitude=payload.longitude,
        city=market.city if market else None,
        state=market.state if market else None,
        country=market.country if market else None,
        timezone=timezone,
        formattedAddress=_format_market(market),
    )
