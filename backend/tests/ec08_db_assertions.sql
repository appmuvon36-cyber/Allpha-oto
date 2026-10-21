do $$
begin
  if not exists (select 1 from pg_class where oid='public.oto_notification_preferences'::regclass and relrowsecurity) then
    raise exception 'notification preferences must have RLS enabled';
  end if;
  if not exists (select 1 from pg_class where oid='public.oto_integration_outbox'::regclass and relrowsecurity) then
    raise exception 'integration outbox must have RLS enabled';
  end if;
  if not exists (select 1 from pg_class where oid='public.oto_integration_reconciliation_runs'::regclass and relrowsecurity) then
    raise exception 'reconciliation runs must have RLS enabled';
  end if;
  if not exists (select 1 from pg_class where oid='public.oto_whatsapp_webhook_events'::regclass and relrowsecurity) then
    raise exception 'WhatsApp webhook events must have RLS enabled';
  end if;
  if has_table_privilege('anon','public.oto_integration_outbox','SELECT')
     or has_table_privilege('authenticated','public.oto_integration_outbox','SELECT') then
    raise exception 'outbox must not be directly readable by anon/authenticated';
  end if;
  if has_table_privilege('anon','public.oto_notification_preferences','SELECT')
     or has_table_privilege('authenticated','public.oto_notification_preferences','SELECT') then
    raise exception 'notification preferences must not be directly readable by anon/authenticated';
  end if;
  if not has_function_privilege('authenticated','public.oto_whatsapp_consent_set(boolean,text,text)','EXECUTE') then
    raise exception 'authenticated customers need the guarded consent RPC';
  end if;
  if has_function_privilege('anon','public.oto_whatsapp_consent_set(boolean,text,text)','EXECUTE') then
    raise exception 'anon must not execute the consent RPC';
  end if;
  if not has_function_privilege('service_role','public.oto_integration_outbox_claim(integer,integer)','EXECUTE') then
    raise exception 'service role must be able to claim outbox work';
  end if;
  if has_function_privilege('authenticated','public.oto_integration_outbox_claim(integer,integer)','EXECUTE')
     or has_function_privilege('anon','public.oto_integration_outbox_claim(integer,integer)','EXECUTE') then
    raise exception 'outbox worker RPC must remain service-role-only';
  end if;
  if not exists (select 1 from pg_indexes where schemaname='public' and indexname='oto_integration_outbox_due_idx') then
    raise exception 'outbox due-work index is missing';
  end if;
  if has_table_privilege('anon','public.oto_whatsapp_webhook_events','SELECT') or has_table_privilege('authenticated','public.oto_whatsapp_webhook_events','SELECT') then
    raise exception 'WhatsApp webhook events must not be directly readable by anon/authenticated';
  end if;
  if not has_function_privilege('service_role','public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text)','EXECUTE') then
    raise exception 'service role must be able to persist WhatsApp webhook events';
  end if;
  if has_function_privilege('authenticated','public.oto_whatsapp_webhook_event_record(text,text,text,text,timestamptz,text,text,text)','EXECUTE') then
    raise exception 'WhatsApp webhook event RPC must remain service-role-only';
  end if;
end $$;
select 'EC-08 RLS, grants, indexes and guarded functions verified' as result;

-- Transactional EC-08 behavior checks use only the disposable CI database.
do $ec08$
declare
  v_admin uuid := '00000000-0000-0000-0000-000000000801';
  v_customer uuid := '00000000-0000-0000-0000-000000000802';
  v_order uuid := '00000000-0000-0000-0000-000000000803';
  v_first jsonb; v_replay jsonb; v_claim jsonb; v_result jsonb; v_pref jsonb;
  v_id uuid; v_lock uuid;
