create table if not exists public.scheduler_runs (
  id uuid primary key default gen_random_uuid(),
  trigger_type text not null,
  status text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  markets_considered integer not null default 0,
  markets_enqueued integer not null default 0,
  jobs_enqueued integer not null default 0,
  "limit" integer,
  error text,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint scheduler_runs_trigger_type_check check (
    trigger_type in ('cron', 'admin', 'smoke')
  ),
  constraint scheduler_runs_status_check check (
    status in ('running', 'succeeded', 'failed')
  )
);

create index if not exists scheduler_runs_started_at_idx
  on public.scheduler_runs (started_at desc);

create index if not exists scheduler_runs_status_started_at_idx
  on public.scheduler_runs (status, started_at desc);

create table if not exists public.worker_jobs (
  id text primary key,
  job_type text not null,
  status text not null,
  payload jsonb not null default '{}'::jsonb,
  payload_summary jsonb not null default '{}'::jsonb,
  market_key text,
  scheduler_run_id uuid references public.scheduler_runs(id) on delete set null,
  ingest_run_id uuid,
  attempts integer not null default 0,
  max_attempts integer not null default 5,
  queued_at timestamptz not null default now(),
  sent_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  last_error text,
  result jsonb,
  sqs_message_id text,
  run_id text,
  updated_at timestamptz not null default now(),
  constraint worker_jobs_status_check check (
    status in ('queued', 'sent', 'processing', 'succeeded', 'failed', 'dead')
  )
);

create index if not exists worker_jobs_status_queued_at_idx
  on public.worker_jobs (status, queued_at desc);

create index if not exists worker_jobs_job_type_status_idx
  on public.worker_jobs (job_type, status);

create index if not exists worker_jobs_finished_at_idx
  on public.worker_jobs (finished_at desc);

create index if not exists worker_jobs_market_key_idx
  on public.worker_jobs (market_key)
  where market_key is not null;

create index if not exists worker_jobs_ingest_run_id_idx
  on public.worker_jobs (ingest_run_id)
  where ingest_run_id is not null;

create index if not exists worker_jobs_scheduler_run_id_idx
  on public.worker_jobs (scheduler_run_id)
  where scheduler_run_id is not null;

alter table public.ingest_runs
  add column if not exists job_id text references public.worker_jobs(id) on delete set null;

create index if not exists ingest_runs_job_id_idx
  on public.ingest_runs (job_id)
  where job_id is not null;

alter table public.worker_jobs enable row level security;
alter table public.scheduler_runs enable row level security;
