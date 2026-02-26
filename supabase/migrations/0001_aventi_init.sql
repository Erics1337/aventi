-- Aventi v1 core schema scaffold
create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
-- create extension if not exists postgis; -- enable if supported in target Supabase project
-- create extension if not exists vector;

create table if not exists public.profiles (
  id uuid primary key,
  email text,
  city text,
  timezone text,
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_preferences (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  categories text[] not null default '{}',
  vibes text[] not null default '{}',
  radius_miles integer not null default 10,
  travel_mode_city text,
  updated_at timestamptz not null default now()
);

create table if not exists public.user_vibe_weights (
  user_id uuid not null references public.profiles(id) on delete cascade,
  vibe text not null,
  weight numeric(10,4) not null default 1.0,
  updated_at timestamptz not null default now(),
  primary key (user_id, vibe)
);

create table if not exists public.venues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique,
  city text not null,
  state text,
  country text not null default 'US',
  address text,
  latitude double precision,
  longitude double precision,
  booking_domain text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  venue_id uuid references public.venues(id) on delete set null,
  source_event_key text,
  title text not null,
  normalized_title text generated always as (lower(regexp_replace(title, '\\s+', ' ', 'g'))) stored,
  description text,
  category text not null,
  booking_url text not null,
  image_url text,
  price_label text,
  is_free boolean not null default false,
  dress_code text,
  crowd_age text,
  music_genre text,
  hidden boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (booking_url)
);

create index if not exists events_normalized_title_idx on public.events using gin (normalized_title gin_trgm_ops);
create index if not exists events_hidden_idx on public.events (hidden);

create table if not exists public.event_occurrences (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events(id) on delete cascade,
  starts_at timestamptz not null,
  ends_at timestamptz,
  timezone text,
  cancelled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_id, starts_at)
);

create index if not exists event_occurrences_starts_at_idx on public.event_occurrences (starts_at);

create table if not exists public.event_tags (
  event_id uuid not null references public.events(id) on delete cascade,
  tag text not null,
  tag_type text not null default 'vibe',
  score numeric(10,4),
  primary key (event_id, tag, tag_type)
);

create table if not exists public.swipe_actions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  action text not null check (action in ('like', 'pass')),
  surfaced_at timestamptz,
  position integer,
  created_at timestamptz not null default now()
);
create index if not exists swipe_actions_user_created_idx on public.swipe_actions (user_id, created_at desc);

create table if not exists public.favorites (
  user_id uuid not null references public.profiles(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, event_id)
);

create table if not exists public.event_reports (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  reason text not null,
  details text,
  created_at timestamptz not null default now(),
  unique (event_id, user_id)
);
create index if not exists event_reports_event_idx on public.event_reports (event_id);

create table if not exists public.premium_entitlements (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  plan text not null default 'free',
  is_premium boolean not null default false,
  source text not null default 'stub',
  valid_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.feed_impressions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  event_id uuid not null references public.events(id) on delete cascade,
  served_at timestamptz not null default now(),
  position integer,
  affinity_score numeric(10,4),
  filters jsonb not null default '{}'::jsonb
);

create table if not exists public.ingest_sources (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  source_type text not null,
  base_url text,
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ingest_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references public.ingest_sources(id) on delete set null,
  city text,
  status text not null default 'queued',
  started_at timestamptz,
  finished_at timestamptz,
  discovered_count integer not null default 0,
  inserted_count integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.verification_runs (
  id uuid primary key default gen_random_uuid(),
  event_id uuid references public.events(id) on delete cascade,
  status text not null,
  verified_at timestamptz not null default now(),
  http_status integer,
  active boolean,
  details jsonb not null default '{}'::jsonb
);

create table if not exists public.job_queue (
  id uuid primary key default gen_random_uuid(),
  job_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 5,
  run_at timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists job_queue_ready_idx on public.job_queue (status, run_at);

create table if not exists public.job_runs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.job_queue(id) on delete cascade,
  status text not null,
  worker_name text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  error_message text,
  log jsonb not null default '{}'::jsonb
);

-- Hide events after 3 unique reports.
create or replace function public.aventi_apply_report_threshold()
returns trigger
language plpgsql
as $$
begin
  update public.events e
  set hidden = true,
      updated_at = now()
  where e.id = new.event_id
    and (
      select count(distinct er.user_id)
      from public.event_reports er
      where er.event_id = new.event_id
    ) >= 3;
  return new;
end;
$$;

drop trigger if exists trg_aventi_report_threshold on public.event_reports;
create trigger trg_aventi_report_threshold
after insert on public.event_reports
for each row execute function public.aventi_apply_report_threshold();

alter table public.profiles enable row level security;
alter table public.user_preferences enable row level security;
alter table public.user_vibe_weights enable row level security;
alter table public.favorites enable row level security;
alter table public.swipe_actions enable row level security;
alter table public.event_reports enable row level security;
alter table public.premium_entitlements enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
for select using (auth.uid() = id);
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
for update using (auth.uid() = id);

drop policy if exists "user_preferences_all_own" on public.user_preferences;
create policy "user_preferences_all_own" on public.user_preferences
for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "user_vibe_weights_all_own" on public.user_vibe_weights;
create policy "user_vibe_weights_all_own" on public.user_vibe_weights
for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "favorites_all_own" on public.favorites;
create policy "favorites_all_own" on public.favorites
for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "swipes_all_own" on public.swipe_actions;
create policy "swipes_all_own" on public.swipe_actions
for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "reports_insert_own" on public.event_reports;
create policy "reports_insert_own" on public.event_reports
for insert with check (auth.uid() = user_id);
drop policy if exists "reports_select_own" on public.event_reports;
create policy "reports_select_own" on public.event_reports
for select using (auth.uid() = user_id);

drop policy if exists "entitlements_select_own" on public.premium_entitlements;
create policy "entitlements_select_own" on public.premium_entitlements
for select using (auth.uid() = user_id);
