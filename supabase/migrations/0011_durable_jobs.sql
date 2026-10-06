create table if not exists public.jobs (
  id text primary key,
  job_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'retry', 'completed', 'dead', 'cancelled')),
  run_at timestamptz not null default now(),
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 5 check (max_attempts > 0),
  dedup_key text,
  locked_by text,
  lease_expires_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  result jsonb,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists jobs_active_dedup_key_uidx
  on public.jobs (dedup_key)
  where dedup_key is not null and status in ('queued', 'processing', 'retry');
create index if not exists jobs_claim_idx on public.jobs (status, run_at, lease_expires_at);

create table if not exists public.job_outbox (
  id bigint generated always as identity primary key,
  job_id text not null unique references public.jobs(id) on delete cascade,
  available_at timestamptz not null default now(),
  published_at timestamptz,
  publish_attempts integer not null default 0,
  sqs_message_id text,
  last_error text,
  created_at timestamptz not null default now()
);
create index if not exists job_outbox_pending_idx
  on public.job_outbox (available_at, id) where published_at is null;

create table if not exists public.provider_daily_usage (
  usage_date date not null,
  provider text not null,
  used_units integer not null default 0 check (used_units >= 0),
  limit_units integer not null check (limit_units > 0),
  updated_at timestamptz not null default now(),
  primary key (usage_date, provider)
);

alter table public.jobs enable row level security;
alter table public.job_outbox enable row level security;
alter table public.provider_daily_usage enable row level security;

revoke all on public.jobs from anon, authenticated;
revoke all on public.job_outbox from anon, authenticated;
revoke all on public.provider_daily_usage from anon, authenticated;
