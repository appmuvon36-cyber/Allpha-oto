-- EC-01: narrow public category RPC to avoid exposing inactive category records.
create or replace function public.oto_public_product_categories()
returns table (
  id uuid,
  parent_id uuid,
  name text,
  slug text,
  code text,
  description text,
  vehicle_scope text,
  sort_order integer,
  is_active boolean
)
language sql
stable
security definer
set search_path to 'pg_catalog', 'public'
as $function$
  select c.id, c.parent_id, c.name, c.slug, c.code, c.description, c.vehicle_scope, c.sort_order, c.is_active
  from public.product_categories c
  where c.is_active is true
  order by c.sort_order asc, c.name asc
  limit 500;
$function$;

revoke all on function public.oto_public_product_categories() from public;
grant execute on function public.oto_public_product_categories() to anon, authenticated;
