\set ON_ERROR_STOP on
-- Disposable database only. No production users or supplier data are touched.
insert into auth.users(id,email) values
 ('20000000-0000-4000-8000-000000000001','supplier-fixture@example.invalid'),
 ('20000000-0000-4000-8000-000000000002','moderator-fixture@example.invalid'),
 ('20000000-0000-4000-8000-000000000003','audit-failure-fixture@example.invalid')
on conflict(id) do nothing;
insert into public.user_profiles(id,role,is_active) values
 ('20000000-0000-4000-8000-000000000001','customer',true),
 ('20000000-0000-4000-8000-000000000002','moderator',true),
 ('20000000-0000-4000-8000-000000000003','customer',true)
on conflict(id) do nothing;

select set_config('request.jwt.claim.sub','20000000-0000-4000-8000-000000000001',false);
do $$
declare
  v_result jsonb;
  v_supplier_id uuid;
  v_document_id uuid;
  v_offer_id uuid;
  v_count integer;
  v_payload jsonb;
begin
  v_payload:=jsonb_build_object(
    'legal_name','Fixture Supplier PT','display_name','Fixture Parts',
    'supplier_type','supplier','contact_email','ops@example.invalid',
    'address',jsonb_build_object('city','Jakarta','province','DKI Jakarta')
  );
  v_result:=public.oto_supplier_onboard(v_payload,'phase06-onboard-0001');
  if v_result#>>'{supplier,status}'<>'pending_review' then raise exception 'supplier must begin in pending_review'; end if;
  v_supplier_id:=(v_result#>>'{supplier,id}')::uuid;
  select count(*) into v_count from public.suppliers where owner_user_id=auth.uid();
  if v_count<>1 then raise exception 'onboarding should create exactly one supplier'; end if;
  select count(*) into v_count from public.audit_logs where actor_user_id=auth.uid() and request_id='phase06-onboard-0001';
  if v_count<>1 then raise exception 'supplier onboarding must have one audit row'; end if;

  v_result:=public.oto_supplier_onboard(v_payload,'phase06-onboard-0001');
  if v_result->>'replayed'<>'true' then raise exception 'supplier onboarding retry must replay'; end if;
  begin
    perform public.oto_supplier_onboard(v_payload||jsonb_build_object('display_name','Different supplier'),'phase06-onboard-0001');
    raise exception 'expected idempotency payload mismatch to fail';
  exception when sqlstate '22023' then
    if sqlerrm not like '%request_id_reused_for_different_operation%' then raise; end if;
  end;
  begin
    perform public.oto_supplier_onboard(v_payload,'phase06-onboard-duplicate-01');
    raise exception 'expected duplicate owner onboarding to fail';
  exception when sqlstate '23505' then
    if sqlerrm not like '%supplier_profile_already_exists%' then raise; end if;
  end;

  insert into storage.objects(bucket_id,name) values(
    'supplier-verification-documents',
    auth.uid()::text||'/'||v_supplier_id::text||'/registration.pdf'
  );
  v_result:=public.oto_supplier_document_register(v_supplier_id,jsonb_build_object(
    'document_type','business_registration',
    'storage_path',auth.uid()::text||'/'||v_supplier_id::text||'/registration.pdf',
    'original_filename','registration.pdf','content_type','application/pdf',
    'file_size_bytes',1024,'sha256',repeat('a',64)
  ),'phase06-document-register-01');
  v_document_id:=(v_result#>>'{document,id}')::uuid;
  if v_result#>>'{document,status}'<>'pending_review' then raise exception 'new supplier document must be pending review'; end if;
  select count(*) into v_count from public.audit_logs where request_id='phase06-document-register-01';
  if v_count<>1 then raise exception 'document registration must be audited'; end if;

  begin
    perform public.oto_supplier_onboard(v_payload,'phase05-force-audit-failure');
    raise exception 'expected forced supplier audit failure';
  exception when others then
    if sqlerrm='expected forced supplier audit failure' then raise; end if;
    if sqlerrm<>'fixture_forced_audit_failure' then raise; end if;
  end;
  select count(*) into v_count from public.suppliers where owner_user_id='20000000-0000-4000-8000-000000000003';
  if v_count<>0 then raise exception 'supplier insert must roll back when audit insert fails'; end if;

  -- Staff role cannot self-onboard through the SECURITY DEFINER RPC.
  perform set_config('request.jwt.claim.sub','20000000-0000-4000-8000-000000000002',false);
  begin
    perform public.oto_supplier_onboard(v_payload,'phase06-staff-onboard-01');
    raise exception 'expected staff self-onboarding to be rejected';
  exception when sqlstate '42501' then
    if sqlerrm not like '%supplier_onboarding_role_required%' then raise; end if;
  end;
  v_result:=public.oto_supplier_admin_mutate(
    'review_supplier_document',null,null,v_document_id,
    jsonb_build_object('status','verified'),
    'phase06-document-review-01'
  );
  if v_result#>>'{document,status}'<>'verified' then raise exception 'document review did not verify document'; end if;
  v_result:=public.oto_supplier_admin_mutate(
    'approve_supplier',v_supplier_id,null,null,'{}'::jsonb,'phase06-supplier-approve-01'
  );
  if v_result#>>'{supplier,status}'<>'active' then raise exception 'supplier should activate only after verified document'; end if;

  perform set_config('request.jwt.claim.sub','20000000-0000-4000-8000-000000000001',false);
  v_payload:=jsonb_build_object(
    'supplier_sku','PHASE06-SP-100',
    'source_url','https://supplier.example.invalid/parts/SP-100',
    'source_evidence',jsonb_build_object('type','supplier_quote','reference','Q-100'),
    'condition','new_aftermarket','unit_cost',125000,'asking_price',149000,
    'stock_quantity',5,'quote_expires_at',(now()+interval '7 days')::text,
    'lead_time_days',3,'minimum_order_quantity',2,'warranty_days',30
  );
  v_result:=public.oto_supplier_offer_submit(v_supplier_id,v_payload,'phase06-offer-submit-01');
  v_offer_id:=(v_result#>>'{offer,id}')::uuid;
  if v_result#>>'{offer,status}'<>'pending_review' then raise exception 'supplier offer must begin pending review'; end if;
  if v_result#>>'{offer,stock_checked_at}' is null then raise exception 'supplier stock report needs a timestamp'; end if;
  if v_result#>>'{offer,source_verified_at}' is not null then raise exception 'supplier report cannot mark itself verified'; end if;

  v_result:=public.oto_supplier_offer_submit(v_supplier_id,v_payload||jsonb_build_object(
    'stock_quantity',9,'quote_expires_at',(now()+interval '10 days')::text
  ),'phase06-offer-refresh-01');
  if (v_result#>>'{offer,id}')::uuid<>v_offer_id then raise exception 'same supplier SKU must update rather than duplicate an active/pending offer'; end if;
  select count(*) into v_count from public.supplier_offers where supplier_id=v_supplier_id and supplier_sku='PHASE06-SP-100';
  if v_count<>1 then raise exception 'supplier offer deduplication failed'; end if;

  begin
    perform public.oto_supplier_offer_submit(v_supplier_id,v_payload||jsonb_build_object(
      'supplier_sku','PHASE06-EXPIRED','quote_expires_at',(now()-interval '1 day')::text
    ),'phase06-offer-expired-01');
    raise exception 'expected expired quote to be rejected';
  exception when sqlstate '22023' then
    if sqlerrm not like '%supplier_quote_expiry_must_be_future%' then raise; end if;
  end;

  perform set_config('request.jwt.claim.sub','20000000-0000-4000-8000-000000000002',false);
  v_result:=public.oto_supplier_admin_mutate('approve_offer',null,v_offer_id,null,'{}'::jsonb,'phase06-offer-approve-01');
  if v_result#>>'{offer,status}'<>'active' then raise exception 'valid offer review did not activate offer'; end if;
  if v_result#>>'{offer,source_verified_at}' is null then raise exception 'approved offer needs source verification timestamp'; end if;
  select count(*) into v_count from public.audit_logs where entity_type in ('supplier','supplier_document','supplier_offer');
  if v_count<7 then raise exception 'expected supplier, document and offer audit events'; end if;
end $$;

select 'phase06_supplier_sourcing_assertions_passed' as result;
