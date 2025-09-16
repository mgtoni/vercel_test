-- Create a manifest table for PDFs stored in Supabase Storage
-- Adjust schema/columns as needed for your app

create table if not exists public.pdf_assets (
  id uuid primary key default gen_random_uuid(),
  bucket text not null,
  path text not null,
  order_index integer not null default 0,
  is_default boolean not null default false,
  score_min integer,
  score_max integer
);

-- Indexes to speed up queries
create index if not exists idx_pdf_assets_group on public.pdf_assets (group_key);
create index if not exists idx_pdf_assets_group_default on public.pdf_assets (group_key, is_default);
create index if not exists idx_pdf_assets_active on public.pdf_assets (active);
create index if not exists idx_pdf_assets_order on public.pdf_assets (group_key, order_index);

-- Basic RLS setup (you may customize to your needs)
alter table public.pdf_assets enable row level security;

-- Policy allowing service role full access; restrict anon if needed.
do $$ begin
  if not exists (
    select 1 from pg_policies where polname = 'service_role_all_pdf_assets'
  ) then
    create policy service_role_all_pdf_assets on public.pdf_assets
      for all
      using (true)
      with check (true);
  end if;
end $$;

-- Optional: policy to allow read-only for authenticated users (adjust as needed)
-- create policy authenticated_read_pdf_assets on public.pdf_assets
--   for select to authenticated using (active = true);

