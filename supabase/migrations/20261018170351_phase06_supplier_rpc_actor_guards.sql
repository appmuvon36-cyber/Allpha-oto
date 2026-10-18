-- Phase 06 hardening: enforce active profiles and restrict self-onboarding roles in definer RPCs.
create or replace function public.oto_supplier_onboard(p_payload jsonb,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog','public','storage'
as $function$
declare
  v_actor uuid := auth.uid();
  v_role public.oto_user_role;
  v_active boolean;
  v_existing public.audit_logs%rowtype;
  v_supplier public.suppliers%rowtype;
  v_result jsonb;
  v_type text := coalesce(nullif(btrim(p_payload->>'supplier_type'),''),'supplier');
  v_legal_name text := nullif(btrim(p_payload->>'legal_name'),'');
  v_display_name text := nullif(btrim(p_payload->>'display_name'),'');
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
  select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
  if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
  if v_role not in ('customer'::public.oto_user_role,'supplier'::public.oto_user_role) then raise exception using errcode='42501',message='supplier_onboarding_role_required'; end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then
    raise exception using errcode='22023',message='request_id_required_or_length_invalid';
  end if;
  if v_legal_name is null or length(v_legal_name)>200 or v_display_name is null or length(v_display_name)>160 then
    raise exception using errcode='22023',message='supplier_name_required_or_invalid';
  end if;
  if v_type not in ('oem_distributor','aftermarket_distributor','supplier','workshop','reconditioner','dismantler','individual') then
    raise exception using errcode='22023',message='supplier_type_invalid';
  end if;
  if p_payload?'website_url' and nullif(btrim(p_payload->>'website_url'),'') is not null and (p_payload->>'website_url') !~* '^https?://' then
    raise exception using errcode='22023',message='supplier_website_url_invalid';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(v_actor::text || ':supplier-onboard:' || p_request_id,0));
  select * into v_existing from public.audit_logs where actor_user_id=v_actor and request_id=p_request_id limit 1;
  if found then
    if v_existing.details->>'action' is distinct from 'supplier_onboard'
      or v_existing.details->'payload' is distinct from coalesce(p_payload,'{}'::jsonb) then
      raise exception using errcode='22023',message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(coalesce(v_existing.details->'result',jsonb_build_object('id',v_existing.entity_id)),'{replayed}','true'::jsonb,true);
  end if;
  perform pg_advisory_xact_lock(hashtextextended(v_actor::text,1));
  if exists(select 1 from public.suppliers where owner_user_id=v_actor) then
    raise exception using errcode='23505',message='supplier_profile_already_exists';
  end if;
  insert into public.suppliers(
    owner_user_id,legal_name,display_name,supplier_type,status,contact_name,contact_email,contact_phone,
    address,business_registration_number,website_url
  ) values (
    v_actor,v_legal_name,v_display_name,v_type,'pending_review',
    nullif(btrim(p_payload->>'contact_name'),''),nullif(btrim(p_payload->>'contact_email'),''),
    nullif(btrim(p_payload->>'contact_phone'),''),coalesce(p_payload->'address','{}'::jsonb),
    nullif(btrim(p_payload->>'business_registration_number'),''),nullif(btrim(p_payload->>'website_url'),'')
  ) returning * into v_supplier;
  v_result:=jsonb_build_object('supplier',to_jsonb(v_supplier),'replayed',false);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,'supplier_onboard','supplier',v_supplier.id,p_request_id,
    jsonb_build_object('action','supplier_onboard','payload',coalesce(p_payload,'{}'::jsonb),'target_id',null,'result',v_result));
  return v_result;
end;
$function$;

