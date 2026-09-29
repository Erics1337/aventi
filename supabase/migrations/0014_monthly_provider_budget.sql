-- One UTC-calendar-month monetary ceiling shared by every paid provider.
-- Monetary values are integer micro-USD (1 USD = 1,000,000 micro-USD).
-- Application reservations use a configured conservative maximum cost per unit.
create table if not exists public.provider_monthly_usage (
  usage_month date primary key,
  used_microusd bigint not null default 0
    check (used_microusd >= 0),
  limit_microusd bigint not null
    check (limit_microusd > 0 and limit_microusd <= 20000000),
  updated_at timestamptz not null default now(),
  constraint provider_monthly_usage_month_start
    check (usage_month = date_trunc('month', usage_month)::date),
  constraint provider_monthly_usage_within_limit
    check (used_microusd <= limit_microusd)
);

alter table public.provider_monthly_usage enable row level security;
revoke all on public.provider_monthly_usage from anon, authenticated;
