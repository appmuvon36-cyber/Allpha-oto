-- EC-05 additive fulfillment metadata and immutable order-status timeline.
-- Existing orders, reservations, payment records and policies are preserved.
alter table public.oto_orders
  add column if not exists shipping_carrier text,
  add column if not exists shipping_service text,
  add column if not exists shipping_exception_code text,
  add column if not exists shipping_exception_note text,
  add column if not exists shipping_last_event_at timestamptz;

create table if not exists public.oto_fulfillment_events (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.oto_orders(id) on delete restrict,
  actor_user_id uuid references auth.users(id) on delete restrict,
  event_type text not null check (event_type in (
    'order_paid','fulfillment_started','packed','shipped','in_transit',
    'delivery_attempt_failed','delivery_exception','delivered',
    'tracking_updated','exception_resolved'
  )),
  from_status text,
  to_status text,
  carrier text,
  service text,
  tracking_code text,
  note text,
  metadata jsonb not null default '{}'::jsonb check(jsonb_typeof(metadata)='object'),
  created_at timestamptz not null default now()
);
create index if not exists oto_fulfillment_events_order_created_idx
  on public.oto_fulfillment_events(order_id, created_at desc);
create index if not exists oto_orders_fulfillment_queue_idx
  on public.oto_orders(status, updated_at desc)
  where status in ('paid','processing','shipped','delivered');

alter table public.oto_fulfillment_events enable row level security;
drop policy if exists "fulfillment event owner or order staff read" on public.oto_fulfillment_events;
create policy "fulfillment event owner or order staff read"
on public.oto_fulfillment_events for select to authenticated
using (
  exists (
    select 1 from public.oto_orders o
    where o.id = order_id
      and (o.customer_user_id = (select auth.uid())
        or public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]))
  )
);
revoke insert, update, delete on public.oto_fulfillment_events from public, anon, authenticated;
grant select on public.oto_fulfillment_events to authenticated;

create or replace function public.oto_fulfillment_order_status_event()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $function$
declare
  v_actor uuid;
  v_event text;
begin
  if tg_op <> 'UPDATE' or new.status is not distinct from old.status then
    return new;
  end if;

  v_actor := auth.uid();
  v_event := case new.status
    when 'paid' then 'order_paid'
    when 'processing' then 'fulfillment_started'
    when 'shipped' then 'shipped'
    when 'delivered' then 'delivered'
    else null
  end;

  if v_event is not null then
    insert into public.oto_fulfillment_events(
      order_id, actor_user_id, event_type, from_status, to_status,
      carrier, service, tracking_code, metadata
    ) values (
      new.id, v_actor, v_event, old.status, new.status,
      new.shipping_carrier, new.shipping_service, new.tracking_code,
      jsonb_build_object('source','order_status_transition')
    );
    update public.oto_orders
      set shipping_last_event_at = now()
      where id = new.id and shipping_last_event_at is distinct from now();
  end if;
  return new;
end;
$function$;

drop trigger if exists oto_orders_fulfillment_status_event on public.oto_orders;
create trigger oto_orders_fulfillment_status_event
after update of status on public.oto_orders
for each row execute function public.oto_fulfillment_order_status_event();

revoke all on function public.oto_fulfillment_order_status_event() from public, anon, authenticated;