create or replace function public.oto_supplier_document_register(p_supplier_id uuid,p_payload jsonb,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog','public','storage'
as $function$
declare
  v_actor uuid := auth.uid();
  v_role public.oto_user_role;
  v_active boolean;
  v_existing public.audit_logs%rowtype;
  v_document public.supplier_documents%rowtype;
  v_result jsonb;
  v_path text := nullif(btrim(p_payload->>'storage_path'),'');
  v_type text := nullif(btrim(p_payload->>'document_type'),'');
  v_mime text := nullif(btrim(p_payload->>'content_type'),'');
  v_size bigint := nullif(p_payload->>'file_size_bytes','')::bigint;
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
  select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
  if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_required_or_length_invalid'; end if;
  if p_supplier_id is null or not exists(select 1 from public.suppliers s where s.id=p_supplier_id and s.owner_user_id=v_actor and s.status in ('pending_review','active')) then
    raise exception using errcode='42501',message='supplier_ownership_required';
  end if;
  if v_type not in ('business_registration','tax_registration','business_license','identity_authorization','source_rights','other')
    or v_mime not in ('application/pdf','image/jpeg','image/png')
    or v_path is null or v_path !~ ('^'||v_actor::text||'/'||p_supplier_id::text||'/')
    or v_size is null or v_size<1 or v_size>10485760
    or nullif(btrim(p_payload->>'original_filename'),'') is null then
    raise exception using errcode='22023',message='supplier_document_metadata_invalid';
  end if;
  if not exists(select 1 from storage.objects o where o.bucket_id='supplier-verification-documents' and o.name=v_path) then
    raise exception using errcode='P0002',message='uploaded_supplier_document_not_found';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(v_actor::text || ':' || p_request_id,0));
  select * into v_existing from public.audit_logs where actor_user_id=v_actor and request_id=p_request_id limit 1;
  if found then
    if v_existing.details->>'action' is distinct from 'supplier_document_register'
      or v_existing.details->'payload' is distinct from coalesce(p_payload,'{}'::jsonb)
      or v_existing.details->'target_id' is distinct from to_jsonb(p_supplier_id) then
      raise exception using errcode='22023',message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(coalesce(v_existing.details->'result',jsonb_build_object('id',v_existing.entity_id)),'{replayed}','true'::jsonb,true);
  end if;
  insert into public.supplier_documents(supplier_id,document_type,storage_path,original_filename,content_type,file_size_bytes,sha256,expires_at,created_by)
  values(p_supplier_id,v_type,v_path,nullif(btrim(p_payload->>'original_filename'),''),v_mime,v_size,
    nullif(btrim(p_payload->>'sha256'),''),nullif(p_payload->>'expires_at','')::timestamptz,v_actor)
  returning * into v_document;
  v_result:=jsonb_build_object('document',to_jsonb(v_document),'replayed',false);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,'supplier_document_register','supplier_document',v_document.id,p_request_id,
    jsonb_build_object('action','supplier_document_register','payload',coalesce(p_payload,'{}'::jsonb),'target_id',p_supplier_id,'result',v_result));
  return v_result;
end;
$function$;

