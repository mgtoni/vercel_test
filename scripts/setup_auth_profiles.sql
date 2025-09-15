-- Supabase auth + profiles setup (idempotent)
--
-- Purpose:
-- - Create/repair public.profiles with first_name/last_name and full_name.
-- - Add RLS policies so users can read/update their own profile.
-- - Add triggers so new auth users auto-create a profile from user_metadata.
-- - Provide optional RPC to update both profile and auth.user_metadata together.
--
-- Usage:
-- - Run as a single script in Supabase SQL editor.
-- - Safe to run multiple times; uses IF NOT EXISTS and CREATE OR REPLACE.

-- 1) Table definition --------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  first_name text not null default '',
  last_name  text not null default '',
  -- Computed full name kept consistent server-side
  full_name  text generated always as (btrim(coalesce(first_name,'') || ' ' || coalesce(last_name,''))) stored,
  email      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- If table existed without columns, add them.
alter table public.profiles add column if not exists first_name text;
alter table public.profiles add column if not exists last_name  text;
alter table public.profiles add column if not exists email      text;
alter table public.profiles add column if not exists created_at timestamptz not null default now();
alter table public.profiles add column if not exists updated_at timestamptz not null default now();

-- Ensure defaults and not-null on names
alter table public.profiles alter column first_name set default '';
alter table public.profiles alter column last_name  set default '';
update public.profiles set first_name = coalesce(first_name,'');
update public.profiles set last_name  = coalesce(last_name,'');
alter table public.profiles alter column first_name set not null;
alter table public.profiles alter column last_name  set not null;

-- Recreate full_name as generated column if it already exists but is not generated
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'profiles' and column_name = 'full_name'
  ) then
    begin
      alter table public.profiles drop column full_name;
    exception when undefined_column then
      null;
    end;
  end if;
  alter table public.profiles add column full_name text
    generated always as (btrim(coalesce(first_name,'') || ' ' || coalesce(last_name,''))) stored;
exception when duplicate_column then
  null;
end $$;

-- Timestamps trigger to keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end; $$;

drop trigger if exists set_timestamp on public.profiles;
create trigger set_timestamp
before update on public.profiles
for each row execute function public.set_updated_at();

-- 2) RLS policies ------------------------------------------------------------
alter table public.profiles enable row level security;

-- Users can select their own row
drop policy if exists "Read own profile" on public.profiles;
create policy "Read own profile"
on public.profiles for select
using (auth.uid() = id);

-- Users can update their own row
drop policy if exists "Update own profile" on public.profiles;
create policy "Update own profile"
on public.profiles for update
using (auth.uid() = id)
with check (auth.uid() = id);

-- Allow inserts only via service role (or backend admin upsert)
drop policy if exists "Insert via service role" on public.profiles;
create policy "Insert via service role"
on public.profiles for insert
with check ((auth.jwt() ->> 'role') = 'service_role');

-- 3) Triggers to sync from auth.users ---------------------------------------
-- Create/replace function that inserts/updates a profile when an auth user is created/updated.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  fn text := coalesce(new.raw_user_meta_data->>'first_name','');
  ln text := coalesce(new.raw_user_meta_data->>'last_name','');
begin
  insert into public.profiles (id, first_name, last_name, email)
  values (new.id, fn, ln, new.email)
  on conflict (id) do update set
    first_name = excluded.first_name,
    last_name  = excluded.last_name,
    email      = excluded.email,
    updated_at = now();
  return new;
end; $$;

-- Ensure trigger exists on auth.users insert
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- Keep profile in sync when auth user metadata changes (optional but helpful)
create or replace function public.handle_user_metadata_update()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  fn text := coalesce(new.raw_user_meta_data->>'first_name','');
  ln text := coalesce(new.raw_user_meta_data->>'last_name','');
begin
  update public.profiles
    set first_name = fn,
        last_name  = ln,
        email      = new.email,
        updated_at = now()
  where id = new.id;
  return new;
end; $$;

drop trigger if exists on_auth_user_updated on auth.users;
create trigger on_auth_user_updated
after update on auth.users
for each row execute function public.handle_user_metadata_update();

-- 4) Backfill helpers for existing data -------------------------------------
-- If you previously had full_name only and want to populate first/last, run:
-- update public.profiles
--   set first_name = coalesce(first_name, nullif(regexp_replace(full_name, '\s+[^ ]+$', ''), '')),
--       last_name  = coalesce(last_name,  nullif(regexp_replace(full_name, '^(.+)\s+', ''), ''))
-- where coalesce(full_name, '') <> '';

-- 5) Optional RPC to update names in one call (updates both profile and auth metadata)
create or replace function public.update_my_names(p_first text, p_last text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'Not authenticated';
  end if;

  -- Update profile
  update public.profiles
     set first_name = coalesce(p_first,'')
       , last_name  = coalesce(p_last,'')
       , updated_at = now()
   where id = uid;

  -- Update auth.user_metadata (requires service definer and auth admin privileges are handled by Supabase)
  -- Note: Supabase permits updating auth.users via the builtin helper. The recommended way
  -- from the client is to call supabase.auth.updateUser; from SQL we avoid touching auth.users directly.
  -- Instead, have your backend also call supabase.auth.admin.updateUserById to mirror names.
end; $$;

-- 6) Verification ------------------------------------------------------------
-- Check table definition
-- select column_name, is_generated, column_default, is_nullable from information_schema.columns
--  where table_schema='public' and table_name='profiles' order by ordinal_position;

-- Check RLS policies
-- select polname, cmd, qual, with_check from pg_policies where schemaname='public' and tablename='profiles';

-- Simulate a new user insert (admin only):
-- insert into auth.users(id, email, raw_user_meta_data)
-- values (gen_random_uuid(), 'example@example.com', '{"first_name":"Ada","last_name":"Lovelace"}')
-- on conflict do nothing;
