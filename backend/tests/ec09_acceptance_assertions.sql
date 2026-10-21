-- EC-09 acceptance assertions. This file runs only in the disposable CI database.
do $ec09$
declare
 v_customer uuid := '09000000-0000-4000-8000-000000000011';
 v_admin uuid := '09000000-0000-4000-8000-000000000012';
 v_order uuid;
 v_intent uuid;
 v_result jsonb;
 v_replay jsonb;
 v_caught boolean := false;
begin
 insert into auth.users(id,email) values(v_customer,'ec09-payment-customer@example.invalid'),(v_admin,'ec09-payment-admin@example.invalid')
 on conflict(id) do nothing;
 insert into public.user_profiles(id,role,is_active) values(v_customer,'customer',true),(v_admin,'admin',true)
 on conflict(id) do update set role=excluded.role,is_active=true;
 insert into public.oto_orders(customer_user_id,status,subtotal,shipping_fee,total_amount,shipping_address)
 values(v_customer,'pending_payment',1000,0,1000,'{"recipient_name":"EC09 Fixture","phone":"081234567890","address":"CI-only fixture","city":"Bogor","province":"Jawa Barat","postal_code":"16120"}'::jsonb)
 returning id into v_order;
 insert into public.oto_payment_intents(order_id,customer_user_id,provider,provider_order_id,amount,status,payment_details)
 values(v_order,v_customer,'rajaongkir','ec09-provider-order-001',1000,'pending','{}'::jsonb)
 returning id into v_intent;

 perform set_config('request.jwt.claim.role','service_role',true);
 perform set_config('request.jwt.claim.sub','',true);
 v_result:=public.oto_payment_webhook_apply('ec09-event-settlement-001','rajaongkir','ec09-provider-order-001',
  'ec09-transaction-001','settlement',1000,repeat('a',64));
 if coalesce((v_result->>'replayed')::boolean,true) then raise exception 'first payment webhook was treated as replay'; end if;
 if (select status from public.oto_payment_intents where id=v_intent)<>'settlement'
  or (select status from public.oto_orders where id=v_order)<>'paid' then
  raise exception 'valid payment webhook did not settle the matching order and intent';
 end if;

 v_replay:=public.oto_payment_webhook_apply('ec09-event-settlement-001','rajaongkir','ec09-provider-order-001',
  'ec09-transaction-001','settlement',1000,repeat('a',64));
 if coalesce((v_replay->>'replayed')::boolean,false) is not true then
  raise exception 'same payment webhook payload was not idempotently replayed';
 end if;

 begin
  perform public.oto_payment_webhook_apply('ec09-event-settlement-001','rajaongkir','ec09-provider-order-001',
   'ec09-transaction-001','settlement',1000,repeat('b',64));
  raise exception 'conflicting payload reused an existing payment event key';
 exception when unique_violation then
  if position('payment_webhook_event_payload_conflict' in sqlerrm)=0 then raise; end if;
  v_caught:=true;
 end;
 if not v_caught then raise exception 'conflicting payment event payload was not rejected'; end if;

 v_caught:=false;
 begin
  perform public.oto_payment_webhook_apply('ec09-event-amount-mismatch','rajaongkir','ec09-provider-order-001',
   'ec09-transaction-001','paid',999,repeat('c',64));
  raise exception 'mismatched payment amount unexpectedly succeeded';
 exception when check_violation then
  if position('payment_amount_mismatch' in sqlerrm)=0 then raise; end if;
  v_caught:=true;
 end;
 if not v_caught then raise exception 'mismatched payment amount was not rejected'; end if;

 v_result:=public.oto_payment_webhook_apply('ec09-event-stale-pending','rajaongkir','ec09-provider-order-001',
  'ec09-transaction-001','pending',1000,repeat('d',64));
 if (select status from public.oto_payment_intents where id=v_intent)<>'settlement'
  or (select status from public.oto_orders where id=v_order)<>'paid' then
  raise exception 'stale pending callback regressed a terminal payment state';
 end if;
end
$ec09$;

do $$
begin
 if not (select relrowsecurity from pg_class where oid='public.oto_payment_intents'::regclass) then
  raise exception 'payment intents RLS must remain enabled';
 end if;
 if not (select relrowsecurity from pg_class where oid='public.oto_payment_webhook_events'::regclass) then
  raise exception 'payment webhook events RLS must remain enabled';
 end if;
 if not has_function_privilege('service_role','public.oto_payment_webhook_apply(text,text,text,text,text,numeric,text)','EXECUTE') then
  raise exception 'service role must execute the payment webhook RPC';
 end if;
 if has_function_privilege('anon','public.oto_payment_webhook_apply(text,text,text,text,text,numeric,text)','EXECUTE')
  or has_function_privilege('authenticated','public.oto_payment_webhook_apply(text,text,text,text,text,numeric,text)','EXECUTE') then
  raise exception 'payment webhook RPC must remain service-role-only';
 end if;
 if has_function_privilege('anon','public.oto_integration_outbox_claim(integer,integer)','EXECUTE')
  or has_function_privilege('authenticated','public.oto_integration_outbox_claim(integer,integer)','EXECUTE') then
  raise exception 'outbox worker RPC must remain service-role-only';
 end if;
 if not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname='oto_order_mutate'
  and has_function_privilege('authenticated',p.oid,'EXECUTE')) then
  raise exception 'authenticated order mutation RPC grant is missing';
 end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname in ('oto_order_mutate','oto_inventory_mutate')
  and has_function_privilege('anon',p.oid,'EXECUTE')) then
  raise exception 'anon must not execute order or inventory mutation RPCs';
 end if;
end $$;
select 'EC-09 payment replay, payload conflict, amount, monotonic state, RLS and grants verified' as result;
