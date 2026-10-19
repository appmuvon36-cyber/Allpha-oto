
create or replace function public.oto_admin_set_user_role(
  p_target_user_id uuid,
  p_role public.oto_user_role,
  p_is_active boolean,
  p_request_id text
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog','public'
as $function$
declare
  v_actor uuid := auth.uid();
  v_actor_role public.oto_user_role;
  v_actor_active boolean;
  v_before public.user_profiles%rowtype;
  v_after public.user_profiles%rowtype;
  v_old public.oto_idempotency_records%rowtype;
  v_fingerprint text := md5(jsonb_build_object('role',p_role::text,'is_active',p_is_active)::text);
  v_result jsonb;
  v_admin_count integer;
begin
  if v_actor is null then
    raise exception using errcode='42501', message='authentication_required';
  end if;
  if p_target_user_id is null or p_role is null or p_is_active is null then
    raise exception using errcode='22023', message='role_change_payload_invalid';
  end if;
  if p_request_id is null or length(btrim(p_request_id)) < 8 or length(p_request_id) > 128 then
    raise exception using errcode='22023', message='request_id_invalid';
  end if;

  select role,is_active into v_actor_role,v_actor_active
  from public.user_profiles where id=v_actor;
  if not found or v_actor_active is distinct from true or v_actor_role <> 'admin'::public.oto_user_role then
    raise exception using errcode='42501', message='admin_role_required';
  end if;
  if p_target_user_id = v_actor then
    raise exception using errcode='22023', message='cannot_change_own_role_or_active_state';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(v_actor::text || ':' || p_request_id, 0));
  select * into v_old from public.oto_idempotency_records
   where actor_user_id=v_actor and request_id=p_request_id for update;
  if found then
    if v_old.action <> 'admin_set_user_role'
       or v_old.target_id is distinct from p_target_user_id
       or v_old.payload_fingerprint <> v_fingerprint then
      raise exception using errcode='22023', message='request_id_reused_for_different_operation';
    end if;
    return jsonb_set(v_old.result, '{replayed}', 'true'::jsonb, true);
  end if;

  -- Serialize role changes so two concurrent requests cannot remove the last active administrator.
  perform pg_advisory_xact_lock(hashtextextended('oto_admin_role_guard', 0));
  select * into v_before from public.user_profiles where id=p_target_user_id for update;
  if not found then
    raise exception using errcode='P0002', message='target_profile_not_found';
  end if;

  if v_before.role='admin'::public.oto_user_role and v_before.is_active is true
     and (p_role <> 'admin'::public.oto_user_role or p_is_active is false) then
    select count(*) into v_admin_count from public.user_profiles
      where role='admin'::public.oto_user_role and is_active is true;
    if v_admin_count <= 1 then
      raise exception using errcode='23514', message='cannot_remove_last_active_admin';
    end if;
  end if;

  update public.user_profiles
     set role=p_role, is_active=p_is_active, updated_at=now()
   where id=p_target_user_id
   returning * into v_after;

  v_result := jsonb_build_object(
    'profile', jsonb_build_object(
      'id',v_after.id,
      'display_name',v_after.display_name,
      'role',v_after.role,
      'is_active',v_after.is_active,
      'updated_at',v_after.updated_at
    ),
    'replayed',false
  );

  insert into public.audit_logs(actor_user_id,action,entity_type,entity_id,request_id,details)
  values(v_actor,'admin_set_user_role','user_profile',p_target_user_id,p_request_id,
    jsonb_build_object(
      'before',jsonb_build_object('role',v_before.role,'is_active',v_before.is_active),
      'after',jsonb_build_object('role',v_after.role,'is_active',v_after.is_active)
    ));

  insert into public.oto_idempotency_records(actor_user_id,request_id,action,target_id,payload_fingerprint,result)
  values(v_actor,p_request_id,'admin_set_user_role',p_target_user_id,v_fingerprint,v_result);

  return v_result;
end;
$function$;

revoke all on function public.oto_admin_set_user_role(uuid,public.oto_user_role,boolean,text) from public,anon;
grant execute on function public.oto_admin_set_user_role(uuid,public.oto_user_role,boolean,text) to authenticated;
;
