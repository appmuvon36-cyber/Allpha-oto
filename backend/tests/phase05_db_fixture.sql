-- Ephemeral PostgreSQL fixture for Phase 05 transaction integration tests only.
-- This schema is created in a disposable GitHub Actions PostgreSQL service, never production.
create schema if not exists auth;
create or replace function auth.uid() returns uuid
language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

do $$ begin
  create type public.oto_user_role as enum ('customer','supplier','catalog_editor','inventory_manager','order_manager','moderator','admin');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.oto_product_condition as enum ('new_oem','new_aftermarket','used','refurbished','remanufactured','damaged_for_parts');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.oto_product_status as enum ('draft','review','approved','published','rejected','archived');
exception when duplicate_object then null; end $$;
do $$ begin
  create type public.oto_fitment_status as enum ('needs_review','verified','rejected');
exception when duplicate_object then null; end $$;

create table public.user_profiles (
  id uuid primary key,
  role public.oto_user_role not null,
  is_active boolean not null default true
);
create table public.products (
  id uuid primary key default gen_random_uuid(),
  sku text not null unique,
  slug text not null unique,
  name text not null,
  description text,
  brand text,
  part_number text,
  category text not null,
  condition public.oto_product_condition not null,
  condition_grade text,
  package_quantity integer not null default 1,
  warranty_days integer not null default 0,
  status public.oto_product_status not null default 'draft',
  currency char(3) not null default 'IDR',
  retail_price numeric,
  fitment_summary text,
  published_at timestamptz,
  created_by uuid,
  updated_by uuid,
  source_rights_evidence text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table public.product_fitments (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id),
  variant_id uuid not null,
  status public.oto_fitment_status not null default 'needs_review',
  evidence_url text,
  evidence_note text,
  verified_by uuid,
  verified_at timestamptz,
  unique(product_id,variant_id)
);
create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  request_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create unique index audit_logs_actor_request_unique on public.audit_logs(actor_user_id,request_id);

create or replace function public.phase05_fail_audit_for_test()
returns trigger language plpgsql as $$
begin
  if new.request_id = 'phase05-force-audit-failure' then
    raise exception 'fixture_forced_audit_failure';
  end if;
  return new;
end $$;
create trigger phase05_fixture_audit_failure
before insert on public.audit_logs
for each row execute function public.phase05_fail_audit_for_test();
