create or replace function public.oto_product_media_review(
  p_media_id uuid,
  p_action text,
  p_request_id text
) returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_media public.product_media%rowtype;
  v_actor uuid := auth.uid();
  v_now timestamptz := now();
begin
  if v_actor is null then raise exception 'authentication_required' using errcode='42501'; end if;
  if not public.oto_has_staff_role(array['admin','catalog_editor','moderator']::public.oto_user_role[]) then
    raise exception 'staff_role_required' using errcode='42501';
  end if;
  if p_request_id is null or length(trim(p_request_id)) < 8 or length(p_request_id) > 160 then
    raise exception 'valid_request_id_required' using errcode='22023';
  end if;
  if p_action not in ('approve','reject','set_primary') then
    raise exception 'invalid_media_action' using errcode='22023';
  end if;

  select * into v_media from public.product_media where id=p_media_id for update;
  if not found then raise exception 'media_not_found' using errcode='P0002'; end if;

  if p_action='approve' then
    if v_media.rights_status not in ('user_owned','permission_granted','licensed','public_domain')
       or (coalesce(trim(v_media.rights_evidence_note),'')='' and coalesce(trim(v_media.rights_evidence_url),'')='') then
      raise exception 'rights_evidence_required' using errcode='23514';
    end if;
    update public.product_media set review_status='approved', reviewed_at=v_now, reviewed_by=v_actor, updated_at=v_now where id=p_media_id;
  elsif p_action='reject' then
    update public.product_media set review_status='rejected', is_primary=false, reviewed_at=v_now, reviewed_by=v_actor, updated_at=v_now where id=p_media_id;
  else
    if v_media.review_status <> 'approved' or v_media.rights_status not in ('user_owned','permission_granted','licensed','public_domain') then
      raise exception 'approved_rights_cleared_media_required' using errcode='23514';
    end if;
    update public.product_media set is_primary=false, updated_at=v_now where product_id=v_media.product_id;
    update public.product_media set is_primary=true, updated_at=v_now where id=p_media_id;
  end if;

  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,'product_media_'||p_action,'product_media',p_media_id,p_request_id,
    jsonb_build_object('product_id',v_media.product_id,'media_kind',v_media.media_kind,'rights_status',v_media.rights_status,'review_status',case when p_action='approve' then 'approved' when p_action='reject' then 'rejected' else v_media.review_status end));

  return jsonb_build_object('media_id',p_media_id,'product_id',v_media.product_id,'action',p_action,'review_status',case when p_action='approve' then 'approved' when p_action='reject' then 'rejected' else v_media.review_status end,'is_primary',p_action='set_primary');
end;
$$;
revoke all on function public.oto_product_media_review(uuid,text,text) from public, anon;
grant execute on function public.oto_product_media_review(uuid,text,text) to authenticated;