begin
  insert into auth.users(id,email) values(v_admin,'ec08-admin-fixture@example.invalid'),(v_customer,'ec08-customer-fixture@example.invalid')
  on conflict(id) do nothing;
  insert into public.user_profiles(id,role,is_active) values(v_admin,'admin',true),(v_customer,'customer',true)
  on conflict(id) do update set role=excluded.role,is_active=excluded.is_active;

  perform set_config('request.jwt.claims','{"role":"service_role"}',true);
  v_first := public.oto_integration_outbox_enqueue(
    'ec08-test-order-status-001','whatsapp_cloud','whatsapp_template','ec08-correlation-001','order',v_order,
    '{"to":"6281234567890","template_name":"order_status","language_code":"id","parameters":["00000803","dikirim"]}'::jsonb,
    repeat('a',64)
  );
  v_replay := public.oto_integration_outbox_enqueue(
    'ec08-test-order-status-001','whatsapp_cloud','whatsapp_template','ec08-correlation-002','order',v_order,
    '{"to":"6281234567890","template_name":"order_status","language_code":"id","parameters":["00000803","dikirim"]}'::jsonb,
    repeat('a',64)
  );
  if coalesce((v_first->>'replayed')::boolean,true) or coalesce((v_replay->>'replayed')::boolean,false) is not true then
    raise exception 'outbox enqueue replay contract failed';
  end if;
  begin
    perform public.oto_integration_outbox_enqueue(
      'ec08-test-order-status-001','whatsapp_cloud','whatsapp_template','ec08-correlation-003','order',v_order,
      '{"to":"6281234567890","template_name":"order_status","language_code":"id","parameters":["changed","dikirim"]}'::jsonb,
      repeat('b',64)
    );
    raise exception 'outbox conflicting replay was accepted';
  exception when unique_violation then null;
  end;

  v_claim := public.oto_integration_outbox_claim(10,90);
  if jsonb_array_length(v_claim) <> 1 then raise exception 'outbox claim did not return exactly one row'; end if;
  v_id := (v_claim->0->>'id')::uuid;
  v_lock := (v_claim->0->>'lock_token')::uuid;
  v_result := public.oto_integration_outbox_fail(v_id,v_lock,'provider_transient',true);
  if v_result->>'status' <> 'retry' then raise exception 'transient outbox failure did not schedule retry'; end if;
  if (v_result->>'next_attempt_at')::timestamptz <= now() then raise exception 'outbox retry backoff was not scheduled in the future'; end if;
  v_result := public.oto_integration_outbox_requeue(v_id,v_admin,'ec08-requeue-request-001');
  if v_result->>'status' <> 'pending' then raise exception 'admin requeue did not return outbox to pending'; end if;
  v_claim := public.oto_integration_outbox_claim(10,90);
  if jsonb_array_length(v_claim) <> 1 then raise exception 'requeued outbox item was not claimable'; end if;
  v_id := (v_claim->0->>'id')::uuid;
  v_lock := (v_claim->0->>'lock_token')::uuid;
  v_result := public.oto_integration_outbox_fail(v_id,v_lock,'provider_permanent',false);
  if v_result->>'status' <> 'dead_letter' then raise exception 'permanent outbox failure did not dead-letter'; end if;

  v_first := public.oto_integration_outbox_enqueue(
    'ec08-test-order-status-002','whatsapp_cloud','whatsapp_template','ec08-correlation-002','order',v_order,
    '{"to":"6281234567890","template_name":"order_status","language_code":"id","parameters":["00000803","dikirim"]}'::jsonb,
    repeat('c',64)
  );
  v_claim := public.oto_integration_outbox_claim(10,90);
  if jsonb_array_length(v_claim) <> 1 then raise exception 'delivery webhook test item was not claimable'; end if;
  v_id := (v_claim->0->>'id')::uuid;
  v_lock := (v_claim->0->>'lock_token')::uuid;
  v_result := public.oto_integration_outbox_complete(v_id,v_lock,'wamid.ec08-test-001',repeat('f',64));
  if v_result->>'status' <> 'provider_accepted' then raise exception 'outbox provider-acceptance state was not recorded'; end if;
  v_result := public.oto_whatsapp_webhook_event_record(
    'wamid.ec08-test-001:delivered:2026-10-21T00:00:00+00:00','wamid.ec08-test-001','delivered','6281234567890',
    '2026-10-21T00:00:00+00:00','ec08-correlation-002',repeat('d',64),null
  );
  if coalesce((v_result->>'replayed')::boolean,true) then raise exception 'first WhatsApp status event was marked as replay'; end if;
  v_replay := public.oto_whatsapp_webhook_event_record(
    'wamid.ec08-test-001:delivered:2026-10-21T00:00:00+00:00','wamid.ec08-test-001','delivered','6281234567890',
    '2026-10-21T00:00:00+00:00','ec08-correlation-002',repeat('d',64),null
  );
  if coalesce((v_replay->>'replayed')::boolean,false) is not true then raise exception 'duplicate WhatsApp status event was not idempotent'; end if;
  if (select provider_delivery_status from public.oto_integration_outbox where id=v_id) <> 'delivered'
     or (select delivered_at from public.oto_integration_outbox where id=v_id) is null then
    raise exception 'WhatsApp delivery webhook did not update outbox delivery state';
  end if;

  perform set_config('request.jwt.claim.sub',v_customer::text,true);
  perform set_config('request.jwt.claims','{"role":"authenticated","sub":"00000000-0000-0000-0000-000000000802"}',true);
  v_pref := public.oto_whatsapp_consent_set(true,'whatsapp-order-status-v1','ec08-consent-request-001');
  if v_pref->>'whatsapp_opt_in' <> 'true' or v_pref->>'replayed' <> 'false' then raise exception 'customer consent write failed'; end if;
  v_pref := public.oto_whatsapp_consent_set(true,'whatsapp-order-status-v1','ec08-consent-request-001');
  if v_pref->>'replayed' <> 'true' then raise exception 'customer consent replay was not idempotent'; end if;
  begin
    perform public.oto_whatsapp_consent_set(false,'whatsapp-order-status-v1','ec08-consent-request-001');
    raise exception 'consent request ID accepted a conflicting payload';
  exception when unique_violation then null;
  end;
  if (select count(*) from public.audit_logs where actor_user_id=v_customer and request_id='ec08-consent-request-001') <> 1 then
    raise exception 'consent replay wrote duplicate audit rows';
  end if;
end;
$ec08$;
select 'EC-08 outbox retry, dead-letter, replay, consent and audit verified' as result;
