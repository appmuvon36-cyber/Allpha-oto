-- EC-01 additive catalog availability + customer sourcing requests.
-- Preserve all existing catalog/inventory rows and existing RLS policy boundaries.

create table if not exists public.sourcing_requests (
  id uuid primary key default gen_random_uuid(),
  customer_user_id uuid not null references auth.users(id) on delete restrict,
  idempotency_key text not null check (length(btrim(idempotency_key)) between 8 and 128),
  part_name text not null check (length(btrim(part_name)) between 2 and 180),
  part_number text check (part_number is null or length(btrim(part_number)) <= 120),
  vehicle_make text check (vehicle_make is null or length(btrim(vehicle_make)) <= 100),
  vehicle_model text check (vehicle_model is null or length(btrim(vehicle_model)) <= 120),
  vehicle_year integer check (vehicle_year is null or vehicle_year between 1950 and 2100),
  quantity integer not null default 1 check (quantity between 1 and 100),
  details text check (details is null or length(btrim(details)) <= 2000),
  contact_phone text check (contact_phone is null or length(btrim(contact_phone)) <= 40),
  status text not null default 'requested' check (status in ('requested','reviewing','quoted','sourced','unavailable','closed','cancelled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (customer_user_id, idempotency_key)
);

create index if not exists sourcing_requests_customer_created_idx
  on public.sourcing_requests (customer_user_id, created_at desc);
create index if not exists sourcing_requests_status_created_idx
  on public.sourcing_requests (status, created_at desc);

alter table public.sourcing_requests enable row level security;
revoke all on public.sourcing_requests from anon, authenticated;
grant select, insert on public.sourcing_requests to authenticated;

drop policy if exists "sourcing requests owner read" on public.sourcing_requests;
create policy "sourcing requests owner read"
  on public.sourcing_requests for select to authenticated
  using (customer_user_id = (select auth.uid()));

drop policy if exists "sourcing requests owner insert" on public.sourcing_requests;
create policy "sourcing requests owner insert"
  on public.sourcing_requests for insert to authenticated
  with check (
    customer_user_id = (select auth.uid())
    and status = 'requested'
  );

drop policy if exists "sourcing requests staff read" on public.sourcing_requests;
create policy "sourcing requests staff read"
  on public.sourcing_requests for select to authenticated
  using (public.oto_has_staff_role(array['admin','catalog_editor','order_manager']::public.oto_user_role[]));

create or replace function public.oto_public_stock_status(p_product_ids uuid[] default null)
returns table(product_id uuid, stock_status text, checked_at timestamptz)
language sql
stable
security definer
set search_path to 'pg_catalog', 'public'
as $function$
  select p.id,
    case
      when b.product_id is null then 'unverified'
      when b.updated_at < now() - interval '24 hours' then 'stale'
      when greatest(0, b.on_hand - b.reserved) = 0 then 'out_of_stock'
      when greatest(0, b.on_hand - b.reserved) <= 3 then 'low_stock'
      else 'in_stock'
    end as stock_status,
    b.updated_at as checked_at
  from public.products p
  left join public.inventory_balances b on b.product_id = p.id
  where p.status = 'published'
    and (p_product_ids is null or p.id = any(p_product_ids))
  order by p.name asc;
$function$;

revoke all on function public.oto_public_stock_status(uuid[]) from public;
grant execute on function public.oto_public_stock_status(uuid[]) to anon, authenticated;
