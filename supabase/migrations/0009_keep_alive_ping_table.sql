create table if not exists public.keep_alive_pings (
  id text primary key,
  created_at timestamptz not null default now()
);

insert into public.keep_alive_pings (id)
values ('supabase-free-tier-heartbeat')
on conflict (id) do nothing;

alter table public.keep_alive_pings enable row level security;

drop policy if exists "keep_alive_pings_select_anon" on public.keep_alive_pings;
create policy "keep_alive_pings_select_anon" on public.keep_alive_pings
for select
to anon
using (true);

grant usage on schema public to anon;
grant select on public.keep_alive_pings to anon;
