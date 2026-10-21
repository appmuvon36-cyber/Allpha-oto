-- Track anonymous search-result impressions with coarse per-client deduplication.
-- Existing events remain valid; the new field is nullable for backward compatibility.
alter table public.oto_product_search_events
  add column if not exists client_hash text;

create index if not exists oto_product_search_events_client_product_created_idx
  on public.oto_product_search_events (client_hash, product_id, created_at desc);

create or replace function public.oto_record_product_search_events(
  p_query text,
  p_product_ids uuid[],
  p_client_hash text
)
returns table(recorded_count integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_query text;
  v_recorded integer := 0;
begin
  v_query := left(trim(coalesce(p_query, '')), 100);
  if length(v_query) < 2
     or p_client_hash !~ '^[0-9a-f]{64}$'
     or coalesce(array_length(p_product_ids, 1), 0) = 0 then
    return query select 0;
    return;
  end if;

  with candidate_ids as (
    select distinct unnest(p_product_ids[1:20]) as product_id
  ), inserted as (
    insert into public.oto_product_search_events (normalized_query, product_id, client_hash)
    select v_query, c.product_id, p_client_hash
    from candidate_ids c
    join public.products p on p.id = c.product_id and p.status = 'published'
    where not exists (
      select 1
      from public.oto_product_search_events recent
      where recent.client_hash = p_client_hash
        and recent.product_id = c.product_id
        and recent.created_at > now() - interval '10 minutes'
    )
    returning 1
  )
  select count(*)::integer into v_recorded from inserted;

  return query select v_recorded;
end;
$$;

revoke all on function public.oto_record_product_search_events(text, uuid[], text) from public;
grant execute on function public.oto_record_product_search_events(text, uuid[], text) to anon, authenticated;
