-- Phase 07 end-to-end transactional assertions. Runs only on disposable CI PostgreSQL.
do $$
declare
  customer_id uuid := '07000000-0000-4000-8000-000000000001';
  manager_id uuid := '07000000-0000-4000-8000-000000000002';
  product_id uuid := '07000000-0000-4000-8000-000000000003';
  checkout_payload jsonb := '{"items":[{"product_id":"07000000-0000-4000-8000-000000000003","quantity":4}],"shipping_address":{"recipient_name":"CI Customer","phone":"081234567890","address":"Jalan Fixture 1","city":"Bogor","province":"Jawa Barat"},"shipping_fee":0}'::jsonb;
  result jsonb; order_id uuid; payment_id uuid; return_id uuid; order_item_id uuid;
  available integer; orders_before integer;
begin
  insert into auth.users(id,email) values(customer_id,'phase07-customer@example.invalid'),(manager_id,'phase07-manager@example.invalid') on conflict(id) do nothing;
  insert into public.user_profiles(id,role,is_active) values(customer_id,'customer',true),(manager_id,'admin',true) on conflict(id) do update set role=excluded.role,is_active=true;
  insert into public.products(id,sku,slug,name,category,condition,package_quantity,warranty_days,status,currency,retail_price,source_rights_evidence)
  values(product_id,'PHASE07-CI-001','phase07-ci-001','Phase 07 CI Fixture','CI', 'new_aftermarket',1,0,'published','IDR',1000,'CI-only synthetic fixture')
  on conflict(id) do update set status='published',retail_price=1000;
  perform set_config('request.jwt.claim.sub',manager_id::text,true);
  result:=public.oto_inventory_mutate('receipt',product_id,'{"quantity":10,"reason":"CI fixture opening balance"}'::jsonb,'phase07-stock-receipt-001');
  if (result#>>'{balance,on_hand}')::integer<>10 then raise exception 'phase07 receipt balance mismatch'; end if;
  -- Forced audit failure must roll back balance, ledger and idempotency writes together.
  begin
    perform public.oto_inventory_mutate('receipt',product_id,'{"quantity":3,"reason":"forced audit rollback"}'::jsonb,'phase05-force-audit-failure');
  exception when others then
    if position('fixture_forced_audit_failure' in sqlerrm)=0 then raise; end if;
  end;
  if (select b.on_hand from public.inventory_balances b where b.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>10
     or exists(select 1 from public.oto_idempotency_records where actor_user_id=manager_id and request_id='phase05-force-audit-failure')
     or exists(select 1 from public.inventory_ledger il where il.product_id='07000000-0000-4000-8000-000000000003'::uuid and il.reason='forced audit rollback') then
    raise exception 'phase07 failed to roll back mutation after audit failure';
  end if;
  select count(*) into orders_before from public.oto_orders;
  perform set_config('request.jwt.claim.sub',customer_id::text,true);
  result:=public.oto_order_mutate('checkout',null,checkout_payload,'phase07-checkout-0001');
  order_id:=(result#>>'{order,id}')::uuid;
  if order_id is null or result#>>'{order,status}'<>'pending_payment' then raise exception 'phase07 checkout did not create pending order'; end if;
  result:=public.oto_order_mutate('checkout',null,checkout_payload,'phase07-checkout-0001');
  if result->>'replayed'<>'true' then raise exception 'phase07 checkout retry was not idempotent'; end if;
  if (select count(*) from public.oto_orders)-orders_before<>1 then raise exception 'phase07 checkout replay duplicated order'; end if;
  if (select b.reserved from public.inventory_balances b where b.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>4 then raise exception 'phase07 stock reservation mismatch'; end if;
  begin
    perform public.oto_order_mutate('checkout',null,jsonb_set(checkout_payload,'{items,0,quantity}','7'::jsonb),'phase07-checkout-oversell-01');
    raise exception 'phase07 oversell unexpectedly succeeded';
  exception when sqlstate '22023' then null;
  end;
  if (select count(*) from public.oto_orders)-orders_before<>1 then raise exception 'phase07 oversell created an order'; end if;
  result:=public.oto_order_mutate('submit_payment_evidence',order_id,'{"amount":"4000","method":"manual_transfer","evidence_reference":"ci-fixture-proof"}'::jsonb,'phase07-payment-submit-001');
  payment_id:=(result#>>'{payment,id}')::uuid;
  if result#>>'{order,status}'<>'payment_review' then raise exception 'phase07 payment evidence incorrectly skipped review'; end if;
  perform set_config('request.jwt.claim.sub',manager_id::text,true);
  result:=public.oto_order_mutate('verify_payment',order_id,jsonb_build_object('payment_event_id',payment_id,'provider_reference','CI-VERIFIED-TRANSFER'),'phase07-payment-verify-001');
  if result#>>'{order,status}'<>'paid' then raise exception 'phase07 verified payment did not mark paid'; end if;
  perform public.oto_order_mutate('start_fulfillment',order_id,'{}'::jsonb,'phase07-fulfill-start-001');
  result:=public.oto_order_mutate('mark_shipped',order_id,'{"tracking_code":"CI-TRACK-001"}'::jsonb,'phase07-ship-001');
  if result#>>'{order,status}'<>'shipped' then raise exception 'phase07 shipment transition failed'; end if;
  if (select b.on_hand from public.inventory_balances b where b.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>6 or (select b2.reserved from public.inventory_balances b2 where b2.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>0 then raise exception 'phase07 ship did not consume reservation atomically'; end if;
  perform public.oto_order_mutate('mark_delivered',order_id,'{}'::jsonb,'phase07-deliver-001');
  select x.id into order_item_id from public.oto_order_items x where x.order_id=(select o2.id from public.oto_orders o2 where o2.customer_user_id=customer_id order by o2.created_at desc limit 1) limit 1;
  perform set_config('request.jwt.claim.sub',customer_id::text,true);
  result:=public.oto_order_mutate('request_return',order_id,jsonb_build_object('reason','CI return inspection','items',jsonb_build_array(jsonb_build_object('order_item_id',order_item_id,'quantity',1))),'phase07-return-request-001');
  return_id:=(result#>>'{return,id}')::uuid;
  perform set_config('request.jwt.claim.sub',manager_id::text,true);
  perform public.oto_order_mutate('approve_return',order_id,jsonb_build_object('return_id',return_id),'phase07-return-approve-001');
  perform public.oto_order_mutate('receive_return',order_id,jsonb_build_object('return_id',return_id,'restock_items',jsonb_build_array(order_item_id)),'phase07-return-receive-001');
  result:=public.oto_order_mutate('record_refund',order_id,jsonb_build_object('return_id',return_id,'provider_reference','CI-REFUND-001'),'phase07-refund-record-001');
  if result#>>'{order,status}'<>'partially_returned' then raise exception 'phase07 partial refund order status mismatch'; end if;
  if (select b.on_hand from public.inventory_balances b where b.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>7 then raise exception 'phase07 inspected return did not restock selected item'; end if;
  if not exists(select 1 from public.audit_logs where request_id='phase07-stock-receipt-001')
     or not exists(select 1 from public.audit_logs where request_id='phase07-checkout-0001')
     or not exists(select 1 from public.audit_logs where request_id='phase07-refund-record-001') then
    raise exception 'phase07 audit trail missing critical transaction';
  end if;
  if (select count(*) from public.inventory_ledger where reference_type='order' and reference_id=order_id)<2 then
    raise exception 'phase07 inventory ledger did not record reservation and consumption events';
  end if;
  if not exists(select 1 from public.inventory_ledger where reference_type='return' and reference_id=return_id and movement='return') then raise exception 'phase07 return restock ledger event missing'; end if;

  -- Cancelling an order in payment review must clear the pending payment queue in the same transaction.
  perform set_config('request.jwt.claim.sub',customer_id::text,true);
  result:=public.oto_order_mutate('checkout',null,jsonb_set(checkout_payload,'{items,0,quantity}','1'::jsonb),'phase07-checkout-cancel-01');
  order_id:=(result#>>'{order,id}')::uuid;
  result:=public.oto_order_mutate('submit_payment_evidence',order_id,'{"amount":"1000","method":"manual_transfer","evidence_reference":"ci-cancel-proof"}'::jsonb,'phase07-payment-cancel-submit');
  payment_id:=(result#>>'{payment,id}')::uuid;
  result:=public.oto_order_mutate('cancel_order',order_id,'{}'::jsonb,'phase07-payment-cancel-order');
  if result#>>'{order,status}'<>'cancelled' or (select pe.status from public.oto_payment_events pe where pe.id=payment_id)<>'rejected' then
    raise exception 'phase07 cancellation did not close pending payment review';
  end if;

  -- Reservation expiry must cancel unpaid orders and release reserved stock atomically.
  perform set_config('request.jwt.claim.sub',customer_id::text,true);
  result:=public.oto_order_mutate('checkout',null,jsonb_set(checkout_payload,'{items,0,quantity}','2'::jsonb),'phase07-checkout-expiry-01');
  order_id:=(result#>>'{order,id}')::uuid;
  update public.inventory_reservations ir set expires_at=now()-interval '1 minute' where ir.order_id=(result#>>'{order,id}')::uuid and ir.status='reserved';
  perform set_config('request.jwt.claim.sub',manager_id::text,true);
  result:=public.oto_expire_reservations('phase07-expire-reservations-01');
  if (result->>'cancelled_orders')::integer<>1 or (result->>'released_reservations')::integer<>1 then raise exception 'phase07 reservation expiry counts mismatch'; end if;
  if (select o.status from public.oto_orders o where o.id=order_id)<>'cancelled' then raise exception 'phase07 expired checkout was not cancelled'; end if;
  if (select b.reserved from public.inventory_balances b where b.product_id='07000000-0000-4000-8000-000000000003'::uuid)<>0 then raise exception 'phase07 expired reservation remained reserved'; end if;
  result:=public.oto_expire_reservations('phase07-expire-reservations-01');
  if result->>'replayed'<>'true' then raise exception 'phase07 reservation expiry retry was not idempotent'; end if;
end $$;

do $$
begin
  if not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname='oto_order_mutate' and has_function_privilege('authenticated',p.oid,'EXECUTE')) then raise exception 'phase07 authenticated order RPC grant missing'; end if;
  if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname in ('oto_order_mutate','oto_inventory_mutate') and has_function_privilege('anon',p.oid,'EXECUTE')) then raise exception 'phase07 RPC is executable by anon'; end if;
  if not (select relrowsecurity from pg_class where oid='public.oto_orders'::regclass) then raise exception 'phase07 orders RLS disabled'; end if;
  if not (select relrowsecurity from pg_class where oid='public.oto_payment_events'::regclass) then raise exception 'phase07 payment RLS disabled'; end if;
end $$;
