-- Market heat tiers + per-market radius + activity attribution for feed impressions
-- Enables cron-driven, heat-aware city scans.

alter table public.market_inventory_state
  add column if not exists radius_miles numeric(6,2) not null default 25.0,
  add column if not exists last_user_active_at timestamptz,
  add column if not exists active_user_count_7d integer not null default 0,
  add column if not exists active_user_count_14d integer not null default 0,
  add column if not exists heat_tier text not null default 'cold';

-- Keep the constraint separate so it survives re-runs on existing rows with legacy values.
do $$
begin
  if not exists (
    select 1 from information_schema.table_constraints
    where table_schema = 'public'
      and table_name = 'market_inventory_state'
      and constraint_name = 'market_inventory_state_heat_tier_check'
  ) then
    alter table public.market_inventory_state
      add constraint market_inventory_state_heat_tier_check
      check (heat_tier in ('hot', 'warm', 'cold'));
  end if;
end$$;

create index if not exists market_inventory_state_heat_idx
  on public.market_inventory_state (heat_tier, last_user_active_at desc);

-- Attribute feed_impressions to a market so the scheduler can compute
-- distinct-active-user counts per market cheaply.
alter table public.feed_impressions
  add column if not exists market_key text;

create index if not exists feed_impressions_market_served_idx
  on public.feed_impressions (market_key, served_at desc);

-- Same for swipe_actions: the stream of distinct users over the last N days
-- is the primary signal for heat.
alter table public.swipe_actions
  add column if not exists market_key text;

create index if not exists swipe_actions_market_created_idx
  on public.swipe_actions (market_key, created_at desc);
