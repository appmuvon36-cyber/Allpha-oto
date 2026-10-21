-- EC-08: durable integration outbox, explicit WhatsApp consent, and reconciliation history.
-- All tables are server-only. Customer consent changes are exposed through one guarded RPC.
create table if not exists public.oto_notification_preferences (
  customer_user_id uuid primary key references auth.users(id) on delete cascade,
  whatsapp_opt_in boolean not null default false,
  consent_version text,
  consented_at timestamptz,
  revoked_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint oto_notification_preferences_consent_version_length check (consent_version is null or length(consent_version) between 1 and 80),
  constraint oto_notification_preferences_consent_state check (
    (whatsapp_opt_in = true and consented_at is not null and revoked_at is null)
    or (whatsapp_opt_in = false and revoked_at is not null)
    or (whatsapp_opt_in = false and consented_at is null and revoked_at is null)
  )
);
alter table public.oto_notification_preferences enable row level security;
revoke all on public.oto_notification_preferences from public, anon, authenticated;
grant select, insert, update, delete on public.oto_notification_preferences to service_role;

create table if not exists public.oto_integration_outbox (
  id uuid primary key default gen_random_uuid(),
  event_key text not null unique,
  provider text not null check (provider in ('whatsapp_cloud')),
  event_type text not null check (event_type in ('whatsapp_template')),
  correlation_id text not null,
  aggregate_type text not null,
  aggregate_id uuid,
  payload jsonb not null default '{}'::jsonb,
  payload_fingerprint text not null,
  status text not null default 'pending' check (status in ('pending','processing','retry','delivered','dead_letter')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 8 check (max_attempts between 1 and 20),
  next_attempt_at timestamptz not null default now(),
  locked_at timestamptz,
  lock_token uuid,
  last_error_code text,
  last_error_at timestamptz,
  delivered_at timestamptz,
  provider_message_id text,
  response_digest text,
  last_admin_actor_user_id uuid,
  last_admin_request_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint oto_integration_outbox_payload_size check (octet_length(payload::text) <= 16384),
  constraint oto_integration_outbox_lock_state check (
    (status = 'processing' and locked_at is not null and lock_token is not null)
    or (status <> 'processing' and lock_token is null)
  )
);
create index if not exists oto_integration_outbox_due_idx
  on public.oto_integration_outbox(status, next_attempt_at, created_at)
  where status in ('pending','retry','processing');
create index if not exists oto_integration_outbox_correlation_idx
  on public.oto_integration_outbox(correlation_id, created_at desc);
create index if not exists oto_integration_outbox_aggregate_idx
  on public.oto_integration_outbox(aggregate_type, aggregate_id, created_at desc);
alter table public.oto_integration_outbox enable row level security;
revoke all on public.oto_integration_outbox from public, anon, authenticated;
grant select, insert, update, delete on public.oto_integration_outbox to service_role;

create table if not exists public.oto_integration_reconciliation_runs (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  run_type text not null,
  status text not null check (status in ('running','completed','partial','failed')),
  correlation_id text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  scanned_count integer not null default 0 check (scanned_count >= 0),
  matched_count integer not null default 0 check (matched_count >= 0),
  mismatch_count integer not null default 0 check (mismatch_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  summary jsonb not null default '{}'::jsonb,
  created_by uuid,
  created_at timestamptz not null default now(),
  constraint oto_integration_reconciliation_summary_size check (octet_length(summary::text) <= 12000)
);
create index if not exists oto_integration_reconciliation_recent_idx
  on public.oto_integration_reconciliation_runs(started_at desc, provider, status);
alter table public.oto_integration_reconciliation_runs enable row level security;
revoke all on public.oto_integration_reconciliation_runs from public, anon, authenticated;
grant select, insert, update on public.oto_integration_reconciliation_runs to service_role;

create or replace function public.oto_whatsapp_consent_set(p_opt_in boolean, p_consent_version text, p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare a uuid := auth.uid(); prof public.user_profiles%rowtype; pref public.oto_notification_preferences%rowtype; prior public.audit_logs%rowtype;
begin
  if a is null then raise exception using errcode='42501', message='authentication_required'; end if;
  if p_request_id is null or length(p_request_id) < 8 or length(p_request_id) > 128 then
    raise exception using errcode='22023', message='request_id_invalid';
  end if;
  if p_opt_in and (p_consent_version is null or length(trim(p_consent_version)) < 1 or length(p_consent_version) > 80) then
    raise exception using errcode='22023', message='consent_version_required';
  end if;
  select * into prof from public.user_profiles where id=a for update;
  if not found or prof.is_active is not true or prof.role <> 'customer' then
    raise exception using errcode='42501', message='active_customer_required';
  end if;
  select * into prior from public.audit_logs where actor_user_id=a and request_id=p_request_id and entity_type='notification_preference' limit 1;
  if found then
    if prior.action <> case when p_opt_in then 'whatsapp_notification_opt_in' else 'whatsapp_notification_opt_out' end
       or coalesce(prior.details->>'consent_version','') <> coalesce(case when p_opt_in then trim(p_consent_version) else null end,'') then
      raise exception using errcode='23505', message='consent_request_id_payload_conflict';
    end if;
    select * into pref from public.oto_notification_preferences where customer_user_id=a;
    return jsonb_build_object('customer_user_id',pref.customer_user_id,'whatsapp_opt_in',pref.whatsapp_opt_in,
      'consent_version',pref.consent_version,'consented_at',pref.consented_at,'revoked_at',pref.revoked_at,'updated_at',pref.updated_at,'replayed',true);
  end if;
  insert into public.oto_notification_preferences(customer_user_id,whatsapp_opt_in,consent_version,consented_at,revoked_at,updated_at)
  values(a,p_opt_in,case when p_opt_in then trim(p_consent_version) else null end,
         case when p_opt_in then now() else null end,
         case when p_opt_in then null else now() end,now())
  on conflict(customer_user_id) do update set
    whatsapp_opt_in=excluded.whatsapp_opt_in,
    consent_version=case when excluded.whatsapp_opt_in then excluded.consent_version else public.oto_notification_preferences.consent_version end,
    consented_at=case when excluded.whatsapp_opt_in then now() else public.oto_notification_preferences.consented_at end,
    revoked_at=case when excluded.whatsapp_opt_in then null else now() end,
    updated_at=now()
  returning * into pref;
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(a,case when p_opt_in then 'whatsapp_notification_opt_in' else 'whatsapp_notification_opt_out' end,
         'notification_preference',a,p_request_id,jsonb_build_object('channel','whatsapp','opt_in',p_opt_in,
         'consent_version',case when p_opt_in then trim(p_consent_version) else null end));
  return jsonb_build_object('customer_user_id',pref.customer_user_id,'whatsapp_opt_in',pref.whatsapp_opt_in,
    'consent_version',pref.consent_version,'consented_at',pref.consented_at,'revoked_at',pref.revoked_at,'updated_at',pref.updated_at,'replayed',false);
end;
$function$;
revoke all on function public.oto_whatsapp_consent_set(boolean,text,text) from public, anon;
grant execute on function public.oto_whatsapp_consent_set(boolean,text,text) to authenticated;

create or replace function public.oto_integration_outbox_enqueue(
 p_event_key text, p_provider text, p_event_type text, p_correlation_id text,
 p_aggregate_type text, p_aggregate_id uuid, p_payload jsonb, p_payload_fingerprint text
) returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; inserted_count integer;
begin
  if coalesce(auth.jwt()->>'role','') <> 'service_role' then raise exception using errcode='42501', message='service_role_required'; end if;
  if p_event_key is null or length(p_event_key) < 8 or length(p_event_key) > 240
     or p_provider <> 'whatsapp_cloud' or p_event_type <> 'whatsapp_template'
     or p_correlation_id is null or length(p_correlation_id) < 8 or length(p_correlation_id) > 128
     or p_aggregate_type is null or length(p_aggregate_type) > 80
     or p_payload is null or octet_length(p_payload::text) > 16384
     or p_payload_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception using errcode='22023', message='outbox_fields_invalid';
  end if;
  insert into public.oto_integration_outbox(event_key,provider,event_type,correlation_id,aggregate_type,aggregate_id,payload,payload_fingerprint)
  values(p_event_key,p_provider,p_event_type,p_correlation_id,p_aggregate_type,p_aggregate_id,p_payload,p_payload_fingerprint)
  on conflict(event_key) do nothing;
  get diagnostics inserted_count = row_count;
  select * into r from public.oto_integration_outbox where event_key=p_event_key for update;
  if r.payload_fingerprint <> p_payload_fingerprint then
    raise exception using errcode='23505', message='outbox_event_key_payload_conflict';
  end if;
  return jsonb_build_object('id',r.id,'event_key',r.event_key,'status',r.status,'correlation_id',r.correlation_id,
    'attempt_count',r.attempt_count,'replayed',(inserted_count=0));
end;
$function$;
revoke all on function public.oto_integration_outbox_enqueue(text,text,text,text,text,uuid,jsonb,text) from public, anon, authenticated;
grant execute on function public.oto_integration_outbox_enqueue(text,text,text,text,text,uuid,jsonb,text) to service_role;

create or replace function public.oto_integration_outbox_claim(p_limit integer default 10, p_lease_seconds integer default 90)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare claimed jsonb;
begin
  if coalesce(auth.jwt()->>'role','') <> 'service_role' then raise exception using errcode='42501', message='service_role_required'; end if;
  if p_limit < 1 or p_limit > 50 or p_lease_seconds < 15 or p_lease_seconds > 600 then
    raise exception using errcode='22023', message='claim_bounds_invalid';
  end if;
  update public.oto_integration_outbox set status='dead_letter',lock_token=null,locked_at=null,
    last_error_code=coalesce(last_error_code,'attempt_limit_exhausted'),last_error_at=now(),updated_at=now()
  where status='processing' and locked_at < now() - make_interval(secs=>p_lease_seconds) and attempt_count >= max_attempts;
  with picked as (
    select id from public.oto_integration_outbox
    where ((status in ('pending','retry') and next_attempt_at <= now())
       or (status='processing' and locked_at < now() - make_interval(secs=>p_lease_seconds) and attempt_count < max_attempts))
      and attempt_count < max_attempts
    order by next_attempt_at,created_at
    for update skip locked limit p_limit
  ), updated as (
    update public.oto_integration_outbox o set status='processing',attempt_count=o.attempt_count+1,
      locked_at=now(),lock_token=gen_random_uuid(),updated_at=now()
    from picked where o.id=picked.id returning o.*
  )
  select coalesce(jsonb_agg(to_jsonb(updated) order by updated.created_at),'[]'::jsonb) into claimed from updated;
  return claimed;
end;
$function$;
revoke all on function public.oto_integration_outbox_claim(integer,integer) from public, anon, authenticated;
grant execute on function public.oto_integration_outbox_claim(integer,integer) to service_role;

create or replace function public.oto_integration_outbox_complete(p_id uuid,p_lock_token uuid,p_provider_message_id text,p_response_digest text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype;
begin
  if coalesce(auth.jwt()->>'role','') <> 'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
  update public.oto_integration_outbox set status='delivered',delivered_at=now(),provider_message_id=left(p_provider_message_id,240),
    response_digest=left(p_response_digest,64),last_error_code=null,locked_at=null,lock_token=null,updated_at=now()
  where id=p_id and status='processing' and lock_token=p_lock_token returning * into r;
  if not found then raise exception using errcode='40001',message='outbox_lease_lost'; end if;
  return jsonb_build_object('id',r.id,'status',r.status,'delivered_at',r.delivered_at,'correlation_id',r.correlation_id);
end;
$function$;
revoke all on function public.oto_integration_outbox_complete(uuid,uuid,text,text) from public, anon, authenticated;
grant execute on function public.oto_integration_outbox_complete(uuid,uuid,text,text) to service_role;

create or replace function public.oto_integration_outbox_fail(p_id uuid,p_lock_token uuid,p_error_code text,p_retryable boolean)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; v_status text; v_delay integer;
begin
  if coalesce(auth.jwt()->>'role','') <> 'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
  select * into r from public.oto_integration_outbox where id=p_id and status='processing' and lock_token=p_lock_token for update;
  if not found then raise exception using errcode='40001',message='outbox_lease_lost'; end if;
  v_status := case when p_retryable and r.attempt_count < r.max_attempts then 'retry' else 'dead_letter' end;
  v_delay := least(3600, 5 * (2 ^ greatest(0,r.attempt_count-1))::integer);
  update public.oto_integration_outbox set status=v_status,next_attempt_at=now()+make_interval(secs=>v_delay),
    last_error_code=left(coalesce(nullif(p_error_code,''),'provider_error'),100),last_error_at=now(),
    locked_at=null,lock_token=null,updated_at=now() where id=p_id returning * into r;
  return jsonb_build_object('id',r.id,'status',r.status,'attempt_count',r.attempt_count,'next_attempt_at',r.next_attempt_at,
    'last_error_code',r.last_error_code,'correlation_id',r.correlation_id);
end;
$function$;
revoke all on function public.oto_integration_outbox_fail(uuid,uuid,text,boolean) from public, anon, authenticated;
grant execute on function public.oto_integration_outbox_fail(uuid,uuid,text,boolean) to service_role;

create or replace function public.oto_integration_outbox_requeue(p_id uuid,p_actor_user_id uuid,p_request_id text)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog','public'
as $function$
declare r public.oto_integration_outbox%rowtype; old_status text;
begin
  if coalesce(auth.jwt()->>'role','') <> 'service_role' then raise exception using errcode='42501',message='service_role_required'; end if;
  if p_actor_user_id is null or p_request_id is null or length(p_request_id)<8 or length(p_request_id)>128 then
    raise exception using errcode='22023',message='requeue_fields_invalid';
  end if;
  select * into r from public.oto_integration_outbox where id=p_id for update;
  if not found then raise exception using errcode='P0002',message='outbox_record_not_found'; end if;
  if r.last_admin_actor_user_id=p_actor_user_id and r.last_admin_request_id=p_request_id then
    return jsonb_build_object('id',r.id,'status',r.status,'replayed',true,'correlation_id',r.correlation_id);
  end if;
  if r.status not in ('dead_letter','retry') then raise exception using errcode='22023',message='outbox_record_not_retriable'; end if;
  old_status := r.status;
  update public.oto_integration_outbox set status='pending',attempt_count=0,next_attempt_at=now(),last_error_code=null,
    last_error_at=null,locked_at=null,lock_token=null,last_admin_actor_user_id=p_actor_user_id,
    last_admin_request_id=p_request_id,updated_at=now() where id=p_id returning * into r;
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(p_actor_user_id,'integration_outbox_requeued','oto_integration_outbox',p_id,p_request_id,
    jsonb_build_object('previous_status',old_status,'correlation_id',r.correlation_id,'provider',r.provider));
  return jsonb_build_object('id',r.id,'status',r.status,'replayed',false,'correlation_id',r.correlation_id);
end;
$function$;
revoke all on function public.oto_integration_outbox_requeue(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.oto_integration_outbox_requeue(uuid,uuid,text) to service_role;
