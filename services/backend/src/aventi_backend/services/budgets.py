from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aventi_backend.core.settings import Settings, get_settings

MAX_MONTHLY_BUDGET_MICROUSD = 20_000_000
PAID_PROVIDERS = frozenset(
    {"serpapi", "gemini", "geocoding", "images", "pollinations"}
)


class BudgetError(RuntimeError):
    """Base class for terminal provider-budget decisions."""


class PaidProcessingDisabled(BudgetError):
    pass


class BudgetNotConfigured(BudgetError):
    pass


class BudgetExceeded(BudgetError):
    def __init__(self, message: str, *, reset_at: datetime) -> None:
        super().__init__(message)
        self.reset_at = reset_at


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    provider: str
    units: int
    used: int
    limit: int
    usage_date: date
    reserved_microusd: int
    monthly_used_microusd: int
    monthly_limit_microusd: int
    usage_month: date
    operation: str | None = None

    @property
    def remaining(self) -> int:
        """Daily provider units left after this reservation."""
        return max(0, self.limit - self.used)

    @property
    def monthly_remaining_microusd(self) -> int:
        return max(0, self.monthly_limit_microusd - self.monthly_used_microusd)


def _utc_periods(now: datetime | None = None) -> tuple[date, date, datetime, datetime]:
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    usage_date = current.date()
    usage_month = usage_date.replace(day=1)
    next_day = datetime.combine(usage_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    if usage_month.month == 12:
        next_month_date = date(usage_month.year + 1, 1, 1)
    else:
        next_month_date = date(usage_month.year, usage_month.month + 1, 1)
    next_month = datetime.combine(next_month_date, datetime.min.time(), tzinfo=UTC)
    return usage_date, usage_month, next_day, next_month


class BudgetManager:
    """Atomically reserve daily units and shared monthly money before provider calls.

    Monetary amounts are integer micro-USD (1 USD = 1,000,000 micro-USD). Each
    unit reserves the configured conservative maximum provider cost. Reservations
    remain consumed when an external call fails so actual spend cannot outrun the
    ledger. The aggregate ceiling resets at 00:00 UTC on the first of each month.
    """

    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def _limits(self, provider: str) -> tuple[int, int, int]:
        if provider not in PAID_PROVIDERS:
            raise BudgetNotConfigured(f"Unknown paid provider: {provider}")
        daily_limit = self.settings.provider_daily_budgets.get(provider)
        if type(daily_limit) is not int or daily_limit <= 0:
            raise BudgetNotConfigured(f"No positive daily budget configured for {provider}")
        max_cost = self.settings.provider_max_cost_microusd.get(provider)
        if type(max_cost) is not int or max_cost <= 0:
            raise BudgetNotConfigured(
                f"No positive maximum unit cost configured for {provider}"
            )
        monthly_limit = self.settings.provider_monthly_budget_microusd
        if (
            type(monthly_limit) is not int
            or monthly_limit <= 0
            or monthly_limit > MAX_MONTHLY_BUDGET_MICROUSD
        ):
            raise BudgetNotConfigured(
                "Monthly provider budget must be between 1 and 20000000 micro-USD"
            )
        return daily_limit, max_cost, monthly_limit

    async def reserve(
        self,
        provider: str,
        units: int = 1,
        *,
        operation: str | None = None,
        commit: bool = True,
    ) -> BudgetReservation:
        name = provider.strip().lower()
        if type(units) is not int or units < 1:
            raise ValueError("Budget reservation units must be a positive integer")
        if not self.settings.paid_discovery_enabled:
            raise PaidProcessingDisabled("Paid provider processing is disabled")
        daily_limit, max_cost, monthly_limit = self._limits(name)
        usage_date, usage_month, next_day, next_month = _utc_periods()
        if units > daily_limit:
            raise BudgetExceeded(
                f"Reservation exceeds the daily {name} budget", reset_at=next_day
            )
        reserved_microusd = units * max_cost
        if reserved_microusd > monthly_limit:
            raise BudgetExceeded(
                "Reservation exceeds the shared monthly provider budget",
                reset_at=next_month,
            )

        # Every reservation takes the monthly row lock first. Concurrent calls are
        # serialized against the aggregate ceiling, then update their provider/day
        # row in the same database transaction.
        monthly_result = await self.session.execute(
            text(
                """
                insert into public.provider_monthly_usage (
                  usage_month, used_microusd, limit_microusd, updated_at
                )
                values (:usage_month, :reserved_microusd, :monthly_limit, now())
                on conflict (usage_month) do update
                set used_microusd = public.provider_monthly_usage.used_microusd
                                     + excluded.used_microusd,
                    limit_microusd = least(
                      public.provider_monthly_usage.limit_microusd,
                      excluded.limit_microusd
                    ),
                    updated_at = now()
                where public.provider_monthly_usage.used_microusd
                        + excluded.used_microusd
                      <= least(
                        public.provider_monthly_usage.limit_microusd,
                        excluded.limit_microusd
                      )
                returning used_microusd, limit_microusd
                """
            ),
            {
                "usage_month": usage_month,
                "reserved_microusd": reserved_microusd,
                "monthly_limit": monthly_limit,
            },
        )
        monthly_row = monthly_result.mappings().first()
        if monthly_row is None:
            await self.session.rollback()
            raise BudgetExceeded(
                "Shared monthly provider budget exhausted", reset_at=next_month
            )

        daily_result = await self.session.execute(
            text(
                """
                insert into public.provider_daily_usage (
                  usage_date, provider, used_units, limit_units, updated_at
                )
                values (:usage_date, :provider, :units, :daily_limit, now())
                on conflict (usage_date, provider) do update
                set used_units = public.provider_daily_usage.used_units + excluded.used_units,
                    limit_units = least(
                      public.provider_daily_usage.limit_units,
                      excluded.limit_units
                    ),
                    updated_at = now()
                where public.provider_daily_usage.used_units + excluded.used_units
                      <= least(
                        public.provider_daily_usage.limit_units,
                        excluded.limit_units
                      )
                returning used_units, limit_units
                """
            ),
            {
                "usage_date": usage_date,
                "provider": name,
                "units": units,
                "daily_limit": daily_limit,
            },
        )
        daily_row = daily_result.mappings().first()
        if daily_row is None:
            # This also rolls back the monthly reservation above.
            await self.session.rollback()
            raise BudgetExceeded(f"Daily {name} budget exhausted", reset_at=next_day)
        if commit:
            await self.session.commit()
        return BudgetReservation(
            provider=name,
            units=units,
            used=int(daily_row["used_units"]),
            limit=int(daily_row["limit_units"]),
            usage_date=usage_date,
            reserved_microusd=reserved_microusd,
            monthly_used_microusd=int(monthly_row["used_microusd"]),
            monthly_limit_microusd=int(monthly_row["limit_microusd"]),
            usage_month=usage_month,
            operation=operation,
        )

    async def _capacity(self, provider: str) -> tuple[int, int] | None:
        name = provider.strip().lower()
        if not self.settings.paid_discovery_enabled:
            return None
        try:
            daily_limit, max_cost, monthly_limit = self._limits(name)
        except BudgetNotConfigured:
            return None
        usage_date, usage_month, _, _ = _utc_periods()
        result = await self.session.execute(
            text(
                """
                select
                  coalesce((
                    select used_units from public.provider_daily_usage
                    where usage_date = :usage_date and provider = :provider
                  ), 0) as daily_used_units,
                  coalesce((
                    select limit_units from public.provider_daily_usage
                    where usage_date = :usage_date and provider = :provider
                  ), :daily_limit) as stored_daily_limit,
                  coalesce((
                    select used_microusd from public.provider_monthly_usage
                    where usage_month = :usage_month
                  ), 0) as monthly_used_microusd,
                  coalesce((
                    select limit_microusd from public.provider_monthly_usage
                    where usage_month = :usage_month
                  ), :monthly_limit) as stored_monthly_limit
                """
            ),
            {
                "usage_date": usage_date,
                "usage_month": usage_month,
                "provider": name,
                "daily_limit": daily_limit,
                "monthly_limit": monthly_limit,
            },
        )
        row = result.mappings().first()
        if row is None:  # pragma: no cover - the SELECT always yields one row
            return 0, 0
        effective_daily_limit = min(daily_limit, int(row["stored_daily_limit"]))
        daily_remaining = max(0, effective_daily_limit - int(row["daily_used_units"]))
        effective_monthly_limit = min(monthly_limit, int(row["stored_monthly_limit"]))
        monthly_remaining = max(
            0, effective_monthly_limit - int(row["monthly_used_microusd"])
        )
        return daily_remaining, monthly_remaining // max_cost

    async def remaining(self, provider: str) -> int:
        """Return currently reservable units under both caps, without consuming one."""
        capacity = await self._capacity(provider)
        if capacity is None:
            return 0
        daily_remaining, monthly_affordable_units = capacity
        return min(daily_remaining, monthly_affordable_units)

    async def next_reset_at(self, provider: str) -> datetime | None:
        """Return the effective UTC reset when a configured provider is exhausted."""
        capacity = await self._capacity(provider)
        if capacity is None:
            return None
        daily_remaining, monthly_affordable_units = capacity
        _, _, next_day, next_month = _utc_periods()
        if monthly_affordable_units == 0:
            return next_month
        if daily_remaining == 0:
            return next_day
        return None

    async def try_reserve(
        self,
        provider: str,
        units: int = 1,
        *,
        operation: str | None = None,
        commit: bool = True,
    ) -> BudgetReservation | None:
        try:
            return await self.reserve(provider, units, operation=operation, commit=commit)
        except BudgetError:
            return None
