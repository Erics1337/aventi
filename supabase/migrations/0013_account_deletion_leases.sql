-- Fence concurrent deletion requests and stale retries without losing the tombstone.
alter table public.account_deletions add column if not exists run_token uuid;
