-- EC-09 isolated concurrency fixture. Run only in the disposable CI PostgreSQL database.
do $$
declare
 v_customer uuid := '09000000-0000-4000-8000-000000000001';
 v_admin uuid := '09000000-0000-4000-8000-000000000002';
 v_product uuid := '09000000-0000-4000-8000-000000000003';
 v_result jsonb;
begin
 insert into auth.users(id,email) values(v_customer,'ec09-concurrency-customer@example.invalid'),(v_admin,'ec09-concurrency-admin@example.invalid')
 on conflict(id) do nothing;
 insert into public.user_profiles(id,role,is_active) values(v_customer,'customer',true),(v_admin,'admin',true)
 on conflict(id) do update set role=excluded.role,is_active=true;
 insert into public.products(id,sku,slug,name,category,condition,package_quantity,warranty_days,status,currency,retail_price,weight_grams,source_rights_evidence)
 values(v_product,'EC09-CONCURRENT-001','ec09-concurrent-001','EC09 Concurrent Checkout Fixture','CI','new_aftermarket',1,0,'published','IDR',1000,250,'CI-only synthetic fixture')
 on conflict(id) do update set status='published',retail_price=1000,weight_grams=250;
 perform set_config('request.jwt.claim.sub',v_admin::text,true);
 v_result:=public.oto_inventory_mutate('receipt',v_product,'{"quantity":5,"reason":"EC-09 disposable concurrency fixture"}'::jsonb,'ec09-stock-receipt-001');
 if (v_result#>>'{balance,on_hand}')::integer<>5 then raise exception 'EC-09 fixture stock did not initialize to five'; end if;
end $$;
