alter table public.events
  add column if not exists verification_status text not null default 'pending',
  add column if not exists verification_fail_count integer not null default 0,
  add column if not exists last_verified_at timestamptz,
  add column if not exists last_verified_active boolean;

create index if not exists events_verification_status_idx on public.events (verification_status);

create table if not exists public.market_inventory_state (
  market_key text primary key,
  city text not null,
  state text,
  country text not null default 'US',
  center_latitude double precision,
  center_longitude double precision,
  last_requested_at timestamptz,
  last_scan_requested_at timestamptz,
  last_scan_started_at timestamptz,
  last_scan_completed_at timestamptz,
  last_scan_succeeded_at timestamptz,
  scan_lock_until timestamptz,
  visible_event_count_7d integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists market_inventory_state_last_requested_idx
  on public.market_inventory_state (last_requested_at desc);

create table if not exists public.market_ingest_sources (
  market_key text not null,
  source_id uuid not null references public.ingest_sources(id) on delete cascade,
  priority integer not null default 100,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (market_key, source_id)
);

create index if not exists market_ingest_sources_market_priority_idx
  on public.market_ingest_sources (market_key, priority, enabled);

with verification_rollup as (
  select
    vr.event_id,
    max(vr.verified_at) as last_verified_at,
    (
      array_agg(vr.active order by vr.verified_at desc)
    )[1] as last_verified_active,
    count(*) filter (
      where vr.active = false
        and vr.verified_at >= now() - interval '24 hours'
    ) as inactive_failures_24h
  from public.verification_runs vr
  group by vr.event_id
)
update public.events e
set verification_status = case
      when rollup.last_verified_active is true then 'verified'
      when coalesce(rollup.inactive_failures_24h, 0) >= 2 then 'inactive'
      when coalesce(rollup.inactive_failures_24h, 0) = 1 then 'suspect'
      else 'pending'
    end,
    verification_fail_count = coalesce(rollup.inactive_failures_24h, 0),
    last_verified_at = rollup.last_verified_at,
    last_verified_active = rollup.last_verified_active,
    hidden = case
      when e.hidden = true
        and coalesce(e.metadata ->> 'verificationStatus', '') = 'inactive'
      then false
      else e.hidden
    end,
    updated_at = now()
from verification_rollup rollup
where e.id = rollup.event_id;
