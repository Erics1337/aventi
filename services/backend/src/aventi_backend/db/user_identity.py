from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5


def canonical_user_uuid(user_id: str) -> str:
    try:
        return str(UUID(user_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"aventi:user:{user_id}"))


def canonical_event_uuid(event_id: str) -> str:
    try:
        return str(UUID(event_id))
    except ValueError as exc:
        raise ValueError(f"Invalid eventId: {event_id!r}") from exc


def utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end
