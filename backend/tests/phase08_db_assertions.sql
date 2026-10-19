-- Phase 08 governance RPC integration assertions; disposable PostgreSQL only.
do $$
declare
  admin_id uuid := '08000000-0000-4000-8000-000000000001';
  target_id uuid := '08000000-0000-4000-8000-000000000002';
  result jsonb;
  audit_count integer;
begin
  insert into auth.users(id,email) values
    (admin_id,'phase08-admin@example.invalid'),
    (target_id,'phase08-target@example.invalid')
  on conflict (id) do nothing;

  insert into public.user_profiles(id,display_name,role,is_active,created_at,updated_at)
  values
    (admin_id,'Phase 08 Admin','admin',true,now(),now()),
    (target_id,'Phase 08 Target','customer',true,now(),now())
  on conflict (id) do update
    set display_name=excluded.display_name,role=excluded.role,is_active=excluded.is_active,updated_at=now();

  perform set_config('request.jwt.claim.sub',admin_id::text,true);
  result:=public.oto_admin_set_user_role(target_id,'inventory_manager'::public.oto_user_role,true,'phase08-role-change-01');
  if result#>>'{profile,role}'<>'inventory_manager' or result#>>'{profile,is_active}'<>'true' then
    raise exception 'phase08 role mutation did not return updated profile';
  end if;

  result:=public.oto_admin_set_user_role(target_id,'inventory_manager'::public.oto_user_role,true,'phase08-role-change-01');
  if result->>'replayed'<>'true' then raise exception 'phase08 role mutation replay was not idempotent'; end if;

  begin
    perform public.oto_admin_set_user_role(target_id,'moderator'::public.oto_user_role,true,'phase08-role-change-01');
    raise exception 'phase08 idempotency conflict unexpectedly succeeded';
  exception when sqlstate '22023' then
    if position('request_id_reused_for_different_operation' in sqlerrm)=0 then raise; end if;
  end;

  begin
    perform public.oto_admin_set_user_role(admin_id,'customer'::public.oto_user_role,false,'phase08-self-change-01');
    raise exception 'phase08 self role mutation unexpectedly succeeded';
  exception when sqlstate '22023' then
    if position('cannot_change_own_role_or_active_state' in sqlerrm)=0 then raise; end if;
  end;

  select count(*) into audit_count from public.audit_logs
    where actor_user_id=admin_id and request_id='phase08-role-change-01' and action='admin_set_user_role';
  if audit_count<>1 then raise exception 'phase08 role mutation audit count mismatch'; end if;
end $$;
