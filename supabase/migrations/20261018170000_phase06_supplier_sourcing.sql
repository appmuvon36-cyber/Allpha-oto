-- Phase 06 — Supplier & Sourcing.
-- Additive extension of the existing supplier tables; no production rows are deleted.
alter table public.suppliers
  add column if not exists business_registration_number text,
  add column if not exists website_url text,
  add column if not exists reviewed_by uuid references auth.users(id) on delete set null,
  add column if not exists reviewed_at timestamptz,
  add column if not exists review_note text;

alter table public.supplier_offers
  add column if not exists lead_time_days integer not null default 0,
  add column if not exists minimum_order_quantity integer not null default 1,
  add column if not exists warranty_days integer not null default 0,
  add column if not exists last_verified_by uuid references auth.users(id) on delete set null,
  add column if not exists source_verified_at timestamptz;

do $$
begin
  if not exists (select 1 from pg_constraint where conrelid='public.suppliers'::regclass and conname='suppliers_website_url_scheme_check') then
    alter table public.suppliers add constraint suppliers_website_url_scheme_check
      check (website_url is null or website_url ~* '^https?://');
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.supplier_offers'::regclass and conname='supplier_offers_lead_time_days_check') then
    alter table public.supplier_offers add constraint supplier_offers_lead_time_days_check check (lead_time_days >= 0);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.supplier_offers'::regclass and conname='supplier_offers_minimum_order_quantity_check') then
    alter table public.supplier_offers add constraint supplier_offers_minimum_order_quantity_check check (minimum_order_quantity >= 1);
  end if;
  if not exists (select 1 from pg_constraint where conrelid='public.supplier_offers'::regclass and conname='supplier_offers_warranty_days_check') then
    alter table public.supplier_offers add constraint supplier_offers_warranty_days_check check (warranty_days >= 0);
  end if;
end $$;

create table if not exists public.supplier_documents (
  id uuid primary key default gen_random_uuid(),
  supplier_id uuid not null references public.suppliers(id) on delete restrict,
  document_type text not null check (document_type in ('business_registration','tax_registration','business_license','identity_authorization','source_rights','other')),
  storage_path text not null unique,
  original_filename text not null,
  content_type text not null check (content_type in ('application/pdf','image/jpeg','image/png')),
  file_size_bytes bigint not null check (file_size_bytes between 1 and 10485760),
  sha256 text check (sha256 is null or sha256 ~ '^[a-fA-F0-9]{64}$'),
  expires_at timestamptz,
  status text not null default 'pending_review' check (status in ('pending_review','verified','rejected','expired')),
  review_note text,
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists suppliers_owner_user_id_idx on public.suppliers(owner_user_id);
create unique index if not exists suppliers_owner_user_id_unique
  on public.suppliers(owner_user_id) where owner_user_id is not null;
create index if not exists suppliers_status_created_idx on public.suppliers(status,created_at desc);
create index if not exists supplier_offers_supplier_status_idx on public.supplier_offers(supplier_id,status,updated_at desc);
create index if not exists supplier_offers_expiry_stock_idx on public.supplier_offers(status,quote_expires_at,stock_checked_at desc);
create index if not exists supplier_documents_supplier_status_idx on public.supplier_documents(supplier_id,status,created_at desc);
create unique index if not exists supplier_offers_supplier_sku_live_uidx
  on public.supplier_offers(supplier_id,lower(btrim(supplier_sku)))
  where supplier_sku is not null and status in ('pending_review','active');

alter table public.supplier_documents enable row level security;
grant select on public.supplier_documents to authenticated;

drop policy if exists "supplier owners read own documents" on public.supplier_documents;
create policy "supplier owners read own documents" on public.supplier_documents
  for select to authenticated
  using (exists (
    select 1 from public.suppliers s
    where s.id=supplier_documents.supplier_id and s.owner_user_id=(select auth.uid())
  ));

drop policy if exists "staff manages supplier documents" on public.supplier_documents;
create policy "staff manages supplier documents" on public.supplier_documents
  for all to authenticated
  using (public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role]))
  with check (public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role]));

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('supplier-verification-documents','supplier-verification-documents',false,10485760,array['application/pdf','image/jpeg','image/png'])
on conflict (id) do update set public=false,file_size_limit=10485760,allowed_mime_types=array['application/pdf','image/jpeg','image/png'];

