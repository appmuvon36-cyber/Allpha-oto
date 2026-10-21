-- EC-09: bind payment webhook replay keys to the exact verified payload and prevent stale callbacks
-- from regressing a terminal payment intent. Additive function replacement; no production rows are rewritten.
create or replace function public.oto_payment_webhook_apply(
 p_event_key text,p_provider text,p_provider_order_id text,p_transaction_id text,p_status text,
 p_amount numeric,p_payload_digest text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare pi public.oto_payment_intents%rowtype; o public.oto_orders%rowtype; ev public.oto_payment_webhook_events%rowtype;
begin
 if coalesce(auth.jwt()->>'role',current_setting('request.jwt.claim.role',true),'')<>'service_role' then
  raise exception using errcode='42501',message='service_role_required';
 end if;
 if p_provider not in ('midtrans','rajaongkir') or p_event_key is null or length(p_event_key)<1 or length(p_event_key)>200
  or p_provider_order_id is null or length(p_provider_order_id)<1 or length(p_provider_order_id)>180
  or p_status not in ('pending','challenge','capture','settlement','deny','cancel','expire','failure','refund','partial_refund','paid','expired','failed')
  or p_payload_digest is null or p_payload_digest !~ '^[0-9a-f]{64}$' then
  raise exception using errcode='22023',message='webhook_fields_invalid';
 end if;
 perform pg_advisory_xact_lock(hashtextextended(p_provider||':'||p_event_key,0));
 select * into ev from public.oto_payment_webhook_events where provider=p_provider and provider_event_key=p_event_key for update;
 if found then
  if ev.payload_digest is distinct from p_payload_digest or ev.status is distinct from p_status then
   raise exception using errcode='23505',message='payment_webhook_event_payload_conflict';
  end if;
  return jsonb_build_object('replayed',true,'event_id',ev.id,'status',ev.status);
 end if;
 select * into pi from public.oto_payment_intents where provider=p_provider and provider_order_id=p_provider_order_id for update;
 if not found then raise exception using errcode='P0002',message='payment_intent_not_found'; end if;
 select * into o from public.oto_orders where id=pi.order_id for update;
 if p_status not in ('refund','partial_refund') and (p_amount is null or p_amount is distinct from pi.amount or p_amount is distinct from o.total_amount) then
  raise exception using errcode='23514',message='payment_amount_mismatch';
 end if;
 if p_status in ('capture','settlement','paid') then
  if o.status='pending_payment' then
   insert into public.oto_payment_events(order_id,event_type,amount,method,provider_reference,status,review_note,reviewed_at)
   values(o.id,'payment',p_amount,'provider',p_transaction_id,'verified','Verified by authenticated RajaOngkir payment callback/status reconciliation',now());
   update public.oto_orders set status='paid',updated_at=now() where id=o.id;
  elsif o.status not in ('paid','processing','shipped','delivered') then
   raise exception using errcode='22023',message='order_state_blocks_payment_settlement';
  end if;
 end if;
 update public.oto_payment_intents set
  status=case
   when status in ('settlement','capture','paid','refunded') and p_status not in ('refund','partial_refund') then status
   when p_status in ('refund','partial_refund') then 'refunded'
   when p_status='paid' then 'paid'
   when p_status='expired' then 'expired'
   when p_status='failed' then 'failed'
   else p_status end,
  provider_transaction_id=coalesce(p_transaction_id,provider_transaction_id),updated_at=now()
 where id=pi.id;
 insert into public.oto_payment_webhook_events(provider,provider_event_key,order_id,payment_intent_id,status,signature_valid,payload_digest,processed_at)
 values(p_provider,p_event_key,o.id,pi.id,p_status,true,p_payload_digest,now()) returning * into ev;
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(null,'payment_webhook_'||p_status,'oto_payment_intent',pi.id,p_event_key,jsonb_build_object('provider',p_provider,'order_id',o.id,'transaction_id',p_transaction_id,'payload_digest',p_payload_digest));
 return jsonb_build_object('replayed',false,'event_id',ev.id,'status',p_status,'order_id',o.id);
end;
$function$;
revoke all on function public.oto_payment_webhook_apply(text,text,text,text,text,numeric,text) from public,anon,authenticated;
grant execute on function public.oto_payment_webhook_apply(text,text,text,text,text,numeric,text) to service_role;
