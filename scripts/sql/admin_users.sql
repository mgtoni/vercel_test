-- Admin users table to gate admin endpoints
create table if not exists public.admin_users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  role text default 'admin',
  active boolean not null default true,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create index if not exists idx_admin_users_email on public.admin_users (email);
create index if not exists idx_admin_users_active on public.admin_users (active);

alter table public.admin_users enable row level security;

-- Service role policy (server uses service key)
do $$ begin
  if not exists (
    select 1 from pg_policies where policyname = 'service_role_all_admin_users'
  ) then
    create policy service_role_all_admin_users on public.admin_users for all using (true) with check (true);
  end if;
end $$;

-- Optional: allow authenticated users to read their own row
-- create policy authenticated_read_self_admin_users on public.admin_users
--   for select to authenticated using (auth.jwt() ->> 'email' = email);