drop policy if exists "supplier owners upload verification documents" on storage.objects;
create policy "supplier owners upload verification documents" on storage.objects
  for insert to authenticated
  with check (
    bucket_id='supplier-verification-documents'
    and (storage.foldername(name))[1]=(select auth.uid())::text
    and exists (
      select 1 from public.suppliers s
      where s.owner_user_id=(select auth.uid())
        and s.id::text=(storage.foldername(name))[2]
        and s.status in ('pending_review','active')
    )
  );

drop policy if exists "supplier owners read verification documents" on storage.objects;
create policy "supplier owners read verification documents" on storage.objects
  for select to authenticated
  using (
    bucket_id='supplier-verification-documents'
    and (storage.foldername(name))[1]=(select auth.uid())::text
    and exists (
      select 1 from public.suppliers s
      where s.owner_user_id=(select auth.uid())
        and s.id::text=(storage.foldername(name))[2]
    )
  );

drop policy if exists "staff read supplier verification documents" on storage.objects;
create policy "staff read supplier verification documents" on storage.objects
  for select to authenticated
  using (
    bucket_id='supplier-verification-documents'
    and public.oto_has_staff_role(array['admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role])
  );

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
  v_existing public.audit_logs%rowtype;
  v_document public.supplier_documents%rowtype;
  v_result jsonb;
  v_path text := nullif(btrim(p_payload->>'storage_path'),'');
  v_type text := nullif(btrim(p_payload->>'document_type'),'');
  v_mime text := nullif(btrim(p_payload->>'content_type'),'');
  v_size bigint := nullif(p_payload->>'file_size_bytes','')::bigint;
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
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

create or replace function public.oto_supplier_admin_mutate(
  p_action text,p_supplier_id uuid default null,p_offer_id uuid default null,p_document_id uuid default null,
  p_payload jsonb default '{}'::jsonb,p_request_id text default null
)
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
  v_document public.supplier_documents%rowtype;
  v_result jsonb;
  v_target uuid := coalesce(p_document_id,p_offer_id,p_supplier_id);
  v_reason text := nullif(btrim(p_payload->>'reason'),'');
  v_doc_status text := nullif(btrim(p_payload->>'status'),'');
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
  select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
  if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
  if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role,'inventory_manager'::public.oto_user_role) then
    raise exception using errcode='42501',message='supplier_operations_role_required';
  end if;
  if p_request_id is null or length(btrim(p_request_id))<8 or length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_required_or_length_invalid'; end if;
  if p_action not in ('approve_supplier','reject_supplier','suspend_supplier','review_supplier_document','approve_offer','reject_offer','expire_offer') then
    raise exception using errcode='22023',message='unsupported_supplier_action';
  end if;
  if p_action in ('approve_supplier','reject_supplier','suspend_supplier','review_supplier_document') and v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role) then
    raise exception using errcode='42501',message='admin_or_moderator_required';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(v_actor::text || ':' || p_request_id,0));
  select * into v_existing from public.audit_logs where actor_user_id=v_actor and request_id=p_request_id limit 1;
  if found then
    if v_existing.details->>'action' is distinct from p_action
      or v_existing.details->'payload' is distinct from coalesce(p_payload,'{}'::jsonb)
      or v_existing.details->'target_id' is distinct from coalesce(to_jsonb(v_target),'null'::jsonb) then
      raise exception using errcode='22023',message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(coalesce(v_existing.details->'result',jsonb_build_object('id',v_existing.entity_id)),'{replayed}','true'::jsonb,true);
  end if;
  if p_action in ('approve_supplier','reject_supplier','suspend_supplier') then
    if p_supplier_id is null then raise exception using errcode='22023',message='supplier_id_required'; end if;
    select * into v_supplier from public.suppliers where id=p_supplier_id for update;
    if not found then raise exception using errcode='P0002',message='supplier_not_found'; end if;
    if p_action='approve_supplier' then
      if v_supplier.status<>'pending_review' then raise exception using errcode='22023',message='supplier_not_pending_review'; end if;
      if not exists(select 1 from public.supplier_documents where supplier_id=p_supplier_id and status='verified') then
        raise exception using errcode='22023',message='verified_supplier_document_required';
      end if;
      update public.suppliers set status='active',reviewed_by=v_actor,reviewed_at=now(),review_note=null,updated_at=now()
      where id=p_supplier_id returning * into v_supplier;
    elsif p_action='reject_supplier' then
      if v_reason is null then raise exception using errcode='22023',message='supplier_rejection_reason_required'; end if;
      update public.suppliers set status='rejected',reviewed_by=v_actor,reviewed_at=now(),review_note=v_reason,updated_at=now()
      where id=p_supplier_id returning * into v_supplier;
    else
      if v_reason is null then raise exception using errcode='22023',message='supplier_suspension_reason_required'; end if;
      if v_supplier.status<>'active' then raise exception using errcode='22023',message='only_active_supplier_can_be_suspended'; end if;
      update public.suppliers set status='suspended',reviewed_by=v_actor,reviewed_at=now(),review_note=v_reason,updated_at=now()
      where id=p_supplier_id returning * into v_supplier;
    end if;
    v_result:=jsonb_build_object('supplier',to_jsonb(v_supplier),'replayed',false);
  elsif p_action='review_supplier_document' then
    if p_document_id is null or v_doc_status not in ('verified','rejected') then raise exception using errcode='22023',message='supplier_document_review_invalid'; end if;
    if v_doc_status='rejected' and v_reason is null then raise exception using errcode='22023',message='supplier_document_rejection_reason_required'; end if;
    update public.supplier_documents set status=v_doc_status,review_note=v_reason,reviewed_by=v_actor,reviewed_at=now(),updated_at=now()
    where id=p_document_id returning * into v_document;
    if not found then raise exception using errcode='P0002',message='supplier_document_not_found'; end if;
    v_result:=jsonb_build_object('document',to_jsonb(v_document),'replayed',false);
  else
    if p_offer_id is null then raise exception using errcode='22023',message='supplier_offer_id_required'; end if;
    select * into v_offer from public.supplier_offers where id=p_offer_id for update;
    if not found then raise exception using errcode='P0002',message='supplier_offer_not_found'; end if;
    if p_action='approve_offer' then
      if v_offer.status<>'pending_review' then raise exception using errcode='22023',message='supplier_offer_not_pending_review'; end if;
      if not exists(select 1 from public.suppliers where id=v_offer.supplier_id and status='active') then raise exception using errcode='22023',message='active_supplier_required'; end if;
      if v_offer.unit_cost is null or v_offer.quote_expires_at is null or v_offer.quote_expires_at<=now()
        or v_offer.stock_checked_at is null or v_offer.stock_checked_at<now()-interval '24 hours'
        or v_offer.source_evidence='{}'::jsonb then
        raise exception using errcode='22023',message='supplier_offer_evidence_price_stock_or_expiry_invalid';
      end if;
      update public.supplier_offers set status='active',last_verified_by=v_actor,source_verified_at=now(),updated_at=now()
      where id=p_offer_id returning * into v_offer;
    elsif p_action='reject_offer' then
      if v_reason is null then raise exception using errcode='22023',message='supplier_offer_rejection_reason_required'; end if;
      update public.supplier_offers set status='rejected',last_verified_by=v_actor,source_verified_at=null,updated_at=now()
      where id=p_offer_id returning * into v_offer;
    else
      update public.supplier_offers set status='expired',last_verified_by=v_actor,updated_at=now()
      where id=p_offer_id returning * into v_offer;
    end if;
    v_result:=jsonb_build_object('offer',to_jsonb(v_offer),'replayed',false);
  end if;
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,p_action,case when p_action='review_supplier_document' then 'supplier_document' when p_action in ('approve_offer','reject_offer','expire_offer') then 'supplier_offer' else 'supplier' end,
    coalesce(p_document_id,p_offer_id,p_supplier_id),p_request_id,
    jsonb_build_object('action',p_action,'payload',coalesce(p_payload,'{}'::jsonb),'target_id',v_target,'result',v_result));
  return v_result;
end;
$function$;

revoke all on function public.oto_supplier_onboard(jsonb,text) from public,anon;
revoke all on function public.oto_supplier_document_register(uuid,jsonb,text) from public,anon;
revoke all on function public.oto_supplier_offer_submit(uuid,jsonb,text) from public,anon;
revoke all on function public.oto_supplier_admin_mutate(text,uuid,uuid,uuid,jsonb,text) from public,anon;
grant execute on function public.oto_supplier_onboard(jsonb,text) to authenticated;
grant execute on function public.oto_supplier_document_register(uuid,jsonb,text) to authenticated;
grant execute on function public.oto_supplier_offer_submit(uuid,jsonb,text) to authenticated;
grant execute on function public.oto_supplier_admin_mutate(text,uuid,uuid,uuid,jsonb,text) to authenticated;
