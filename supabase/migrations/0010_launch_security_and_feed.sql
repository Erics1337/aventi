create extension if not exists postgis with schema extensions;
alter table public.venues add column if not exists location extensions.geography(Point,4326)
  generated always as (case when latitude between -90 and 90 and longitude between -180 and 180
    then extensions.st_setsrid(extensions.st_makepoint(longitude,latitude),4326)::extensions.geography end) stored;
create index if not exists venues_location_gist on public.venues using gist(location);
alter table public.events add column if not exists admission_restriction text
  check (admission_restriction in ('all','18+','21+'));
alter table public.events add column if not exists admission_source_url text;
alter table public.swipe_actions add column if not exists action_id uuid;
alter table public.swipe_actions add column if not exists result jsonb;
create unique index if not exists swipe_actions_idempotency on public.swipe_actions(user_id,action_id);
create table public.feed_sessions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
 event_ids uuid[] not null, request_hash text not null, created_at timestamptz not null default now(),
 expires_at timestamptz not null default now() + interval '30 minutes'
);
create index feed_sessions_expiry on public.feed_sessions(expires_at);
create table public.request_limits (
 key text not null, window_start timestamptz not null, count integer not null default 1,
 primary key(key,window_start)
);
-- Supabase clients use Auth and intentionally public Storage only. All domain access is via API.
do $$ declare item record; begin
 for item in select tablename from pg_tables where schemaname='public' loop
  execute format('alter table public.%I enable row level security',item.tablename);
  execute format('revoke all on public.%I from anon, authenticated',item.tablename);
 end loop;
end $$;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
-- Image writes are backend-only too; the original policy allowed arbitrary uploads.
drop policy if exists "Authenticated users can upload event images" on storage.objects;
