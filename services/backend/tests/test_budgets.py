from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aventi_backend.core.settings import Settings
from aventi_backend.services.budgets import (
    BudgetExceeded,
    BudgetManager,
    BudgetNotConfigured,
    PaidProcessingDisabled,
)


class _Mappings:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return _Mappings(self.row)


class _Session:
    def __init__(self, *rows):
        self.rows = list(rows)
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result(self.rows.pop(0))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _settings(**overrides):
    values = {
        "env": "development",
        "paid_discovery_enabled": True,
        "provider_daily_budgets": {"gemini": 3},
        "provider_monthly_budget_microusd": 1_000,
        "provider_max_cost_microusd": {"gemini": 400},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_reserve_updates_monthly_then_daily_in_one_transaction() -> None:
    session = _Session(
        {"used_microusd": 800, "limit_microusd": 1_000},
        {"used_units": 2, "limit_units": 3},
    )
    manager = BudgetManager(session, settings=_settings())  # type: ignore[arg-type]

    reservation = await manager.reserve("gemini", operation="verify")

    assert "provider_monthly_usage" in session.calls[0][0]
    assert "provider_daily_usage" in session.calls[1][0]
    assert session.calls[0][1]["reserved_microusd"] == 400
    assert session.calls[1][1]["units"] == 1
    assert reservation.remaining == 1
    assert reservation.monthly_remaining_microusd == 200
    assert reservation.operation == "verify"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_monthly_exhaustion_rolls_back_before_daily_reservation() -> None:
    session = _Session(None)
    manager = BudgetManager(session, settings=_settings())  # type: ignore[arg-type]

    with pytest.raises(BudgetExceeded) as error:
        await manager.reserve("gemini")

    assert "monthly" in str(error.value).lower()
    assert error.value.reset_at.tzinfo is UTC
    assert error.value.reset_at.day == 1
    assert len(session.calls) == 1
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_daily_exhaustion_rolls_back_monthly_reservation() -> None:
    session = _Session(
        {"used_microusd": 400, "limit_microusd": 1_000},
        None,
    )
    manager = BudgetManager(session, settings=_settings())  # type: ignore[arg-type]

    with pytest.raises(BudgetExceeded) as error:
        await manager.reserve("gemini")

    assert "daily" in str(error.value).lower()
    assert len(session.calls) == 2
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_toggle_daily_cap_and_max_cost_are_all_required() -> None:
    session = _Session()
    disabled = BudgetManager(
        session,
        settings=_settings(paid_discovery_enabled=False),
    )
    with pytest.raises(PaidProcessingDisabled):
        await disabled.reserve("gemini")

    uncapped = BudgetManager(session, settings=_settings(provider_daily_budgets={}))
    with pytest.raises(BudgetNotConfigured):
        await uncapped.reserve("gemini")

    unknown_cost = BudgetManager(session, settings=_settings(provider_max_cost_microusd={}))
    with pytest.raises(BudgetNotConfigured):
        await unknown_cost.reserve("gemini")
    assert session.calls == []


@pytest.mark.asyncio
async def test_first_reservation_cannot_exceed_either_cap() -> None:
    session = _Session()
    manager = BudgetManager(session, settings=_settings())  # type: ignore[arg-type]
    with pytest.raises(BudgetExceeded):
        await manager.reserve("gemini", units=4)
    assert session.calls == []

    monthly = BudgetManager(
        session,
        settings=_settings(
            provider_daily_budgets={"gemini": 10},
            provider_monthly_budget_microusd=500,
        ),
    )
    with pytest.raises(BudgetExceeded) as error:
        await monthly.reserve("gemini", units=2)
    assert error.value.reset_at.day == 1
    assert session.calls == []


@pytest.mark.asyncio
async def test_remaining_is_zero_when_month_cannot_fund_one_more_unit() -> None:
    session = _Session(
        {
            "daily_used_units": 1,
            "stored_daily_limit": 3,
            "monthly_used_microusd": 601,
            "stored_monthly_limit": 1_000,
        },
        {
            "daily_used_units": 1,
            "stored_daily_limit": 3,
            "monthly_used_microusd": 601,
            "stored_monthly_limit": 1_000,
        },
    )
    manager = BudgetManager(session, settings=_settings())  # type: ignore[arg-type]

    assert await manager.remaining("gemini") == 0
    reset = await manager.next_reset_at("gemini")
    assert reset is not None
    assert reset.tzinfo is UTC
    assert reset.day == 1


@pytest.mark.asyncio
async def test_pollinations_is_supported_but_fails_closed_without_cost() -> None:
    session = _Session()
    manager = BudgetManager(
        session,
        settings=_settings(provider_daily_budgets={"pollinations": 2}),
    )
    with pytest.raises(BudgetNotConfigured):
        await manager.reserve("pollinations")
    assert await manager.remaining("pollinations") == 0
    assert session.calls == []


def test_settings_enforce_twenty_dollar_hard_ceiling() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            AVENTI_ENV="test",
            AVENTI_PROVIDER_MONTHLY_BUDGET_MICROUSD=20_000_001,
        )


def test_migration_enforces_aggregate_hard_ceiling_and_rls() -> None:
    migration = (
        __import__("pathlib").Path(__file__).parents[3]
        / "supabase/migrations/0014_monthly_provider_budget.sql"
    ).read_text()
    assert "limit_microusd <= 20000000" in migration
    assert "primary key" in migration
    assert "enable row level security" in migration
    assert "revoke all on public.provider_monthly_usage from anon, authenticated" in migration


@pytest.mark.parametrize("value", [True, 0.5, "10"])
def test_cost_configuration_rejects_non_integer_values(value):
    from aventi_backend.core.settings import Settings

    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            AVENTI_ENV="test",
            AVENTI_PROVIDER_MAX_COST_MICROUSD={"pollinations": value},
        )


def test_enabled_production_requires_pollinations_credential():
    from aventi_backend.core.settings import Settings

    providers = {"serpapi": 1, "gemini": 1, "geocoding": 1, "pollinations": 1}
    with pytest.raises(ValueError, match="Discovery provider credentials"):
        Settings(
            _env_file=None,
            AVENTI_ENV="production",
            AVENTI_DATABASE_URL="postgresql://test",
            AVENTI_SUPABASE_URL="https://example.supabase.co",
            AVENTI_SUPABASE_SECRET_KEY="test",
            AVENTI_INTERNAL_API_KEY="test",
            AVENTI_CORS_ORIGINS=["https://web.example.com"],
            AVENTI_PAID_DISCOVERY_ENABLED=True,
            AVENTI_PROVIDER_DAILY_BUDGETS=providers,
            AVENTI_PROVIDER_MAX_COST_MICROUSD=providers,
            GOOGLE_API_KEY="test",
            SERPAPI_API_KEY="test",
            GOOGLE_GEOCODING_API_KEY="test",
            GOOGLE_TIMEZONE_API_KEY="test",
            POLLINATIONS_API_KEY=None,
        )
