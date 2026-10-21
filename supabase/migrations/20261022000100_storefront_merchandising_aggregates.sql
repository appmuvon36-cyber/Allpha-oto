-- Public storefront aggregates expose only published product IDs and aggregate counts.
-- They do not expose order IDs, customer identifiers, payment details, or raw search terms.
create or replace function public.oto_public_homepage_best_sellers(p_limit integer default 8)
returns table(product_id uuid, units_sold bigint)
language sql
stable
security definer
set search_path = public
as $$
  select oi.product_id, sum(oi.quantity)::bigint as units_sold
  from public.oto_order_items oi
  join public.oto_orders o on o.id = oi.order_id
  join public.products p on p.id = oi.product_id
  where p.status = 'published'
    and o.status in ('paid', 'processing', 'shipped', 'delivered')
    and oi.product_id is not null
  group by oi.product_id
  order by sum(oi.quantity) desc, oi.product_id
  limit greatest(1, least(coalesce(p_limit, 8), 24));
$$;

create or replace function public.oto_public_homepage_popular(
  p_since timestamptz default date_trunc('month', now()),
  p_limit integer default 8
)
returns table(product_id uuid, search_events bigint)
language sql
stable
security definer
set search_path = public
as $$
  select e.product_id, count(*)::bigint as search_events
  from public.oto_product_search_events e
  join public.products p on p.id = e.product_id
  where p.status = 'published'
    and e.product_id is not null
    and e.created_at >= coalesce(p_since, date_trunc('month', now()))
  group by e.product_id
  order by count(*) desc, e.product_id
  limit greatest(1, least(coalesce(p_limit, 8), 24));
$$;

revoke all on function public.oto_public_homepage_best_sellers(integer) from public;
revoke all on function public.oto_public_homepage_popular(timestamptz, integer) from public;
grant execute on function public.oto_public_homepage_best_sellers(integer) to anon, authenticated;
grant execute on function public.oto_public_homepage_popular(timestamptz, integer) to anon, authenticated;
