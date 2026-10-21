-- EC-08 hardening: serialize consent idempotency and report exact outbox enqueue replay state.
create or replace function public.oto_whatsapp_consent_set(p_opt_in boolean,p_consent_version text,p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare a uuid:=auth.uid(); prof public.user_profiles%rowtype; pref public.oto_notification_preferences%rowtype; prior public.audit_logs%rowtype;
begin
 if a is null then raise exception using errcode='42501',message='authentication_required'; end if;
 if p_request_id is null or length(p_request_id)<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_invalid'; end if;
 if p_opt_in and (p_consent_version is null or length(trim(p_consent_version))<1 or length(p_consent_version)>80) then
  raise exception using errcode='22023',message='consent_version_required';
 end if;
 perform pg_advisory_xact_lock(hashtextextended('whatsapp-consent:'||a::text||':'||p_request_id,0));
 select * into prof from public.user_profiles where id=a for update;
 if not found or prof.is_active is not true or prof.role<>'customer' then raise exception using errcode='42501',message='active_customer_required'; end if;
 select * into prior from public.audit_logs where actor_user_id=a and request_id=p_request_id and entity_type='notification_preference' limit 1;
 if found then
  if prior.action <> (case when p_opt_in then 'whatsapp_notification_opt_in' else 'whatsapp_notification_opt_out' end)
     or coalesce(prior.details->>'consent_version','') <> coalesce((case when p_opt_in then trim(p_consent_version) else null end),'') then
   raise exception using errcode='23505',message='consent_request_id_payload_conflict';
  end if;
  select * into pref from public.oto_notification_preferences where customer_user_id=a;
  return jsonb_build_object('customer_user_id',pref.customer_user_id,'whatsapp_opt_in',pref.whatsapp_opt_in,
   'consent_version',pref.consent_version,'consented_at',pref.consented_at,'revoked_at',pref.revoked_at,'updated_at',pref.updated_at,'replayed',true);
 end if;
 insert into public.oto_notification_preferences(customer_user_id,whatsapp_opt_in,consent_version,consented_at,revoked_at,updated_at)
 values(a,p_opt_in,case when p_opt_in then trim(p_consent_version) else null end,
  case when p_opt_in then now() else null end,case when p_opt_in then null else now() end,now())
 on conflict(customer_user_id) do update set whatsapp_opt_in=excluded.whatsapp_opt_in,
  consent_version=case when excluded.whatsapp_opt_in then excluded.consent_version else public.oto_notification_preferences.consent_version end,
  consented_at=case when excluded.whatsapp_opt_in then now() else public.oto_notification_preferences.consented_at end,
  revoked_at=case when excluded.whatsapp_opt_in then null else now() end,updated_at=now()
 returning * into pref;
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
 values(a,case when p_opt_in then 'whatsapp_notification_opt_in' else 'whatsapp_notification_opt_out' end,
  'notification_preference',a,p_request_id,jsonb_build_object('channel','whatsapp','opt_in',p_opt_in,
  'consent_version',case when p_opt_in then trim(p_consent_version) else null end));
 return jsonb_build_object('customer_user_id',pref.customer_user_id,'whatsapp_opt_in',pref.whatsapp_opt_in,
  'consent_version',pref.consent_version,'consented_at',pref.consented_at,'revoked_at',pref.revoked_at,'updated_at',pref.updated_at,'replayed',false);
end;
$function$;
revoke all on function public.oto_whatsapp_consent_set(boolean,text,text) from public,anon;
grant execute on function public.oto_whatsapp_consent_set(boolean,text,text) to authenticated;

create or replace function public.oto_integration_outbox_enqueue(
 p_event_key text,p_provider text,p_event_type text,p_correlation_id text,p_aggregate_type text,
 p_aggregate_id uuid,p_payload jsonb,p_payload_fingerprint text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; inserted_count integer;
begin
 if coalesce(auth.jwt()->>'role','')<>'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
 if p_event_key is null or length(p_event_key)<8 or length(p_event_key)>240 or p_provider<>'whatsapp_cloud'
  or p_event_type<>'whatsapp_template' or p_correlation_id is null or length(p_correlation_id)<8 or length(p_correlation_id)>128
  or p_aggregate_type is null or length(p_aggregate_type)>80 or p_payload is null or octet_length(p_payload::text)>16384
  or p_payload_fingerprint !~ '^[0-9a-f]{64}$' then raise exception using errcode='22023',message='outbox_fields_invalid'; end if;
 insert into public.oto_integration_outbox(event_key,provider,event_type,correlation_id,aggregate_type,aggregate_id,payload,payload_fingerprint)
 values(p_event_key,p_provider,p_event_type,p_correlation_id,p_aggregate_type,p_aggregate_id,p_payload,p_payload_fingerprint)
 on conflict(event_key) do nothing;
 get diagnostics inserted_count=row_count;
 select * into r from public.oto_integration_outbox where event_key=p_event_key for update;
 if r.payload_fingerprint<>p_payload_fingerprint then raise exception using errcode='23505',message='outbox_event_key_payload_conflict'; end if;
 return jsonb_build_object('id',r.id,'event_key',r.event_key,'status',r.status,'correlation_id',r.correlation_id,
  'attempt_count',r.attempt_count,'replayed',(inserted_count=0));
end;
$function$;
revoke all on function public.oto_integration_outbox_enqueue(text,text,text,text,text,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.oto_integration_outbox_enqueue(text,text,text,text,text,uuid,jsonb,text) to service_role;
