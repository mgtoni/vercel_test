
-- Create a manifest table for PDFs stored in Supabase Storage
-- Adjust schema/columns as needed for your app

create table if not exists public.pdf_assets (
  id uuid primary key default gen_random_uuid(),
  module text not null,
  lesson text,
  path text not null,
  is_default boolean not null default false,
  score_min integer,
  score_max integer,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Indexes to speed up queries
create index if not exists idx_pdf_assets_module on public.pdf_assets (module);
create index if not exists idx_pdf_assets_module_default on public.pdf_assets (module, is_default);
create index if not exists idx_pdf_assets_module_lesson on public.pdf_assets (module, lesson);
create index if not exists idx_pdf_assets_active on public.pdf_assets (active);

-- Basic RLS setup (you may customize to your needs)
alter table public.pdf_assets enable row level security;

-- Policy allowing service role full access; restrict anon if needed.
do $$ begin
  if not exists (
    select 1 from pg_policies where policyname = 'service_role_all_pdf_assets'
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