create or replace function public.oto_supplier_offer_submit(p_supplier_id uuid,p_payload jsonb,p_request_id text)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog','public','storage'
as $function$
declare
  v_actor uuid := auth.uid();
  v_role public.oto_user_role;
  v_active boolean;
  v_existing public.audit_logs%rowtype;
  v_supplier public.suppliers%rowtype;
  v_offer public.supplier_offers%rowtype;
  v_result jsonb;
  v_sku text := nullif(btrim(p_payload->>'supplier_sku'),'');
  v_source_url text := nullif(btrim(p_payload->>'source_url'),'');
  v_product_id uuid := nullif(p_payload->>'product_id','')::uuid;
  v_condition public.oto_product_condition;
  v_unit_cost numeric := nullif(p_payload->>'unit_cost','')::numeric;
  v_asking_price numeric := nullif(p_payload->>'asking_price','')::numeric;
  v_stock integer := nullif(p_payload->>'stock_quantity','')::integer;
  v_expiry timestamptz := nullif(p_payload->>'quote_expires_at','')::timestamptz;
  v_lead integer := coalesce(nullif(p_payload->>'lead_time_days','')::integer,0);
  v_moq integer := coalesce(nullif(p_payload->>'minimum_order_quantity','')::integer,1);
  v_warranty integer := coalesce(nullif(p_payload->>'warranty_days','')::integer,0);
  v_evidence jsonb := coalesce(p_payload->'source_evidence','{}'::jsonb);
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
  select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
  if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_required_or_length_invalid'; end if;
  select * into v_supplier from public.suppliers where id=p_supplier_id and owner_user_id=v_actor for update;
  if not found or v_supplier.status<>'active' then raise exception using errcode='42501',message='active_supplier_required'; end if;
  if v_sku is null and v_source_url is null then raise exception using errcode='22023',message='supplier_sku_or_source_url_required'; end if;
  if v_unit_cost is null or v_unit_cost<0 or (v_asking_price is not null and v_asking_price<0) or v_stock is null or v_stock<0 then
    raise exception using errcode='22023',message='supplier_offer_price_or_stock_invalid';
  end if;
  if v_expiry is null or v_expiry<=now() then raise exception using errcode='22023',message='supplier_quote_expiry_must_be_future'; end if;
  if v_lead<0 or v_moq<1 or v_warranty<0 then raise exception using errcode='22023',message='supplier_offer_terms_invalid'; end if;
  if jsonb_typeof(v_evidence)<>'object' or v_evidence='{}'::jsonb then raise exception using errcode='22023',message='supplier_source_evidence_required'; end if;
  if v_source_url is not null and v_source_url !~* '^https?://' then raise exception using errcode='22023',message='supplier_source_url_invalid'; end if;
  v_condition:=(p_payload->>'condition')::public.oto_product_condition;
  if v_product_id is not null and not exists(select 1 from public.products where id=v_product_id and status not in ('archived','rejected')) then
    raise exception using errcode='P0002',message='supplier_offer_product_not_found';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(v_actor::text || ':' || p_request_id,0));
  select * into v_existing from public.audit_logs where actor_user_id=v_actor and request_id=p_request_id limit 1;
  if found then
    if v_existing.details->>'action' is distinct from 'supplier_offer_submit'
      or v_existing.details->'payload' is distinct from coalesce(p_payload,'{}'::jsonb)
      or v_existing.details->'target_id' is distinct from to_jsonb(p_supplier_id) then
      raise exception using errcode='22023',message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(coalesce(v_existing.details->'result',jsonb_build_object('id',v_existing.entity_id)),'{replayed}','true'::jsonb,true);
  end if;
  if v_sku is not null then
    select * into v_offer from public.supplier_offers
    where supplier_id=p_supplier_id and lower(btrim(supplier_sku))=lower(v_sku) and status in ('pending_review','active')
    order by created_at desc limit 1 for update;
  else
    select * into v_offer from public.supplier_offers
    where supplier_id=p_supplier_id and lower(btrim(source_url))=lower(v_source_url) and status in ('pending_review','active')
    order by created_at desc limit 1 for update;
  end if;
  if found then
    update public.supplier_offers set product_id=v_product_id,supplier_sku=v_sku,source_url=v_source_url,
      source_evidence=v_evidence,condition=v_condition,unit_cost=v_unit_cost,asking_price=v_asking_price,currency='IDR',
      stock_quantity=v_stock,stock_checked_at=now(),quote_expires_at=v_expiry,status='pending_review',
      lead_time_days=v_lead,minimum_order_quantity=v_moq,warranty_days=v_warranty,
      last_verified_by=null,source_verified_at=null,updated_at=now()
    where id=v_offer.id returning * into v_offer;
  else
    insert into public.supplier_offers(
      supplier_id,product_id,supplier_sku,source_url,source_evidence,condition,unit_cost,asking_price,currency,
      stock_quantity,stock_checked_at,quote_expires_at,status,lead_time_days,minimum_order_quantity,warranty_days
    ) values (
      p_supplier_id,v_product_id,v_sku,v_source_url,v_evidence,v_condition,v_unit_cost,v_asking_price,'IDR',
      v_stock,now(),v_expiry,'pending_review',v_lead,v_moq,v_warranty
    ) returning * into v_offer;
  end if;
  v_result:=jsonb_build_object('offer',to_jsonb(v_offer),'replayed',false);
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,'supplier_offer_submit','supplier_offer',v_offer.id,p_request_id,
    jsonb_build_object('action','supplier_offer_submit','payload',coalesce(p_payload,'{}'::jsonb),'target_id',p_supplier_id,'result',v_result));
  return v_result;
end;
$function$;
