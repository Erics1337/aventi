alter table public.market_inventory_state
  add column if not exists last_targeted_filter_signature text,
  add column if not exists last_targeted_requested_at timestamptz,
  add column if not exists last_targeted_completed_at timestamptz;

create index if not exists market_inventory_state_targeted_signature_idx
  on public.market_inventory_state (last_targeted_filter_signature, last_targeted_requested_at desc);
