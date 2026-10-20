-- Keep the order's last fulfillment event timestamp synchronized with status transitions.
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
    update public.oto_orders set shipping_last_event_at=now() where id=new.id;
  end if;
  return new;
end;
$function$;
revoke all on function public.oto_fulfillment_order_status_event() from public, anon, authenticated;
