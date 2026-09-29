-- Minimal Supabase-managed schemas for disposable CI PostgreSQL only.
create schema if not exists extensions;
-- The PostGIS CI image may preinstall PostGIS in public. Supabase exposes it
-- from extensions, which the launch migration references explicitly.
drop extension if exists postgis cascade;
create extension postgis with schema extensions;
create schema if not exists auth;
create schema if not exists storage;
do $$ begin
 if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
 if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
 if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role bypassrls; end if;
end $$;
create or replace function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
create table if not exists storage.buckets(id text primary key,name text,public boolean,avif_autodetection boolean,file_size_limit bigint,allowed_mime_types text[]);
create table if not exists storage.objects(id uuid primary key,bucket_id text,name text);
alter table storage.objects enable row level security;
create or replace function storage.foldername(text) returns text[] language sql immutable as $$select string_to_array($1,'/')$$;
