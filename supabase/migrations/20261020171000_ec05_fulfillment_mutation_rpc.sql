-- EC-05 transactional fulfillment mutation RPC. No external tracking calls are made.
create or replace function public.oto_fulfillment_mutate(
  p_order_id uuid,
  p_action text,
  p_payload jsonb,
  p_request_id text
) returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $function$
declare
  a uuid := auth.uid();
  r public.oto_orders%rowtype;
  v_carrier text;
  v_service text;
  v_tracking text;
  v_note text;
  v_code text;
  v_fingerprint text;
  v_previous public.oto_idempotency_records%rowtype;
  v_result jsonb;
  v_from text;
  v_to text;
  v_event text;
begin
  if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
  if not public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]) then
    raise exception using errcode='42501',message='order_role_required';
  end if;
  if p_action not in ('start_fulfillment','pack_order','mark_shipped','mark_delivered','record_exception','resolve_exception','update_tracking') then
    raise exception using errcode='22023',message='unsupported_fulfillment_action';
  end if;
  if p_request_id is null or length(p_request_id)<8 or length(p_request_id)>128 then
    raise exception using errcode='22023',message='idempotency_key_invalid';
  end if;
  if p_payload is null or jsonb_typeof(p_payload)<>'object' then
    raise exception using errcode='22023',message='fulfillment_payload_invalid';
  end if;
  v_fingerprint := encode(extensions.digest(p_action || ':' || p_order_id::text || ':' || p_payload::text,'sha256'),'hex');
  perform pg_advisory_xact_lock(hashtextextended(a::text || ':' || p_request_id,0));
  select * into v_previous from public.oto_idempotency_records
   where actor_user_id=a and request_id=p_request_id;
  if found then
    if v_previous.payload_fingerprint<>v_fingerprint then
      raise exception using errcode='23505',message='idempotency_key_payload_conflict';
    end if;
    return v_previous.result || jsonb_build_object('replayed',true);
  end if;

  select * into r from public.oto_orders where id=p_order_id for update;
  if not found then raise exception using errcode='P0002',message='order_not_found'; end if;
  v_from:=r.status;
  v_carrier:=nullif(btrim(p_payload->>'carrier'),'');
  v_service:=nullif(btrim(p_payload->>'service'),'');
  v_tracking:=nullif(btrim(p_payload->>'tracking_code'),'');
  v_note:=nullif(btrim(p_payload->>'note'),'');
  v_code:=nullif(btrim(p_payload->>'exception_code'),'');

  if p_action='start_fulfillment' then
    if r.status<>'paid' then raise exception using errcode='22023',message='verified_paid_order_required'; end if;
    update public.oto_orders set status='processing',updated_at=now() where id=r.id returning * into r;
    v_event:='fulfillment_started';
  elsif p_action='pack_order' then
    if r.status<>'processing' then raise exception using errcode='22023',message='processing_order_required'; end if;
    v_event:='packed';
  elsif p_action='mark_shipped' then
    if r.status<>'processing' then raise exception using errcode='22023',message='processing_order_required'; end if;
    if v_tracking is null or length(v_tracking)>120 or v_carrier is null or length(v_carrier)>80 or v_service is null or length(v_service)>80 then
      raise exception using errcode='22023',message='carrier_service_tracking_required';
    end if;
    if not exists(select 1 from public.oto_payment_events p where p.order_id=r.id and p.event_type='payment' and p.status='verified' and p.amount=r.total_amount)
       and not exists(select 1 from public.oto_payment_intents p where p.order_id=r.id and p.status in ('paid','capture','settlement') and p.amount=r.total_amount) then
      raise exception using errcode='22023',message='verified_payment_required_before_shipping';
    end if;
    update public.oto_orders set status='shipped',tracking_code=v_tracking,shipping_carrier=v_carrier,shipping_service=v_service,shipped_at=now(),shipping_exception_code=null,shipping_exception_note=null,updated_at=now() where id=r.id returning * into r;
    for v_result in select to_jsonb(res) from public.inventory_reservations res where res.order_id=r.id and res.status='reserved' order by res.product_id for update loop
      update public.inventory_balances set on_hand=on_hand-(v_result->>'quantity')::integer,reserved=reserved-(v_result->>'quantity')::integer,updated_at=now()
       where product_id=(v_result->>'product_id')::uuid and on_hand>=(v_result->>'quantity')::integer and reserved>=(v_result->>'quantity')::integer;
      if not found then raise exception using errcode='23514',message='reservation_balance_inconsistent'; end if;
      update public.inventory_reservations set status='consumed',updated_at=now() where id=(v_result->>'id')::uuid;
      insert into public.inventory_ledger(product_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id)
      values((v_result->>'product_id')::uuid,'sale',-((v_result->>'quantity')::integer),'order',r.id,'Fulfillment shipped; reserved stock consumed',a);
    end loop;
    v_event:='shipped';
  elsif p_action='mark_delivered' then
    if r.status<>'shipped' then raise exception using errcode='22023',message='shipped_order_required'; end if;
    update public.oto_orders set status='delivered',delivered_at=now(),shipping_exception_code=null,shipping_exception_note=null,updated_at=now() where id=r.id returning * into r;
    v_event:='delivered';
  elsif p_action='record_exception' then
    if r.status not in ('shipped','processing') or v_code is null or v_note is null then
      raise exception using errcode='22023',message='active_fulfillment_and_exception_details_required';
    end if;
    update public.oto_orders set shipping_exception_code=left(v_code,80),shipping_exception_note=left(v_note,1000),shipping_last_event_at=now(),updated_at=now() where id=r.id returning * into r;
    v_event:=case when v_code='delivery_attempt_failed' then 'delivery_attempt_failed' else 'delivery_exception' end;
  elsif p_action='resolve_exception' then
    if r.shipping_exception_code is null or v_note is null then raise exception using errcode='22023',message='unresolved_exception_and_note_required'; end if;
    update public.oto_orders set shipping_exception_code=null,shipping_exception_note=null,shipping_last_event_at=now(),updated_at=now() where id=r.id returning * into r;
    v_event:='exception_resolved';
  elsif p_action='update_tracking' then
    if r.status<>'shipped' or v_tracking is null or v_carrier is null or v_service is null then
      raise exception using errcode='22023',message='shipped_order_and_tracking_metadata_required';
    end if;
    update public.oto_orders set tracking_code=v_tracking,shipping_carrier=v_carrier,shipping_service=v_service,shipping_last_event_at=now(),updated_at=now() where id=r.id returning * into r;
    v_event:='tracking_updated';
  end if;

  -- Status transitions are captured by the order trigger. Write explicit events only
  -- for actions that do not change status, avoiding duplicate shipped/delivered events.
  if p_action in ('pack_order','record_exception','resolve_exception','update_tracking') then
    insert into public.oto_fulfillment_events(order_id,actor_user_id,event_type,from_status,to_status,carrier,service,tracking_code,note,metadata)
    values(r.id,a,v_event,v_from,r.status,coalesce(v_carrier,r.shipping_carrier),coalesce(v_service,r.shipping_service),coalesce(v_tracking,r.tracking_code),v_note,
      jsonb_build_object('source','admin_fulfillment_rpc','exception_code',v_code));
  end if;
  v_result:=jsonb_build_object('order',to_jsonb(r),'event_type',v_event,'replayed',false);
  insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
  values(a,p_request_id,'fulfillment_'||p_action,r.id,v_fingerprint,v_result);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(a,'fulfillment_'||p_action,'order',r.id,p_request_id,jsonb_build_object('from_status',v_from,'to_status',r.status,'event_type',v_event,'carrier',r.shipping_carrier,'service',r.shipping_service,'tracking_code',r.tracking_code,'exception_code',r.shipping_exception_code));
  return v_result;
end;
$function$;
revoke all on function public.oto_fulfillment_mutate(uuid,text,jsonb,text) from public,anon;
grant execute on function public.oto_fulfillment_mutate(uuid,text,jsonb,text) to authenticated;

create or replace function public.oto_fulfillment_order_status_event()
returns trigger language plpgsql security definer set search_path=public,pg_temp as $function$
declare v_actor uuid; v_event text;
begin
 if tg_op<>'UPDATE' or new.status is not distinct from old.status then return new; end if;
 v_actor:=auth.uid();
 v_event:=case new.status when 'paid' then 'order_paid' when 'processing' then 'fulfillment_started' when 'shipped' then 'shipped' when 'delivered' then 'delivered' else null end;
 if v_event is not null then
  insert into public.oto_fulfillment_events(order_id,actor_user_id,event_type,from_status,to_status,carrier,service,tracking_code,metadata)
  values(new.id,v_actor,v_event,old.status,new.status,new.shipping_carrier,new.shipping_service,new.tracking_code,jsonb_build_object('source','order_status_transition'));
 end if;
 return new;
end;$function$;
