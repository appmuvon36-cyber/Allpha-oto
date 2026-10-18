-- Phase 06 exact identifier matching. Candidates are advisory only and are never linked automatically.
create or replace function public.oto_supplier_offer_match_candidates(p_offer_id uuid)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog','public'
as $fn$
declare
  v_actor uuid := auth.uid();
  v_role public.oto_user_role;
  v_active boolean;
  v_offer public.supplier_offers%rowtype;
  v_identifier text;
  v_evidence_part text;
  v_candidates jsonb;
begin
  if v_actor is null then raise exception using errcode='42501',message='authentication_required'; end if;
  select role,is_active into v_role,v_active from public.user_profiles where id=v_actor;
  if not found or v_active is distinct from true then raise exception using errcode='42501',message='active_profile_required'; end if;
  if v_role not in ('admin'::public.oto_user_role,'moderator'::public.oto_user_role,'catalog_editor'::public.oto_user_role,'inventory_manager'::public.oto_user_role) then
    raise exception using errcode='42501',message='supplier_operations_role_required';
  end if;
  select * into v_offer from public.supplier_offers where id=p_offer_id;
  if not found then raise exception using errcode='P0002',message='supplier_offer_not_found'; end if;
  v_identifier:=nullif(lower(btrim(v_offer.supplier_sku)),'');
  v_evidence_part:=nullif(lower(btrim(coalesce(v_offer.source_evidence->>'part_number',v_offer.source_evidence->>'oem_part_number'))),'');
  select coalesce(jsonb_agg(candidate order by rank_score desc,created_at desc),'[]'::jsonb)
    into v_candidates
  from (
    select jsonb_build_object(
      'product_id',p.id,'sku',p.sku,'part_number',p.part_number,'name',p.name,'brand',p.brand,
      'condition',p.condition,'status',p.status,
      'match_reason',case
        when v_identifier is not null and lower(btrim(coalesce(p.sku,'')))=v_identifier then 'exact_sku'
        when v_identifier is not null and lower(btrim(coalesce(p.part_number,'')))=v_identifier then 'exact_part_number'
        else 'evidence_part_number'
      end,
      'match_score',100,
      'automatic_linking',false,
      'fitment_verified',exists(select 1 from public.product_fitments f where f.product_id=p.id and f.status='verified')
    ) as candidate,
    case
      when v_identifier is not null and lower(btrim(coalesce(p.sku,'')))=v_identifier then 3
      when v_identifier is not null and lower(btrim(coalesce(p.part_number,'')))=v_identifier then 2
      else 1
    end as rank_score,
    p.created_at
    from public.products p
    where p.status not in ('archived'::public.oto_product_status,'rejected'::public.oto_product_status)
      and (
        (v_identifier is not null and (lower(btrim(coalesce(p.sku,'')))=v_identifier or lower(btrim(coalesce(p.part_number,'')))=v_identifier))
        or (v_evidence_part is not null and lower(btrim(coalesce(p.part_number,'')))=v_evidence_part)
      )
    order by rank_score desc,p.created_at desc
    limit 20
  ) candidates;
  return jsonb_build_object(
    'offer_id',p_offer_id,
    'match_method','exact_normalized_identifier',
    'automatic_linking',false,
    'candidates',v_candidates
  );
end;
$fn$;

revoke all on function public.oto_supplier_offer_match_candidates(uuid) from public,anon;
grant execute on function public.oto_supplier_offer_match_candidates(uuid) to authenticated;
