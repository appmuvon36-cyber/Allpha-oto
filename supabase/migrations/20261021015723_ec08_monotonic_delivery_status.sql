-- EC-08: keep delivery state monotonic when provider callbacks arrive out of order.
create or replace function public.oto_whatsapp_webhook_event_record(
 p_event_key text,p_message_id text,p_status text,p_recipient_id text,p_provider_timestamp timestamptz,
 p_correlation_id text,p_payload_digest text,p_error_code text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare ev public.oto_whatsapp_webhook_events%rowtype; inserted_count integer; v_correlation text;
 v_current_status text; v_effective_status text;
begin
 if coalesce(auth.jwt()->>'role','')<>'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 if p_event_key is null or length(p_event_key)<8 or length(p_event_key)>300 or p_message_id is null or length(p_message_id)>240
  or p_status not in ('sent','delivered','read','failed') or p_payload_digest !~ '^[0-9a-f]{64}$'
  or (p_correlation_id is not null and length(p_correlation_id)>128) or (p_error_code is not null and length(p_error_code)>100) then
  raise exception using errcode='22023',message='whatsapp_webhook_fields_invalid';
 end if;
 select o.correlation_id into v_correlation from public.oto_integration_outbox o
  where o.provider_message_id=p_message_id order by o.updated_at desc limit 1;
 v_correlation:=coalesce(p_correlation_id,v_correlation);
 insert into public.oto_whatsapp_webhook_events(provider_event_key,provider_message_id,status,recipient_id,provider_timestamp,correlation_id,payload_digest,error_code)
 values(p_event_key,p_message_id,p_status,left(p_recipient_id,80),p_provider_timestamp,v_correlation,p_payload_digest,left(p_error_code,100))
 on conflict(provider_event_key) do nothing;
 get diagnostics inserted_count=row_count;
 select * into ev from public.oto_whatsapp_webhook_events where provider_event_key=p_event_key for update;
 if ev.payload_digest<>p_payload_digest or ev.provider_message_id<>p_message_id or ev.status<>p_status then
  raise exception using errcode='23505',message='whatsapp_webhook_event_payload_conflict';
 end if;
 select o.provider_delivery_status into v_current_status from public.oto_integration_outbox o
  where o.provider_message_id=p_message_id order by o.updated_at desc limit 1 for update;
 v_effective_status := case
  when v_current_status='read' then 'read'
  when v_current_status='delivered' and p_status in ('sent','failed') then 'delivered'
  when v_current_status='failed' and p_status in ('sent','failed') then 'failed'
  else p_status end;
 update public.oto_integration_outbox set provider_delivery_status=v_effective_status,
  delivered_at=case when v_effective_status in ('delivered','read') then coalesce(delivered_at,p_provider_timestamp,now())
                    when v_effective_status='failed' then null else delivered_at end,
  last_error_code=case when v_effective_status='failed' then coalesce(left(p_error_code,100),'whatsapp_delivery_failed') else last_error_code end,
  last_error_at=case when v_effective_status='failed' then coalesce(last_error_at,now()) else last_error_at end,updated_at=now()
 where provider_message_id=p_message_id;
 return jsonb_build_object('id',ev.id,'status',ev.status,'effective_delivery_status',v_effective_status,
  'correlation_id',ev.correlation_id,'replayed',(inserted_count=0));
end;
$function$;
revoke all on function public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text) from public,anon,authenticated;
grant execute on function public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text) to service_role;

create or replace function public.oto_integration_outbox_complete(p_id uuid,p_lock_token uuid,p_provider_message_id text,p_response_digest text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; v_delivery_status text; v_delivery_time timestamptz; v_error text;
begin
 if coalesce(auth.jwt()->>'role','')<>'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 update public.oto_integration_outbox set status='provider_accepted',provider_accepted_at=now(),
  provider_message_id=left(p_provider_message_id,240),response_digest=left(p_response_digest,64),
  last_error_code=null,locked_at=null,lock_token=null,updated_at=now()
 where id=p_id and status='processing' and lock_token=p_lock_token returning * into r;
 if not found then raise exception using errcode='40001',message='outbox_lease_lost'; end if;
 select e.status,e.provider_timestamp,e.error_code into v_delivery_status,v_delivery_time,v_error
 from public.oto_whatsapp_webhook_events e where e.provider_message_id=p_provider_message_id
 order by case e.status when 'read' then 3 when 'delivered' then 2 when 'sent' then 1 else 0 end desc,
  e.provider_timestamp desc nulls last,e.received_at desc limit 1;
 if found then
  update public.oto_integration_outbox set provider_delivery_status=v_delivery_status,
   delivered_at=case when v_delivery_status in ('delivered','read') then coalesce(v_delivery_time,now()) else null end,
   last_error_code=case when v_delivery_status='failed' then coalesce(v_error,'whatsapp_delivery_failed') else last_error_code end,
   last_error_at=case when v_delivery_status='failed' then now() else last_error_at end,
   updated_at=now() where id=p_id returning * into r;
 end if;
 return jsonb_build_object('id',r.id,'status',r.status,'provider_delivery_status',r.provider_delivery_status,
  'provider_accepted_at',r.provider_accepted_at,'delivered_at',r.delivered_at,'correlation_id',r.correlation_id);
end;
$function$;
revoke all on function public.oto_integration_outbox_complete(uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.oto_integration_outbox_complete(uuid,uuid,text,text) to service_role;
