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
end $$;
select 'EC-08 RLS, grants, indexes and guarded functions verified' as result;
