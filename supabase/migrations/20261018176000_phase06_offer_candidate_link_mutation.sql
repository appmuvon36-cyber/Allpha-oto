-- Phase 06: manually link an exact-identifier candidate only through audited staff mutation.
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
  v_product_id uuid;
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
  if p_action not in ('approve_supplier','reject_supplier','suspend_supplier','review_supplier_document','approve_offer','reject_offer','expire_offer','match_offer_product') then
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
      if not exists(select 1 from public.supplier_documents where supplier_id=p_supplier_id and status='verified' and (expires_at is null or expires_at>now())) then
        raise exception using errcode='22023',message='current_verified_supplier_document_required';
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
    if v_doc_status='verified' and v_document.expires_at is not null and v_document.expires_at<=now() then
      raise exception using errcode='22023',message='expired_supplier_document_cannot_be_verified';
    end if;
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
    elsif p_action='match_offer_product' then
      v_product_id:=nullif(p_payload->>'product_id','')::uuid;
      if v_product_id is null then raise exception using errcode='22023',message='candidate_product_id_required'; end if;
      if not exists(select 1 from public.products where id=v_product_id and status not in ('archived'::public.oto_product_status,'rejected'::public.oto_product_status)) then
        raise exception using errcode='P0002',message='candidate_product_not_found';
      end if;
      update public.supplier_offers set product_id=v_product_id,status='pending_review',last_verified_by=null,source_verified_at=null,updated_at=now()
      where id=p_offer_id returning * into v_offer;
    else
      update public.supplier_offers set status='expired',last_verified_by=v_actor,updated_at=now()
      where id=p_offer_id returning * into v_offer;
    end if;
    v_result:=jsonb_build_object('offer',to_jsonb(v_offer),'replayed',false);
  end if;
  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,p_action,case when p_action='review_supplier_document' then 'supplier_document' when p_action in ('approve_offer','reject_offer','expire_offer','match_offer_product') then 'supplier_offer' else 'supplier' end,
    coalesce(p_document_id,p_offer_id,p_supplier_id),p_request_id,
    jsonb_build_object('action',p_action,'payload',coalesce(p_payload,'{}'::jsonb),'target_id',v_target,'result',v_result));
  return v_result;
end;
$function$;
