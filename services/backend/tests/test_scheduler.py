from contextlib import asynccontextmanager

import pytest

from aventi_backend.worker import scheduler


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[dict] = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.statements.append({"sql": str(statement), "params": params or {}})

        class Result:
            def mappings(self):
                return self

            def one(self):
                return {"id": "11111111-1111-1111-1111-111111111111"}

        return Result()

    async def commit(self) -> None:
        self.commits += 1


class FakeWarmupService:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def enqueue_weekly_scans(
        self,
        *,
        limit: int = 200,
        scheduler_run_id: str | None = None,
    ) -> dict[str, int]:
        assert scheduler_run_id == "11111111-1111-1111-1111-111111111111"
        return {"markets": limit, "jobs_enqueued": min(limit, 2)}


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

    assert result == {
        "markets": 3,
        "jobs_enqueued": 2,
        "schedulerRunId": "11111111-1111-1111-1111-111111111111",
        "status": "ok",
    }


@pytest.mark.asyncio
async def test_scheduler_run_uses_requested_limit_column() -> None:
    fake_session = FakeSession()
    scheduler_run_id = await scheduler._create_scheduler_run(
        fake_session,  # type: ignore[arg-type]
        trigger_type="cron",
        limit=7,
    )

    assert scheduler_run_id == "11111111-1111-1111-1111-111111111111"
    assert '"limit"' in fake_session.statements[0]["sql"]
    assert "limit_count" not in fake_session.statements[0]["sql"]
    assert fake_session.statements[0]["params"]["limit"] == 7
