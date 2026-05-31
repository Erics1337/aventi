from __future__ import annotations

from types import SimpleNamespace

import pytest

from aventi_backend.api.routes import admin
from aventi_backend.api.routes.admin import (
    SmokeLimitBody,
    _feed_diagnostic,
    _pipeline_trace_steps,
    _queue_attributes,
    _retention_dashboard,
)


def test_pipeline_trace_steps_explain_market_scan_progress() -> None:
    steps = _pipeline_trace_steps(
        {
            "status": "succeeded",
            "ingest_run_id": "ingest-1",
            "discovered_count": 4,
            "inserted_count": 2,
            "result": {"verificationJobsEnqueued": 2, "imageJobsEnqueued": 1},
        }
    )

    assert steps == [
        {"label": "Queued", "status": "complete"},
        {"label": "Processing", "status": "complete"},
        {"label": "Scan complete", "status": "complete"},
        {"label": "Ingest run created", "status": "complete"},
        {"label": "Events discovered", "status": "complete"},
        {"label": "Events inserted", "status": "complete"},
        {"label": "Verification jobs queued", "status": "complete"},
        {"label": "Image jobs queued", "status": "complete"},
        {"label": "Feed inventory updated", "status": "complete"},
    ]


def test_pipeline_trace_reads_nested_ingest_image_jobs() -> None:
    steps = _pipeline_trace_steps(
        {
            "status": "succeeded",
            "ingest_run_id": "ingest-1",
            "discovered_count": 4,
            "inserted_count": 2,
            "result": {"ingest": {"imageJobsEnqueued": 1}},
        }
    )

    assert steps[7] == {"label": "Image jobs queued", "status": "complete"}


def test_pipeline_trace_marks_failed_scan() -> None:
    steps = _pipeline_trace_steps(
        {
            "status": "failed",
            "ingest_run_id": None,
            "discovered_count": 0,
            "inserted_count": 0,
            "result": {},
        }
    )

    assert steps[2] == {"label": "Scan complete", "status": "failed"}
    assert steps[-1] == {"label": "Feed inventory updated", "status": "pending"}


def test_smoke_limit_body_is_clamped_to_small_debug_range() -> None:
    assert SmokeLimitBody(limit=5).limit == 5
    with pytest.raises(ValueError):
        SmokeLimitBody(limit=6)


@pytest.mark.asyncio
async def test_queue_attributes_handles_boto_client_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_client(*args, **kwargs):
        raise RuntimeError("missing region")

    monkeypatch.setattr(admin.boto3, "client", fail_client)

    assert await _queue_attributes(
        SimpleNamespace(aws_endpoint_url=None),
        "https://sqs.example/queue",
    ) == {
        "configured": True,
        "reachable": False,
        "error": "missing region",
    }


class FakeFeedDiagnosticResult:
    def __init__(self, row: dict) -> None:
        self.row = row

    def mappings(self):
        return self

    def first(self) -> dict:
        return self.row


class FakeFeedDiagnosticSession:
    def __init__(self) -> None:
        self.statement = ""
        self.params: dict | None = None

    async def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return FakeFeedDiagnosticResult(
            {
                "market_key": "springfield|il|us",
                "city": "Springfield",
                "state": "IL",
                "country": "US",
                "visible_event_count_7d": 0,
                "active_user_count_7d": 1,
                "last_scan_completed_at": None,
                "last_scan_succeeded_at": None,
                "last_error": None,
                "upcoming_occurrences": 0,
                "hidden_events": 0,
                "pending_verification": 0,
                "suspect_or_inactive": 0,
                "missing_images": 0,
                "last_successful_scan": None,
                "last_failed_scan": None,
            }
        )


@pytest.mark.asyncio
async def test_feed_diagnostic_scopes_event_counts_to_state_and_country() -> None:
    session = FakeFeedDiagnosticSession()

    await _feed_diagnostic(session, "springfield|il|us")

    assert session.params == {"market_key": "springfield|il|us"}
    assert "coalesce(lower(v.state), '') = coalesce(lower(mis.state), '')" in session.statement
    assert "lower(coalesce(v.country, 'US')) = lower(coalesce(mis.country, 'US'))" in (
        session.statement
    )


class FakeMappings:
    def one(self) -> dict:
        return {
            "succeeded_jobs_eligible": 3,
            "failed_dead_jobs_eligible": 2,
            "scheduler_runs_eligible": 1,
        }


class FakeRetentionResult:
    def mappings(self) -> FakeMappings:
        return FakeMappings()


class FakeSession:
    async def execute(self, statement):
        assert "status = 'succeeded'" in str(statement)
        assert "public.scheduler_runs" in str(statement)
        return FakeRetentionResult()


@pytest.mark.asyncio
async def test_retention_dashboard_reports_candidates_without_cleanup() -> None:
    assert await _retention_dashboard(FakeSession()) == {
        "succeededJobsDays": 30,
        "failedDeadJobsDays": 90,
        "schedulerRunsDays": 90,
        "automaticCleanupEnabled": False,
        "candidates": {
            "succeededJobs": 3,
            "failedDeadJobs": 2,
            "schedulerRuns": 1,
        },
    }
