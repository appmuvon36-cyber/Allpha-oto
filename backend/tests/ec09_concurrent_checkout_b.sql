begin;
select set_config('request.jwt.claim.sub','09000000-0000-4000-8000-000000000001',false);
select public.oto_order_mutate('checkout',null,
 '{"items":[{"product_id":"09000000-0000-4000-8000-000000000003","quantity":4}],"shipping_address":{"recipient_name":"EC09 Fixture","phone":"081234567890","address":"CI-only fixture","city":"Bogor","province":"Jawa Barat","postal_code":"16120"},"shipping_fee":0}'::jsonb,
 'ec09-concurrent-checkout-b');
commit;
