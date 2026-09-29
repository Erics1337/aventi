"""Distributed fixed-window limits shared by Lambda instances."""

import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import text


async def enforce_limit(identity: str, maximum: int) -> None:
    from aventi_backend.db.session import open_db_session

    window = datetime.now(UTC).replace(second=0, microsecond=0)
    key = hashlib.sha256(identity.encode()).hexdigest()
    async with open_db_session() as session:
        count = await session.scalar(
            text("""
            insert into public.request_limits(key, window_start) values (:key,:window)
            on conflict(key,window_start) do update set count=request_limits.count+1
            returning count
        """),
            {"key": key, "window": window},
        )
        await session.commit()
    if count > maximum:
        raise HTTPException(429, "Request limit reached", headers={"Retry-After": "60"})
