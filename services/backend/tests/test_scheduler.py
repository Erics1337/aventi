from contextlib import asynccontextmanager

import pytest

from aventi_backend.worker import scheduler


class FakeSession:
    pass


class FakeWarmupService:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def enqueue_weekly_scans(self, *, limit: int = 200) -> dict[str, int]:
        return {"marketsScanned": limit, "jobsEnqueued": min(limit, 2)}


def _session_factory():
    @asynccontextmanager
    async def _session():
        yield FakeSession()

    return _session


def test_parse_limit_defaults_invalid_values() -> None:
    assert scheduler._parse_limit({}) == 200
    assert scheduler._parse_limit({"limit": "bad"}) == 200
    assert scheduler._parse_limit({"limit": None}) == 200


def test_parse_limit_accepts_eventbridge_override() -> None:
    assert scheduler._parse_limit({"limit": "25"}) == 25
    assert scheduler._parse_limit({"limit": 5}) == 5


@pytest.mark.asyncio
async def test_run_returns_scheduler_fanout_shape() -> None:
    result = await scheduler._run(
        3,
        session_factory=_session_factory(),
        warmup_service_factory=lambda session: FakeWarmupService(session),  # type: ignore[arg-type, return-value]
    )

    assert result == {"marketsScanned": 3, "jobsEnqueued": 2, "status": "ok"}
