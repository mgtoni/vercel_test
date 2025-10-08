-- Update pdf_assets schema to use module/lesson structure
alter table public.pdf_assets rename column bucket to module;

alter table public.pdf_assets add column if not exists lesson text;
alter table public.pdf_assets drop column if exists group_key;
alter table public.pdf_assets drop column if exists label;
alter table public.pdf_assets drop column if exists order_index;

alter table public.pdf_assets add column if not exists active boolean not null default true;
alter table public.pdf_assets add column if not exists created_at timestamptz not null default now();
alter table public.pdf_assets add column if not exists updated_at timestamptz not null default now();

update public.pdf_assets
set
  module = trim(module),
  path = trim(path),
  lesson = null
where true;

alter table public.pdf_assets alter column module set not null;
alter table public.pdf_assets alter column path set not null;

-- Refresh indexes
drop index if exists idx_pdf_assets_group;
drop index if exists idx_pdf_assets_group_default;
drop index if exists idx_pdf_assets_order;

create index if not exists idx_pdf_assets_module on public.pdf_assets (module);
create index if not exists idx_pdf_assets_module_default on public.pdf_assets (module, is_default);
create index if not exists idx_pdf_assets_module_lesson on public.pdf_assets (module, lesson);
