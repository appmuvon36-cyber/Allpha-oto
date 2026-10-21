-- EC-07/EC-02 bridge: staff may set a manual shipping quote only before any payment starts.
-- The active inventory reservation expiry bounds the quote's validity; order item/coupon snapshots are unchanged.
create or replace function public.oto_manual_shipping_quote_set(
  p_order_id uuid,
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
  v_amount numeric;
  v_carrier text;
  v_service text;
  v_note text;
  v_expires_at timestamptz;
  v_fingerprint text;
  v_previous public.oto_idempotency_records%rowtype;
  v_result jsonb;
  v_old_shipping_fee numeric;
  v_old_total numeric;
begin
  if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
  if not public.oto_has_staff_role(array['admin','order_manager']::public.oto_user_role[]) then
    raise exception using errcode='42501',message='order_role_required';
  end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then
    raise exception using errcode='22023',message='idempotency_key_invalid';
  end if;
  if p_payload is null or jsonb_typeof(p_payload)<>'object' then
    raise exception using errcode='22023',message='manual_shipping_quote_payload_invalid';
  end if;
  begin
    v_amount := (p_payload->>'amount')::numeric;
  exception when others then
    raise exception using errcode='22023',message='manual_shipping_quote_amount_invalid';
  end;
  v_carrier := nullif(btrim(p_payload->>'carrier'),'');
  v_service := nullif(btrim(p_payload->>'service'),'');
  v_note := nullif(btrim(p_payload->>'note'),'');
  if v_amount is null or v_amount<0 or v_amount>1000000000 or v_amount<>trunc(v_amount)
     or v_carrier is null or length(v_carrier)>80
     or v_service is null or length(v_service)>80
     or v_note is null or length(v_note)>1000 then
    raise exception using errcode='22023',message='manual_shipping_quote_payload_invalid';
  end if;

  v_fingerprint := encode(extensions.digest('manual_shipping_quote_set:'||p_order_id::text||':'||p_payload::text,'sha256'),'hex');
  perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_request_id,0));
  select * into v_previous from public.oto_idempotency_records
   where actor_user_id=a and request_id=p_request_id;
  if found then
    if v_previous.action<>'manual_shipping_quote_set'
       or v_previous.target_id is distinct from p_order_id
       or v_previous.payload_fingerprint<>v_fingerprint then
      raise exception using errcode='23505',message='idempotency_key_payload_conflict';
    end if;
    return v_previous.result || jsonb_build_object('replayed',true);
  end if;

  select * into r from public.oto_orders where id=p_order_id for update;
  if not found then raise exception using errcode='P0002',message='order_not_found'; end if;
  if r.status<>'pending_payment' then
    raise exception using errcode='22023',message='manual_shipping_quote_requires_pending_payment_order';
  end if;
  if exists(select 1 from public.oto_payment_events p where p.order_id=r.id)
     or exists(select 1 from public.oto_payment_intents p where p.order_id=r.id) then
    raise exception using errcode='22023',message='manual_shipping_quote_blocked_after_payment_started';
  end if;
  if exists(select 1 from public.inventory_reservations x where x.order_id=r.id and x.status='reserved' and x.expires_at<=now())
     or not exists(select 1 from public.inventory_reservations x where x.order_id=r.id and x.status='reserved' and x.expires_at>now()) then
    raise exception using errcode='22023',message='manual_shipping_quote_requires_active_reservation';
  end if;

  select min(x.expires_at) into v_expires_at
    from public.inventory_reservations x
   where x.order_id=r.id and x.status='reserved';
  v_old_shipping_fee:=r.shipping_fee;
  v_old_total:=r.total_amount;
  update public.oto_orders
     set shipping_fee=v_amount,
         shipping_carrier=v_carrier,
         shipping_service=v_service,
         total_amount=r.subtotal-r.discount_amount+v_amount,
         shipping_last_event_at=now(),
         updated_at=now()
   where id=r.id returning * into r;

  insert into public.oto_fulfillment_events(
    order_id,actor_user_id,event_type,from_status,to_status,carrier,service,note,metadata
  ) values (
    r.id,a,'manual_shipping_quote_set',r.status,r.status,v_carrier,v_service,v_note,
    jsonb_build_object('source','manual_shipping_quote','previous_shipping_fee',v_old_shipping_fee,
      'new_shipping_fee',v_amount,'previous_total_amount',v_old_total,'new_total_amount',r.total_amount,
      'quote_expires_at',v_expires_at)
  );

  v_result:=jsonb_build_object('order',to_jsonb(r),'quote_expires_at',v_expires_at,'replayed',false);
  insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
  values(a,p_request_id,'manual_shipping_quote_set',r.id,v_fingerprint,v_result);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(a,'manual_shipping_quote_set','order',r.id,p_request_id,
    jsonb_build_object('previous_shipping_fee',v_old_shipping_fee,'new_shipping_fee',v_amount,
      'previous_total_amount',v_old_total,'new_total_amount',r.total_amount,
      'carrier',v_carrier,'service',v_service,'quote_expires_at',v_expires_at));
  return v_result;
end;
$function$;

revoke all on function public.oto_manual_shipping_quote_set(uuid,jsonb,text) from public, anon;
grant execute on function public.oto_manual_shipping_quote_set(uuid,jsonb,text) to authenticated;
