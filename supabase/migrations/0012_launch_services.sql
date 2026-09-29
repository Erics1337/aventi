-- Mobile launch services: subscriptions, durable deletion, destination search,
-- and cached premium event insights.

alter table public.premium_entitlements
  add column if not exists product_identifier text,
  add column if not exists entitlement_status text not null default 'inactive',
  add column if not exists management_url text,
  add column if not exists last_event_at timestamptz;

create table if not exists public.subscription_accounts (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  revenuecat_app_user_id text not null unique,
  original_app_user_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint subscription_accounts_permanent_identity
    check (revenuecat_app_user_id = user_id::text and original_app_user_id = user_id::text)
);

create table if not exists public.revenuecat_events (
  event_id text primary key,
  user_id uuid references public.profiles(id) on delete cascade,
  event_type text not null,
  event_at timestamptz not null,
  payload jsonb not null default '{}'::jsonb,
  processing_status text not null,
  error_message text,
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  constraint revenuecat_events_status_check
    check (processing_status in ('received', 'processed', 'stale', 'rejected'))
);
create index if not exists revenuecat_events_user_event_idx
  on public.revenuecat_events (user_id, event_at desc);

-- No profile FK by design: this row is the durable anti-rebootstrap tombstone.
create table if not exists public.account_deletions (
  user_id uuid primary key,
  status text not null default 'pending',
  current_stage text not null default 'revenuecat',
  stages jsonb not null default '{}'::jsonb,
  last_error text,
  requested_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  constraint account_deletions_status_check
    check (status in ('pending', 'processing', 'failed', 'completed'))
);

create or replace function public.aventi_prevent_deleted_profile_bootstrap()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if exists (select 1 from public.account_deletions where user_id = new.id) then
    raise exception using
      errcode = 'P0001',
      message = 'account deletion has been requested';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_prevent_deleted_profile_bootstrap on public.profiles;
create trigger trg_prevent_deleted_profile_bootstrap
before insert on public.profiles
for each row execute function public.aventi_prevent_deleted_profile_bootstrap();

create table if not exists public.destinations (
  id uuid primary key,
  provider text not null,
  provider_place_id text not null,
  label text not null,
  city text not null,
  state text not null,
  country text not null default 'US',
  latitude double precision not null,
  longitude double precision not null,
  timezone text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_place_id),
  constraint destinations_us_only check (country = 'US'),
  constraint destinations_latitude_check check (latitude between -90 and 90),
  constraint destinations_longitude_check check (longitude between -180 and 180)
);
create index if not exists destinations_city_state_idx on public.destinations (city, state);

create table if not exists public.destination_queries (
  normalized_query text not null,
  destination_id uuid not null references public.destinations(id) on delete cascade,
  rank integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (normalized_query, destination_id)
);
create index if not exists destination_queries_lookup_idx
  on public.destination_queries (normalized_query, rank);

create table if not exists public.event_insights (
  event_id uuid not null references public.events(id) on delete cascade,
  context_hash text not null,
  context jsonb not null default '{}'::jsonb,
  status text not null default 'queued',
  payload jsonb,
  job_id text,
  last_error text,
  generated_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (event_id, context_hash),
  constraint event_insights_status_check
    check (status in ('queued', 'generating', 'ready', 'failed'))
);
create index if not exists event_insights_expiry_idx
  on public.event_insights (status, expires_at);

alter table public.subscription_accounts enable row level security;
alter table public.revenuecat_events enable row level security;
alter table public.account_deletions enable row level security;
alter table public.destinations enable row level security;
alter table public.destination_queries enable row level security;
alter table public.event_insights enable row level security;
