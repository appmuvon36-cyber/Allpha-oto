-- Phase 08: admin user directory includes Auth identities without profiles.
-- Provisioning is restricted to existing Auth identities and always starts as an active customer.
CREATE OR REPLACE FUNCTION public.oto_admin_list_users(
  p_query text DEFAULT NULL,
  p_role public.oto_user_role DEFAULT NULL,
  p_status text DEFAULT 'all',
  p_limit integer DEFAULT 50,
  p_offset integer DEFAULT 0
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public', 'auth'
AS $function$
DECLARE
  v_actor uuid := auth.uid();
  v_actor_role public.oto_user_role;
  v_actor_active boolean;
  v_query text := nullif(btrim(p_query), '');
  v_status text := coalesce(nullif(btrim(p_status), ''), 'all');
  v_count integer;
  v_items jsonb;
BEGIN
  IF v_actor IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'authentication_required';
  END IF;

  SELECT role, is_active INTO v_actor_role, v_actor_active
    FROM public.user_profiles WHERE id = v_actor;
  IF NOT FOUND OR v_actor_active IS DISTINCT FROM true OR v_actor_role <> 'admin'::public.oto_user_role THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'admin_role_required';
  END IF;

  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 OR p_offset IS NULL OR p_offset < 0 OR p_offset > 10000 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'user_directory_pagination_invalid';
  END IF;
  IF v_status NOT IN ('all', 'active', 'inactive', 'missing_profile') THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'user_directory_status_invalid';
  END IF;

  WITH filtered AS (
    SELECT
      u.id,
      p.display_name,
      p.role,
      p.is_active,
      p.created_at,
      p.updated_at,
      u.created_at AS auth_created_at,
      (p.id IS NOT NULL) AS has_profile
    FROM auth.users AS u
    LEFT JOIN public.user_profiles AS p ON p.id = u.id
    WHERE (
      v_query IS NULL
      OR u.id::text ILIKE '%' || v_query || '%'
      OR coalesce(p.display_name, '') ILIKE '%' || v_query || '%'
    )
    AND (p_role IS NULL OR p.role = p_role)
    AND (
      v_status = 'all'
      OR (v_status = 'active' AND p.id IS NOT NULL AND p.is_active IS TRUE)
      OR (v_status = 'inactive' AND p.id IS NOT NULL AND p.is_active IS FALSE)
      OR (v_status = 'missing_profile' AND p.id IS NULL)
    )
  )
  SELECT count(*)::integer INTO v_count FROM filtered;

  WITH filtered AS (
    SELECT
      u.id,
      p.display_name,
      p.role,
      p.is_active,
      p.created_at,
      p.updated_at,
      u.created_at AS auth_created_at,
      (p.id IS NOT NULL) AS has_profile,
      coalesce(p.created_at, u.created_at) AS sort_at
    FROM auth.users AS u
    LEFT JOIN public.user_profiles AS p ON p.id = u.id
    WHERE (
      v_query IS NULL
      OR u.id::text ILIKE '%' || v_query || '%'
      OR coalesce(p.display_name, '') ILIKE '%' || v_query || '%'
    )
    AND (p_role IS NULL OR p.role = p_role)
    AND (
      v_status = 'all'
      OR (v_status = 'active' AND p.id IS NOT NULL AND p.is_active IS TRUE)
      OR (v_status = 'inactive' AND p.id IS NOT NULL AND p.is_active IS FALSE)
      OR (v_status = 'missing_profile' AND p.id IS NULL)
    )
  )
  SELECT coalesce(jsonb_agg(
    jsonb_build_object(
      'id', page.id,
      'display_name', page.display_name,
      'role', page.role,
      'is_active', page.is_active,
      'created_at', page.created_at,
      'updated_at', page.updated_at,
      'auth_created_at', page.auth_created_at,
      'has_profile', page.has_profile
    ) ORDER BY page.sort_at DESC, page.id
  ), '[]'::jsonb)
  INTO v_items
  FROM (
    SELECT * FROM filtered
    ORDER BY sort_at DESC, id
    LIMIT p_limit OFFSET p_offset
  ) AS page;

  RETURN jsonb_build_object(
    'items', v_items,
    'count', v_count,
    'limit', p_limit,
    'offset', p_offset,
    'next_offset', CASE WHEN p_offset + p_limit < v_count THEN p_offset + p_limit ELSE NULL END
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.oto_admin_list_users(text, public.oto_user_role, text, integer, integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.oto_admin_list_users(text, public.oto_user_role, text, integer, integer) TO authenticated;


CREATE OR REPLACE FUNCTION public.oto_admin_provision_user_profile(
  p_target_user_id uuid,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public', 'auth'
AS $function$
DECLARE
  v_actor uuid := auth.uid();
  v_actor_role public.oto_user_role;
  v_actor_active boolean;
  v_old public.oto_idempotency_records%rowtype;
  v_profile public.user_profiles%rowtype;
  v_fingerprint text := md5(jsonb_build_object('target_user_id', p_target_user_id)::text);
  v_result jsonb;
BEGIN
  IF v_actor IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'authentication_required';
  END IF;
  IF p_target_user_id IS NULL OR p_request_id IS NULL OR length(btrim(p_request_id)) < 8 OR length(p_request_id) > 128 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'profile_provision_payload_invalid';
  END IF;

  SELECT role, is_active INTO v_actor_role, v_actor_active
    FROM public.user_profiles WHERE id = v_actor;
  IF NOT FOUND OR v_actor_active IS DISTINCT FROM true OR v_actor_role <> 'admin'::public.oto_user_role THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'admin_role_required';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(v_actor::text || ':' || p_request_id, 0));
  SELECT * INTO v_old
    FROM public.oto_idempotency_records
   WHERE actor_user_id = v_actor AND request_id = p_request_id
   FOR UPDATE;
  IF FOUND THEN
    IF v_old.action <> 'admin_provision_user_profile'
       OR v_old.target_id IS DISTINCT FROM p_target_user_id
       OR v_old.payload_fingerprint <> v_fingerprint THEN
      RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'request_id_reused_for_different_operation';
    END IF;
    RETURN jsonb_set(v_old.result, '{replayed}', 'true'::jsonb, true);
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended('oto_admin_provision_profile:' || p_target_user_id::text, 0));
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_target_user_id) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'auth_identity_not_found';
  END IF;
  IF EXISTS (SELECT 1 FROM public.user_profiles WHERE id = p_target_user_id) THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'profile_already_exists';
  END IF;

  INSERT INTO public.user_profiles(id, display_name, role, is_active)
  VALUES (p_target_user_id, NULL, 'customer'::public.oto_user_role, true)
  RETURNING * INTO v_profile;

  v_result := jsonb_build_object(
    'profile', jsonb_build_object(
      'id', v_profile.id,
      'display_name', v_profile.display_name,
      'role', v_profile.role,
      'is_active', v_profile.is_active,
      'created_at', v_profile.created_at,
      'updated_at', v_profile.updated_at,
      'has_profile', true
    ),
    'replayed', false
  );

  INSERT INTO public.audit_logs(actor_user_id, action, entity_type, entity_id, request_id, details)
  VALUES (
    v_actor,
    'admin_provision_user_profile',
    'user_profile',
    p_target_user_id,
    p_request_id,
    jsonb_build_object('initial_role', 'customer', 'reason', 'existing_auth_identity_missing_profile')
  );

  INSERT INTO public.oto_idempotency_records(actor_user_id, request_id, action, target_id, payload_fingerprint, result)
  VALUES (v_actor, p_request_id, 'admin_provision_user_profile', p_target_user_id, v_fingerprint, v_result);

  RETURN v_result;
END;
$function$;

REVOKE ALL ON FUNCTION public.oto_admin_provision_user_profile(uuid, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.oto_admin_provision_user_profile(uuid, text) TO authenticated;
