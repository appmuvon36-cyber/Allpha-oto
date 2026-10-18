-- Phase 05: audited catalog lifecycle and fitment review.
alter table public.products add column if not exists source_rights_evidence text;
create unique index if not exists audit_logs_actor_request_id_uidx on public.audit_logs (actor_user_id, request_id) where request_id is not null;
create or replace function public.oto_catalog_mutate(p_action text,p_product_id uuid default null,p_payload jsonb default '{}'::jsonb,p_request_id text default null)
returns jsonb language plpgsql security definer set search_path = pg_catalog, public as $$
declare
 v_actor uuid := auth.uid(); v_role public.oto_user_role; v_active boolean;
 v_product public.products%rowtype; v_fitment public.product_fitments%rowtype; v_existing public.audit_logs%rowtype;
 v_result jsonb; v_fitment_status public.oto_fitment_status; v_reason text;
begin
 if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
 select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
 if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
 if v_role not in ('admin'::public.oto_user_role,'catalog_editor'::public.oto_user_role,'moderator'::public.oto_user_role) then raise exception using errcode='42501',message='catalog_role_required'; end if;
 if p_action not in ('create_product','update_product','submit_review','approve_product','publish_product','reject_product','archive_product','save_fitment','review_fitment') then raise exception using errcode='22023',message='unsupported_catalog_action'; end if;
 if p_request_id is not null and length(p_request_id)>128 then raise exception using errcode='22023',message='request_id_too_long'; end if;
 if p_request_id is not null then
  select * into v_existing from public.audit_logs where actor_user_id=v_actor and request_id=p_request_id limit 1;
  if found then
   if v_existing.details->>'action' is distinct from p_action then raise exception using errcode='22023',message='request_id_reused_for_different_action'; end if;
   return coalesce(v_existing.details->'result',jsonb_build_object('id',v_existing.entity_id,'replayed',true));
  end if;
 end if;
 if p_action='create_product' then
  insert into public.products(sku,slug,name,description,brand,part_number,category,condition,condition_grade,package_quantity,warranty_days,currency,retail_price,fitment_summary,source_rights_evidence,status,created_by,updated_by)
  values(nullif(btrim(p_payload->>'sku'),''),nullif(btrim(p_payload->>'slug'),''),nullif(btrim(p_payload->>'name'),''),nullif(btrim(p_payload->>'description'),''),nullif(btrim(p_payload->>'brand'),''),nullif(btrim(p_payload->>'part_number'),''),nullif(btrim(p_payload->>'category'),''),(p_payload->>'condition')::public.oto_product_condition,nullif(btrim(p_payload->>'condition_grade'),''),coalesce((p_payload->>'package_quantity')::integer,1),coalesce((p_payload->>'warranty_days')::integer,0),'IDR',nullif(p_payload->>'retail_price','')::numeric,nullif(btrim(p_payload->>'fitment_summary'),''),nullif(btrim(p_payload->>'source_rights_evidence'),''),'draft',v_actor,v_actor)
  returning * into v_product;
  v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
 elsif p_action='save_fitment' then
  if p_product_id is null or nullif(p_payload->>'variant_id','') is null then raise exception using errcode='22023',message='product_and_variant_required'; end if;
  if not exists(select 1 from public.products where id=p_product_id and status<>'archived') then raise exception using errcode='P0002',message='product_not_found_or_archived'; end if;
  insert into public.product_fitments(product_id,variant_id,status,evidence_url,evidence_note)
  values(p_product_id,(p_payload->>'variant_id')::uuid,'needs_review',nullif(btrim(p_payload->>'evidence_url'),''),nullif(btrim(p_payload->>'evidence_note'),''))
  on conflict(product_id,variant_id) do update set status='needs_review',evidence_url=excluded.evidence_url,evidence_note=excluded.evidence_note,verified_by=null,verified_at=null
  returning * into v_fitment;
  v_result:=jsonb_build_object('fitment',to_jsonb(v_fitment),'replayed',false);
 elsif p_action='review_fitment' then
  if p_product_id is null or nullif(p_payload->>'fitment_id','') is null then raise exception using errcode='22023',message='product_and_fitment_required'; end if;
  v_fitment_status:=(p_payload->>'status')::public.oto_fitment_status;
  if v_fitment_status not in ('verified'::public.oto_fitment_status,'rejected'::public.oto_fitment_status) then raise exception using errcode='22023',message='fitment_review_status_invalid'; end if;
  if v_fitment_status='verified' and nullif(btrim(p_payload->>'evidence_note'),'') is null and nullif(btrim(p_payload->>'evidence_url'),'') is null then raise exception using errcode='22023',message='fitment_evidence_required'; end if;
  update public.product_fitments set status=v_fitment_status,evidence_url=coalesce(nullif(btrim(p_payload->>'evidence_url'),''),evidence_url),evidence_note=coalesce(nullif(btrim(p_payload->>'evidence_note'),''),evidence_note),verified_by=case when v_fitment_status='verified' then v_actor else null end,verified_at=case when v_fitment_status='verified' then now() else null end
  where id=(p_payload->>'fitment_id')::uuid and product_id=p_product_id returning * into v_fitment;
  if not found then raise exception using errcode='P0002',message='fitment_not_found'; end if;
  v_result:=jsonb_build_object('fitment',to_jsonb(v_fitment),'replayed',false);
 else
  if p_product_id is null then raise exception using errcode='22023',message='product_id_required'; end if;
  select * into v_product from public.products where id=p_product_id for update;
  if not found then raise exception using errcode='P0002',message='product_not_found'; end if;
  if p_action='update_product' then
   if v_product.status not in ('draft'::public.oto_product_status,'rejected'::public.oto_product_status) then raise exception using errcode='22023',message='only_draft_or_rejected_products_are_editable'; end if;
   update public.products set sku=case when p_payload?'sku' then nullif(btrim(p_payload->>'sku'),'') else sku end,slug=case when p_payload?'slug' then nullif(btrim(p_payload->>'slug'),'') else slug end,name=case when p_payload?'name' then nullif(btrim(p_payload->>'name'),'') else name end,description=case when p_payload?'description' then nullif(btrim(p_payload->>'description'),'') else description end,brand=case when p_payload?'brand' then nullif(btrim(p_payload->>'brand'),'') else brand end,part_number=case when p_payload?'part_number' then nullif(btrim(p_payload->>'part_number'),'') else part_number end,category=case when p_payload?'category' then nullif(btrim(p_payload->>'category'),'') else category end,condition=case when p_payload?'condition' then (p_payload->>'condition')::public.oto_product_condition else condition end,condition_grade=case when p_payload?'condition_grade' then nullif(btrim(p_payload->>'condition_grade'),'') else condition_grade end,package_quantity=case when p_payload?'package_quantity' then (p_payload->>'package_quantity')::integer else package_quantity end,warranty_days=case when p_payload?'warranty_days' then (p_payload->>'warranty_days')::integer else warranty_days end,retail_price=case when p_payload?'retail_price' then nullif(p_payload->>'retail_price','')::numeric else retail_price end,fitment_summary=case when p_payload?'fitment_summary' then nullif(btrim(p_payload->>'fitment_summary'),'') else fitment_summary end,source_rights_evidence=case when p_payload?'source_rights_evidence' then nullif(btrim(p_payload->>'source_rights_evidence'),'') else source_rights_evidence end,updated_by=v_actor where id=p_product_id returning * into v_product;
   v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
  elsif p_action='submit_review' then
   if v_product.status not in ('draft'::public.oto_product_status,'rejected'::public.oto_product_status) then raise exception using errcode='22023',message='invalid_product_transition'; end if;
   update public.products set status='review',updated_by=v_actor where id=p_product_id returning * into v_product; v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
  elsif p_action='approve_product' then
   if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role) then raise exception using errcode='42501',message='moderator_or_admin_required'; end if;
   if v_product.status<>'review' then raise exception using errcode='22023',message='invalid_product_transition'; end if;
   update public.products set status='approved',updated_by=v_actor where id=p_product_id returning * into v_product; v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
  elsif p_action='publish_product' then
   if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role) then raise exception using errcode='42501',message='moderator_or_admin_required'; end if;
   if v_product.status<>'approved' then raise exception using errcode='22023',message='invalid_product_transition'; end if;
   if nullif(btrim(v_product.sku),'') is null or nullif(btrim(v_product.slug),'') is null or nullif(btrim(v_product.name),'') is null or nullif(btrim(v_product.category),'') is null or v_product.condition is null or v_product.retail_price is null or v_product.retail_price<0 or nullif(btrim(v_product.source_rights_evidence),'') is null then raise exception using errcode='22023',message='publication_requirements_missing'; end if;
   update public.products set status='published',published_at=now(),updated_by=v_actor where id=p_product_id returning * into v_product; v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
  elsif p_action='reject_product' then
   if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role) then raise exception using errcode='42501',message='moderator_or_admin_required'; end if;
   if v_product.status not in ('review'::public.oto_product_status,'approved'::public.oto_product_status) then raise exception using errcode='22023',message='invalid_product_transition'; end if;
   v_reason:=nullif(btrim(p_payload->>'reason'),''); if v_reason is null then raise exception using errcode='22023',message='rejection_reason_required'; end if;
   update public.products set status='rejected',updated_by=v_actor where id=p_product_id returning * into v_product; v_result:=jsonb_build_object('product',to_jsonb(v_product),'reason',v_reason,'replayed',false);
  elsif p_action='archive_product' then
   if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role) then raise exception using errcode='42501',message='moderator_or_admin_required'; end if;
   if v_product.status='archived' then raise exception using errcode='22023',message='product_already_archived'; end if;
   update public.products set status='archived',updated_by=v_actor where id=p_product_id returning * into v_product; v_result:=jsonb_build_object('product',to_jsonb(v_product),'replayed',false);
  end if;
 end if;
 insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details) values(v_actor,p_action,case when p_action in ('save_fitment','review_fitment') then 'product_fitment' else 'product' end,case when p_action in ('save_fitment','review_fitment') then v_fitment.id else coalesce(v_product.id,p_product_id) end,p_request_id,jsonb_build_object('action',p_action,'result',v_result,'payload',p_payload));
 return v_result;
end;
$$;
revoke all on function public.oto_catalog_mutate(text,uuid,jsonb,text) from public,anon;
grant execute on function public.oto_catalog_mutate(text,uuid,jsonb,text) to authenticated;
