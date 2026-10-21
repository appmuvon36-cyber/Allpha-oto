-- EC-08: authenticate and deduplicate WhatsApp delivery status callbacks.
alter table public.oto_integration_outbox drop constraint if exists oto_integration_outbox_status_check;
update public.oto_integration_outbox set status='provider_accepted' where status='delivered';
alter table public.oto_integration_outbox add constraint oto_integration_outbox_status_check
 check (status in ('pending','processing','retry','provider_accepted','dead_letter'));
alter table public.oto_integration_outbox add column if not exists provider_delivery_status text;
alter table public.oto_integration_outbox drop constraint if exists oto_integration_outbox_provider_delivery_status_check;
alter table public.oto_integration_outbox add constraint oto_integration_outbox_provider_delivery_status_check
 check (provider_delivery_status is null or provider_delivery_status in ('sent','delivered','read','failed'));

create table if not exists public.oto_whatsapp_webhook_events (
 id uuid primary key default gen_random_uuid(),
 provider_event_key text not null unique,
 provider_message_id text not null,
 status text not null check (status in ('sent','delivered','read','failed')),
 recipient_id text,
 provider_timestamp timestamptz,
 correlation_id text,
 payload_digest text not null check (payload_digest ~ '^[0-9a-f]{64}$'),
 error_code text,
 received_at timestamptz not null default now(),
 constraint oto_whatsapp_webhook_digest_size check (length(payload_digest)=64)
);
create index if not exists oto_whatsapp_webhook_message_idx
 on public.oto_whatsapp_webhook_events(provider_message_id,provider_timestamp desc);
create index if not exists oto_whatsapp_webhook_correlation_idx
 on public.oto_whatsapp_webhook_events(correlation_id,received_at desc);
alter table public.oto_whatsapp_webhook_events enable row level security;
revoke all on public.oto_whatsapp_webhook_events from public,anon,authenticated;
grant select,insert,update,delete on public.oto_whatsapp_webhook_events to service_role;

create or replace function public.oto_whatsapp_webhook_event_record(
 p_event_key text,p_message_id text,p_status text,p_recipient_id text,p_provider_timestamp timestamptz,
 p_correlation_id text,p_payload_digest text,p_error_code text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare ev public.oto_whatsapp_webhook_events%rowtype; inserted_count integer; v_correlation text;
begin
 if coalesce(auth.jwt()->>'role','')<>'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 if p_event_key is null or length(p_event_key)<8 or length(p_event_key)>300
  or p_message_id is null or length(p_message_id)>240
  or p_status not in ('sent','delivered','read','failed')
  or p_payload_digest !~ '^[0-9a-f]{64}$'
  or (p_correlation_id is not null and length(p_correlation_id)>128)
  or (p_error_code is not null and length(p_error_code)>100) then
  raise exception using errcode='22023',message='whatsapp_webhook_fields_invalid';
 end if;
 select o.correlation_id into v_correlation from public.oto_integration_outbox o
  where o.provider_message_id=p_message_id order by o.updated_at desc limit 1;
 v_correlation:=coalesce(p_correlation_id,v_correlation);
 insert into public.oto_whatsapp_webhook_events(provider_event_key,provider_message_id,status,recipient_id,provider_timestamp,
  correlation_id,payload_digest,error_code)
 values(p_event_key,p_message_id,p_status,left(p_recipient_id,80),p_provider_timestamp,v_correlation,p_payload_digest,left(p_error_code,100))
 on conflict(provider_event_key) do nothing;
 get diagnostics inserted_count=row_count;
 select * into ev from public.oto_whatsapp_webhook_events where provider_event_key=p_event_key for update;
 if ev.payload_digest<>p_payload_digest or ev.provider_message_id<>p_message_id or ev.status<>p_status then
  raise exception using errcode='23505',message='whatsapp_webhook_event_payload_conflict';
 end if;
 update public.oto_integration_outbox set provider_delivery_status=p_status,
  last_error_code=case when p_status='failed' then coalesce(left(p_error_code,100),'whatsapp_delivery_failed') else last_error_code end,
  last_error_at=case when p_status='failed' then now() else last_error_at end,updated_at=now()
 where provider_message_id=p_message_id;
 return jsonb_build_object('id',ev.id,'status',ev.status,'correlation_id',ev.correlation_id,'replayed',(inserted_count=0));
end;
$function$;
revoke all on function public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text) from public,anon,authenticated;
grant execute on function public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text) to service_role;

create or replace function public.oto_integration_outbox_requeue(p_id uuid,p_actor_user_id uuid,p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; old_status text;
begin
 if coalesce(auth.jwt()->>'role','')<>'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 if p_actor_user_id is null or p_request_id is null or length(p_request_id)<8 or length(p_request_id)>128 then
  raise exception using errcode='22023',message='requeue_fields_invalid';
 end if;
 select * into r from public.oto_integration_outbox where id=p_id for update;
 if not found then raise exception using errcode='P0002',message='outbox_record_not_found'; end if;
 if r.last_admin_actor_user_id=p_actor_user_id and r.last_admin_request_id=p_request_id then
  return jsonb_build_object('id',r.id,'status',r.status,'replayed',true,'correlation_id',r.correlation_id);
 end if;
 if r.status not in ('dead_letter','retry') and not (r.status='provider_accepted' and r.provider_delivery_status='failed') then
  raise exception using errcode='22023',message='outbox_record_not_retriable';
 end if;
 old_status:=r.status;
 update public.oto_integration_outbox set status='pending',attempt_count=0,next_attempt_at=now(),last_error_code=null,
  last_error_at=null,locked_at=null,lock_token=null,provider_message_id=null,provider_delivery_status=null,
  last_admin_actor_user_id=p_actor_user_id,last_admin_request_id=p_request_id,updated_at=now()
 where id=p_id returning * into r;
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(p_actor_user_id,'integration_outbox_requeued','oto_integration_outbox',p_id,p_request_id,
  jsonb_build_object('previous_status',old_status,'correlation_id',r.correlation_id,'provider',r.provider));
 return jsonb_build_object('id',r.id,'status',r.status,'replayed',false,'correlation_id',r.correlation_id);
end;
$function$;
revoke all on function public.oto_integration_outbox_requeue(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.oto_integration_outbox_requeue(uuid,uuid,text) to service_role;
