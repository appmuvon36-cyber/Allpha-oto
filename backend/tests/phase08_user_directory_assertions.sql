-- Phase 08 user-directory and trusted profile-provisioning assertions.
-- This file runs only against the disposable GitHub Actions PostgreSQL database.
DO $$
DECLARE
  admin_id uuid := '08000000-0000-4000-8000-000000000001';
  existing_customer_id uuid := '07000000-0000-4000-8000-000000000001';
  missing_profile_id uuid := '08000000-0000-4000-8000-000000000003';
  unknown_auth_id uuid := '08000000-0000-4000-8000-000000000099';
  result jsonb;
  provision_result jsonb;
  audit_count integer;
BEGIN
  INSERT INTO auth.users(id, email, created_at)
  VALUES (missing_profile_id, 'phase08-missing-profile@example.invalid', now())
  ON CONFLICT (id) DO NOTHING;

  DELETE FROM public.user_profiles WHERE id = missing_profile_id;

  PERFORM set_config('request.jwt.claim.sub', admin_id::text, true);
  result := public.oto_admin_list_users(NULL, NULL, 'missing_profile', 50, 0);

  IF (result->>'count')::integer < 1
     OR NOT EXISTS (
       SELECT 1 FROM jsonb_array_elements(result->'items') AS item
       WHERE item->>'id' = missing_profile_id::text
         AND item->>'has_profile' = 'false'
         AND item->'role' = 'null'::jsonb
         AND item->'is_active' = 'null'::jsonb
     ) THEN
    RAISE EXCEPTION 'phase08 user directory did not include Auth identity missing its profile';
  END IF;
  IF position('phase08-missing-profile@example.invalid' IN result::text) > 0
     OR position('"email"' IN result::text) > 0 THEN
    RAISE EXCEPTION 'phase08 user directory exposed Auth email fields';
  END IF;

  result := public.oto_admin_list_users(NULL, 'customer'::public.oto_user_role, 'active', 50, 0);
  IF NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(result->'items') AS item
    WHERE item->>'role' = 'customer' AND item->>'is_active' = 'true' AND item->>'has_profile' = 'true'
  ) THEN
    RAISE EXCEPTION 'phase08 role and active-status filters returned no matching customer';
  END IF;

  provision_result := public.oto_admin_provision_user_profile(missing_profile_id, 'phase08-profile-provision-01');
  IF provision_result#>>'{profile,id}' <> missing_profile_id::text
     OR provision_result#>>'{profile,role}' <> 'customer'
     OR provision_result#>>'{profile,is_active}' <> 'true'
     OR provision_result->>'replayed' <> 'false' THEN
    RAISE EXCEPTION 'phase08 provisioning did not create a customer profile for the existing Auth identity';
  END IF;

  result := public.oto_admin_provision_user_profile(missing_profile_id, 'phase08-profile-provision-01');
  IF result->>'replayed' <> 'true' THEN
    RAISE EXCEPTION 'phase08 profile provisioning retry was not idempotent';
  END IF;

  BEGIN
    PERFORM public.oto_admin_provision_user_profile(missing_profile_id, 'phase08-profile-provision-02');
    RAISE EXCEPTION 'phase08 duplicate profile provisioning unexpectedly succeeded';
  EXCEPTION WHEN unique_violation THEN
    IF position('profile_already_exists' IN SQLERRM) = 0 THEN RAISE; END IF;
  END;

  BEGIN
    PERFORM public.oto_admin_provision_user_profile(unknown_auth_id, 'phase08-profile-provision-03');
    RAISE EXCEPTION 'phase08 provisioning an unknown Auth identity unexpectedly succeeded';
  EXCEPTION WHEN no_data_found THEN
    IF position('auth_identity_not_found' IN SQLERRM) = 0 THEN RAISE; END IF;
  END;

  SELECT count(*) INTO audit_count
    FROM public.audit_logs
   WHERE actor_user_id = admin_id
     AND request_id = 'phase08-profile-provision-01'
     AND action = 'admin_provision_user_profile';
  IF audit_count <> 1 THEN
    RAISE EXCEPTION 'phase08 profile provisioning audit count mismatch';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.oto_idempotency_records
    WHERE actor_user_id = admin_id
      AND request_id = 'phase08-profile-provision-01'
      AND action = 'admin_provision_user_profile'
      AND target_id = missing_profile_id
  ) THEN
    RAISE EXCEPTION 'phase08 profile provisioning idempotency record missing';
  END IF;

  PERFORM set_config('request.jwt.claim.sub', existing_customer_id::text, true);
  BEGIN
    PERFORM public.oto_admin_list_users(NULL, NULL, 'all', 50, 0);
    RAISE EXCEPTION 'phase08 non-admin user directory access unexpectedly succeeded';
  EXCEPTION WHEN SQLSTATE '42501' THEN
    IF position('admin_role_required' IN SQLERRM) = 0 THEN RAISE; END IF;
  END;
END $$;
