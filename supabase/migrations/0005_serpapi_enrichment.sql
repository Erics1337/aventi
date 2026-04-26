-- Add venue rating and review_count from SerpAPI venue data
alter table public.venues
  add column if not exists rating numeric(3,1),
  add column if not exists review_count integer;

-- ticket_offers: normalized ticket links sourced from SerpAPI ticket_info
create table if not exists public.ticket_offers (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events(id) on delete cascade,
  provider text,
  url text not null,
  price_label text,
  is_free boolean,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_id, url)
);

create index if not exists ticket_offers_event_idx on public.ticket_offers (event_id, sort_order);
