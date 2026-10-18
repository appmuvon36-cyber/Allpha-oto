\set ON_ERROR_STOP on
select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',false);
select public.oto_catalog_mutate(
  'create_product', null,
  '{"sku":"PHASE05-CONCURRENT-1","slug":"phase05-concurrent-1","name":"Concurrent fixture","category":"fixture","condition":"new_aftermarket","retail_price":"50000","source_rights_evidence":"test-fixture-only"}'::jsonb,
  'phase05-concurrent-retry-01'
);
