\set ON_ERROR_STOP on
select set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',false);
insert into public.user_profiles(id,role,is_active)
values ('10000000-0000-4000-8000-000000000001','catalog_editor',true);

do $$
declare
  v jsonb;
  v_count integer;
begin
  v := public.oto_catalog_mutate(
    'create_product', null,
    '{"sku":"PHASE05-BASE-1","slug":"phase05-base-1","name":"Phase 05 fixture","category":"fixture","condition":"new_aftermarket","retail_price":"125000","source_rights_evidence":"test-fixture-only"}'::jsonb,
    'phase05-identical-replay-01'
  );
  if v->>'replayed' <> 'false' then raise exception 'first call should not be replayed'; end if;
  select count(*) into v_count from public.products where sku='PHASE05-BASE-1';
  if v_count <> 1 then raise exception 'expected one product after first call, got %',v_count; end if;
  select count(*) into v_count from public.audit_logs where request_id='phase05-identical-replay-01';
  if v_count <> 1 then raise exception 'expected one audit row after first call, got %',v_count; end if;

  v := public.oto_catalog_mutate(
    'create_product', null,
    '{"sku":"PHASE05-BASE-1","slug":"phase05-base-1","name":"Phase 05 fixture","category":"fixture","condition":"new_aftermarket","retail_price":"125000","source_rights_evidence":"test-fixture-only"}'::jsonb,
    'phase05-identical-replay-01'
  );
  if v->>'replayed' <> 'true' then raise exception 'identical retry must report replayed=true'; end if;
  select count(*) into v_count from public.products where sku='PHASE05-BASE-1';
  if v_count <> 1 then raise exception 'identical replay duplicated product'; end if;
  select count(*) into v_count from public.audit_logs where request_id='phase05-identical-replay-01';
  if v_count <> 1 then raise exception 'identical replay duplicated audit row'; end if;

  begin
    perform public.oto_catalog_mutate(
      'create_product', null,
      '{"sku":"PHASE05-CONFLICT-1","slug":"phase05-conflict-1","name":"Changed payload","category":"fixture","condition":"new_aftermarket","source_rights_evidence":"test-fixture-only"}'::jsonb,
      'phase05-identical-replay-01'
    );
    raise exception 'expected conflicting idempotency key to fail';
  exception when sqlstate '22023' then
    if sqlerrm not like '%request_id_reused_for_different_operation%' then raise; end if;
  end;
  select count(*) into v_count from public.products where sku='PHASE05-CONFLICT-1';
  if v_count <> 0 then raise exception 'conflicting replay unexpectedly created a product'; end if;

  begin
    perform public.oto_catalog_mutate(
      'create_product', null,
      '{"sku":"PHASE05-MISSING-KEY","slug":"phase05-missing-key","name":"Missing key","category":"fixture","condition":"new_aftermarket"}'::jsonb,
      null
    );
    raise exception 'expected missing idempotency key to fail';
  exception when sqlstate '22023' then
    if sqlerrm not like '%request_id_required_or_length_invalid%' then raise; end if;
  end;

  begin
    perform public.oto_catalog_mutate(
      'create_product', null,
      '{"sku":"PHASE05-AUDIT-FAIL","slug":"phase05-audit-fail","name":"Audit failure","category":"fixture","condition":"new_aftermarket","source_rights_evidence":"test-fixture-only"}'::jsonb,
      'phase05-force-audit-failure'
    );
    raise exception 'expected forced audit failure';
  exception when others then
    if sqlerrm = 'expected forced audit failure' then raise; end if;
    if sqlerrm <> 'fixture_forced_audit_failure' then raise; end if;
  end;
  select count(*) into v_count from public.products where sku='PHASE05-AUDIT-FAIL';
  if v_count <> 0 then raise exception 'product mutation was not rolled back after audit failure'; end if;
  select count(*) into v_count from public.audit_logs where request_id='phase05-force-audit-failure';
  if v_count <> 0 then raise exception 'failed audit unexpectedly persisted'; end if;
end $$;

-- The null request key and mismatched replay cases must fail without creating rows.
select 'phase05_transaction_assertions_passed' as result;
