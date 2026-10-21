-- Ephemeral PostgreSQL fixture for Phase 05 transaction integration tests only.
-- This schema is created in a disposable GitHub Actions PostgreSQL service, never production.
create schema if not exists auth;
create schema if not exists storage;
do $role$ begin create role anon nologin; exception when duplicate_object then null; end $role$;
do $role$ begin create role authenticated nologin; exception when duplicate_object then null; end $role$;
do $role$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $role$;
create table auth.users (id uuid primary key, email text, created_at timestamptz not null default now());
create table storage.buckets (
  id text primary key, name text not null, public boolean not null default false,
  file_size_limit bigint, allowed_mime_types text[]
);
create table storage.objects (
  id uuid primary key default gen_random_uuid(), bucket_id text not null, name text not null,
  unique(bucket_id,name)
);
create or replace function storage.foldername(name text) returns text[]
language sql immutable as $fn$ select string_to_array(name,'/') $fn$;
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
create or replace function public.oto_has_staff_role(allowed_roles public.oto_user_role[])
returns boolean language sql stable security definer as $role$
  select exists(select 1 from public.user_profiles p where p.id=auth.uid() and p.is_active=true and p.role=any(allowed_roles))
$role$;
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
create table public.suppliers (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid references auth.users(id) on delete set null,
  legal_name text not null,
  display_name text not null,
  supplier_type text not null check (supplier_type in ('oem_distributor','aftermarket_distributor','supplier','workshop','reconditioner','dismantler','individual')),
  status text not null default 'pending_review' check (status in ('pending_review','active','suspended','rejected')),
  contact_name text,
  contact_email text,
  contact_phone text,
  address jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table public.supplier_offers (
  id uuid primary key default gen_random_uuid(),
  supplier_id uuid not null references public.suppliers(id) on delete restrict,
  product_id uuid references public.products(id) on delete set null,
  supplier_sku text,
  source_url text,
  source_evidence jsonb not null default '{}'::jsonb,
  condition public.oto_product_condition not null,
  unit_cost numeric check (unit_cost >= 0),
  asking_price numeric check (asking_price >= 0),
  currency char(3) not null default 'IDR' check (currency='IDR'),
  stock_quantity integer not null default 0 check (stock_quantity >= 0),
  stock_checked_at timestamptz,
  quote_expires_at timestamptz,
  status text not null default 'pending_review' check (status in ('pending_review','active','unavailable','rejected','expired')),
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


-- Minimal existing-baseline inventory ledger for Phase 07 disposable tests.
do $$ begin
  create type public.oto_inventory_movement as enum ('receipt','sale','reservation','release','adjustment_increase','adjustment_decrease','return','write_off');
exception when duplicate_object then null; end $$;
create table if not exists public.inventory_ledger (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete restrict,
  supplier_id uuid references public.suppliers(id) on delete set null,
  movement public.oto_inventory_movement not null,
  quantity_delta integer not null,
  reference_type text,
  reference_id uuid,
  reason text not null,
  actor_user_id uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
